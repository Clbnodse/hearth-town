#!/usr/bin/env python3
"""P7-29 record-time allowlist (Claude re-review msg-2ef3cacc, minor 1).

In rev 1 a goal/plan/action carrying a kind outside the run's
allowlist (e.g. send_money on a claim_job run) was accepted into the
trace and refused only later at /action — so the audit log could show
"action_authorized send_money". The server now rejects such kinds at
record time (400 event_kind_not_in_allowlist) on goal_proposed,
plan_proposed, plan_accepted and action_authorized. A goal with no
candidate (goal None) and in-allowlist kinds still append.
"""
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18929


def main():
    h = Harness("p7_29", PORT).start()
    try:
        h.clear_rates()
        s, run = h.create_run("ember", mode="dry_run",
                              allowlist=["claim_job"], idem="m1-1")
        assert s == 201, (s, run)
        rid, ft = run["id"], run["fencing_token"]

        s, b = h.append_event("ember", rid, "memory_loaded", ft,
                              {"entries": 0})
        assert s == 201, (s, b)

        # Out-of-allowlist goal kind -> 400, no state change.
        s, b = h.append_event("ember", rid, "goal_proposed", ft,
                              {"goal": {"ref": "job", "kind": "send_money"}})
        assert s == 400 and b.get("error") == "event_kind_not_in_allowlist", (s, b)
        print("  goal_proposed kind send_money -> 400 "
              "event_kind_not_in_allowlist")

        # A goal with no candidate is still allowed.
        s, b = h.append_event("ember", rid, "goal_proposed", ft,
                              {"goal": None})
        assert s == 201, (s, b)
        print("  goal_proposed with goal None -> 201")

        s, b = h.append_event("ember", rid, "goal_accepted", ft,
                              {"goal": {"ref": "job"}})
        assert s == 201, (s, b)

        # Out-of-allowlist plan kind -> 400, then the in-allowlist
        # plan appends.
        s, b = h.append_event("ember", rid, "plan_proposed", ft,
                              {"plan": {"action": {"type": "send_money"}}})
        assert s == 400 and b.get("error") == "event_kind_not_in_allowlist", (s, b)
        print("  plan_proposed action send_money -> 400")
        s, b = h.append_event("ember", rid, "plan_proposed", ft,
                              {"plan": {"action": {"type": "claim_job"}}})
        assert s == 201, (s, b)

        s, b = h.append_event("ember", rid, "plan_accepted", ft,
                              {"plan": {"action": {"type": "send_money"}}})
        assert s == 400 and b.get("error") == "event_kind_not_in_allowlist", (s, b)
        print("  plan_accepted action send_money -> 400")
        s, b = h.append_event("ember", rid, "plan_accepted", ft,
                              {"plan": {"action": {"type": "claim_job"}}})
        assert s == 201, (s, b)

        # Out-of-allowlist action -> 400, then the real one appends.
        s, b = h.append_event("ember", rid, "action_authorized", ft,
                              {"action": {"type": "send_money"}})
        assert s == 400 and b.get("error") == "event_kind_not_in_allowlist", (s, b)
        print("  action_authorized send_money -> 400")
        s, b = h.append_event("ember", rid, "action_authorized", ft,
                              {"action": {"type": "claim_job"}})
        assert s == 201, (s, b)

        # The rejected kinds never entered the trace.
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                      token=h.tokens["ember"])
        assert s == 200, (s, b)
        assert "send_money" not in json.dumps(b), \
            "rejected kind is in the trace"
        print("  rejected kinds are absent from GET events")

        # A dry-run evaluation needs no action_result (P7-24 flow);
        # then the run completes from the evaluated state.
        s, b = h.append_event("ember", rid, "evaluation_recorded", ft,
                              {"dry_run": True, "outcome": "executed"})
        assert s == 201, (s, b)

        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {}, token=h.tokens["ember"])
        assert s == 200 and b.get("status") == "COMPLETE", (s, b)
        print("P7-29 record-time allowlist: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
