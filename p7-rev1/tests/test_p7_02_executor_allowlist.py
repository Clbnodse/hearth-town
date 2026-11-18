#!/usr/bin/env python3
"""P7-02 executor allowlist enforcement.

The executor token is scoped to the run's allowlist. Bypass the
runner's client-side checks entirely (call the endpoint directly):
the SERVER must still refuse an action outside the allowlist, and it
must refuse an action attempted with the resident token instead of
the executor token, and with a forged executor token.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18902


def main():
    h = Harness("p7_02", PORT).start()
    try:
        h.clear_rates()
        # Rev 1 (S5): the test needs noop in the policy allowlist
        # (run 3 is noop-only) and no cooldown between its rapid
        # successive runs; the policy itself is the S5 control.
        s, b = h.set_run_policy("ember", {"min_cooldown_ms": 0,
                                          "allowlist": ["claim_job", "noop"]})
        assert s == 200, (s, b)
        job = h.make_job("allowlist quest", tags=["host", "quest"])
        job2 = h.make_job("allowlist quest two", tags=["host", "quest"])

        # Run 1: allowlist ["claim_job"], live mode.
        s, run = h.create_run("ember", mode="live", allowlist=["claim_job"],
                              idem="a1")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)

        # Allowed action with the executor token -> 200.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "claim_job", "job_id": job["id"],
                                  "idempotency_key": "a1-claim"},
                       "fencing_token": ft, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 200 and b.get("outcome") == "executed", (s, b)
        print("  allowed claim_job with executor token: 200 executed")
        # Finish run 1 (evaluation + complete) so run 2 can take the lease.
        s, b = h.append_event("ember", rid, "evaluation_recorded", ft,
                              {"outcome": "executed"}, exec_token=et)
        assert s == 201, (s, b)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {}, token=h.tokens["ember"])
        assert s == 200 and b.get("status") == "COMPLETE", (s, b)

        # Run 2: allowlist ["claim_job"] — try an unlisted capability.
        s, run2 = h.create_run("ember", mode="live",
                               allowlist=["claim_job"], idem="a2")
        assert s == 201, (s, run2)
        rid2, ft2, et2 = run2["id"], run2["fencing_token"], run2["executor_token"]
        h.drive_to_authorized("ember", rid2, ft2, exec_token=et2)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid2}/action",
                      {"action": {"type": "spend_credits", "amount": 5},
                       "fencing_token": ft2, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et2})
        assert s == 403 and b.get("error") == "action_not_in_allowlist", (s, b)
        print("  unlisted spend_credits with executor token: 403 action_not_in_allowlist")

        # "noop" is a real action type but NOT in this run's allowlist.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid2}/action",
                      {"action": {"type": "noop"},
                       "fencing_token": ft2, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et2})
        assert s == 403 and b.get("error") == "action_not_in_allowlist", (s, b)
        print("  noop outside this run's allowlist: 403 action_not_in_allowlist")

        # Resident token instead of the executor token -> 403.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid2}/action",
                      {"action": {"type": "claim_job", "job_id": job2["id"],
                                  "idempotency_key": "a2-claim"},
                       "fencing_token": ft2, "adapter_output_units": 0},
                      token=h.tokens["ember"])
        assert s == 403 and b.get("error") == "executor_token_required", (s, b)
        print("  claim_job with resident token only: 403 executor_token_required")

        # Forged executor token -> 403.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid2}/action",
                      {"action": {"type": "claim_job", "job_id": job2["id"],
                                  "idempotency_key": "a2-claim"},
                       "fencing_token": ft2, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": "forged-token-value"})
        assert s == 403 and b.get("error") == "executor_token_invalid", (s, b)
        print("  claim_job with forged executor token: 403 executor_token_invalid")

        # Run 3: allowlist ["noop"] — claim_job must be refused.
        s, run3 = h.create_run("ember", mode="live", allowlist=["noop"],
                               idem="a3")
        assert s == 409 and run3.get("error") == "lease_already_open", (s, run3)
        # (run 2 still holds the lease — complete it first, then retry)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid2}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200, (s, b)
        s, run3 = h.create_run("ember", mode="live", allowlist=["noop"],
                               idem="a3")
        assert s == 201, (s, run3)
        rid3, ft3, et3 = run3["id"], run3["fencing_token"], run3["executor_token"]
        h.drive_to_authorized("ember", rid3, ft3, exec_token=et3)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid3}/action",
                      {"action": {"type": "claim_job", "job_id": job2["id"],
                                  "idempotency_key": "a3-claim"},
                       "fencing_token": ft3, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et3})
        assert s == 403 and b.get("error") == "action_not_in_allowlist", (s, b)
        print("  claim_job under a noop-only allowlist: 403 action_not_in_allowlist")

        # The refused actions left no claim behind.
        s, b = h.call("GET", f"/public/jobs/{job2['id']}")
        assert b.get("status") == "open" and not b.get("claimed_by"), (s, b)
        print("P7-02 executor allowlist enforcement: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
