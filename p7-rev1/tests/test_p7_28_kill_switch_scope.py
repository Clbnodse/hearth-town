#!/usr/bin/env python3
"""P7-28 kill-switch scope (rev 1, S9).

Claude's audit (re-state, not executed): run_kill_switch is read
only in _p7_run_action (one reference), so it does not stop the
live P6 --reason Ember cron, which claims directly with the
resident token today. CONFIRMED with the claim-route code:
_econ_claim_job_core (the one claim path, used by the legacy
direct-claim route) contains no kill-switch read; the switch is
read only in _p7_run_action. This test proves the scope live:
  - with the switch ON, the legacy direct-claim route still works;
  - with the switch ON, a P7 run action is refused 403;
  - with the switch OFF, the same P7 run's action proceeds.
Run creation is not gated by the switch (only /action is).
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18928


def set_switch(h, enabled, token=None):
    return h.call("POST", "/v1/runs/kill-switch", {"enabled": enabled},
                  token=token if token is not None else h.tokens["muse"])


def main():
    h = Harness("p7_28", PORT).start()
    try:
        h.clear_rates()
        job_a = h.make_job("legacy claim quest", tags=["host", "quest"])
        job_b = h.make_job("p7 action quest", tags=["host", "quest"])

        # Switch ON (muse only; a resident cannot flip it).
        s, b = set_switch(h, True, token=h.tokens["ember"])
        assert s == 403, (s, b)
        s, b = set_switch(h, True)
        assert s == 200 and b.get("enabled") is True, (s, b)
        print("  kill switch ON (muse); resident flip -> 403")

        # The legacy direct-claim route still works while it is on.
        s, b = h.call("POST", f"/v1/jobs/{job_a['id']}/claim",
                      {"resident_id": "nimbus",
                       "idempotency_key": "s9-legacy"},
                      token=h.tokens["nimbus"])
        assert s == 200, (s, b)
        print("  legacy direct claim while ON -> 200 (unaffected)")

        # A P7 run can still be created while it is on (creation
        # is not gated), but its /action is refused.
        s, run = h.create_run("ember", mode="live", idem="s9-1")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "claim_job", "job_id": job_b["id"],
                                  "idempotency_key": "s9-claim"},
                       "fencing_token": ft, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 403 and b.get("error") == "kill_switch_on", (s, b)
        print("  P7 /action while ON -> 403 kill_switch_on")

        # Switch OFF: the same run's action proceeds.
        s, b = set_switch(h, False)
        assert s == 200 and b.get("enabled") is False, (s, b)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "claim_job", "job_id": job_b["id"],
                                  "idempotency_key": "s9-claim"},
                       "fencing_token": ft, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 200 and b.get("outcome") == "executed", (s, b)
        print("  P7 /action after OFF -> 200 executed")
        print("P7-28 kill-switch scope: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
