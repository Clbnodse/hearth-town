#!/usr/bin/env python3
"""P7-05 atomic kill switch.

  (a) Flip ON -> /action is refused (403 kill_switch_on). Flip OFF
      -> the same run's /action proceeds. The flip is recorded in
      the run's trace with a timestamp.
  (b) Race: an /action and a flip issued concurrently from two
      threads must have exactly one consistent outcome — either the
      action commits with action_started BEFORE the flip timestamp,
      or it is refused with the flip timestamp at/before the
      attempt. No action may start after the switch is observed ON.
  (c) A flip after action_started blocks every subsequent action.
"""
import sys
import threading
import time

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18905


def flip(h, enabled):
    return h.call("POST", "/v1/runs/kill-switch", {"enabled": enabled},
                  token=h.tokens["muse"])


def main():
    h = Harness("p7_05", PORT).start()
    try:
        h.clear_rates()
        # Rev 1 (S5): the test uses noop actions and creates runs in
        # rapid succession, so the policy allowlist includes noop
        # and the minimum cooldown is 0 for this test.
        s, b = h.set_run_policy("ember", {"min_cooldown_ms": 0,
                                          "allowlist": ["claim_job", "noop"]})
        assert s == 200, (s, b)
        job = h.make_job("kill switch quest", tags=["host", "quest"])
        job2 = h.make_job("kill switch quest two", tags=["host", "quest"])

        # (a) flip ON blocks the action; OFF lets it through.
        s, run = h.create_run("ember", mode="live", idem="ks-1")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        s, b = flip(h, True)
        assert s == 200 and b["enabled"] is True, (s, b)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "claim_job", "job_id": job["id"],
                                  "idempotency_key": "ks-claim"},
                       "fencing_token": ft, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 403 and b.get("error") == "kill_switch_on", (s, b)
        print("  flip ON -> /action 403 kill_switch_on")
        # The flip is in the run's trace with a timestamp.
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                      token=h.tokens["ember"])
        ks_evs = [e for e in b["events"]
                  if e["event_type"] == "run_kill_switch"]
        assert len(ks_evs) == 1 and ks_evs[0]["payload"]["enabled"] is True, b
        assert ks_evs[0]["payload"]["flipped_at"], ks_evs[0]
        print("  flip recorded in run trace (run_kill_switch + timestamp)")
        s, b = flip(h, False)
        assert s == 200 and b["enabled"] is False, (s, b)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "claim_job", "job_id": job["id"],
                                  "idempotency_key": "ks-claim"},
                       "fencing_token": ft, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 200 and b.get("outcome") == "executed", (s, b)
        print("  flip OFF -> same run's /action 200 executed")
        # Finish this run (evaluation + complete) so part (b) can
        # take a fresh lease each race iteration.
        s, b = h.append_event("ember", rid, "evaluation_recorded", ft,
                              {"outcome": "executed"}, exec_token=et)
        assert s == 201, (s, b)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {}, token=h.tokens["ember"])
        assert s == 200 and b.get("status") == "COMPLETE", (s, b)

        # (b) concurrent flip + action: exactly one consistent outcome.
        committed, refused = 0, 0
        for i in range(5):
            h.clear_rates()
            s, run = h.create_run("ember", mode="live", idem=f"ks-race-{i}")
            assert s == 201, (s, run)
            rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
            h.drive_to_authorized("ember", rid, ft, exec_token=et)
            assert flip(h, False)[0] == 200
            results = {}

            def do_action():
                s2, b2 = h.call(
                    "POST", f"/v1/residents/ember/runs/{rid}/action",
                    {"action": {"type": "noop"}, "fencing_token": ft,
                     "adapter_output_units": 0},
                    token=h.tokens["ember"],
                    extra_headers={"X-Run-Token": et})
                results["action"] = (s2, b2)

            def do_flip():
                s2, b2 = flip(h, True)
                results["flip"] = (s2, b2)

            t1 = threading.Thread(target=do_action)
            t2 = threading.Thread(target=do_flip)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            flip_ts = results["flip"][1]["flipped_at"]
            s2, b2 = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                            token=h.tokens["ember"])
            started = [e for e in b2["events"]
                       if e["event_type"] == "action_started"]
            if results["action"][0] == 200:
                committed += 1
                assert len(started) == 1, b2
                # action_started was recorded BEFORE the flip.
                assert started[0]["payload"]["kill_switch_read_at"] <= flip_ts, \
                    (started[0]["payload"], flip_ts)
            else:
                refused += 1
                assert results["action"][0] == 403, results["action"]
                assert results["action"][1].get("error") == "kill_switch_on"
                assert started == [], b2
            # tidy: flip OFF, block the run so the next race can start.
            assert flip(h, False)[0] == 200
            h.call("POST", f"/v1/residents/ember/runs/{rid}/block",
                   {"reason_code": "manual"}, token=h.tokens["ember"])
        print(f"  race x5: committed={committed} refused={refused} "
              "(each consistent with the flip timestamp)")

        # (c) flip after action_started blocks every subsequent action.
        s, run = h.create_run("ember", mode="live", idem="ks-3")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "noop"}, "fencing_token": ft,
                       "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 200, (s, b)
        assert flip(h, True)[0] == 200
        # No subsequent action may start after the flip. A second
        # action in the same run is refused (the run already acted —
        # the state check fires first); the trace must show exactly
        # one action_started.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "noop"}, "fencing_token": ft,
                       "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 409 and b.get("error") == "invalid_run_transition", (s, b)
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                      token=h.tokens["ember"])
        started = [e for e in b["events"]
                   if e["event_type"] == "action_started"]
        assert len(started) == 1, b
        # And a fresh run's action is refused too.
        assert flip(h, False)[0] == 200
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200, (s, b)
        s, run = h.create_run("ember", mode="live", idem="ks-4")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        assert flip(h, True)[0] == 200
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "noop"}, "fencing_token": ft,
                       "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 403 and b.get("error") == "kill_switch_on", (s, b)
        assert flip(h, False)[0] == 200
        print("  flip after action_started blocks all subsequent actions")
        print("P7-05 atomic kill switch: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
