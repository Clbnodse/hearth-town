#!/usr/bin/env python3
"""P7-20 known refusals are BLOCKED, not UNKNOWN_OUTCOME (rev 1, S3).

P7-06 covers the fully-claimed job. This test covers two more
definite answers from the claim core: (1) the job does not exist
(404), and (2) the resident already claimed the job itself (409).
Both are KNOWN refusals: the run is BLOCKED with reason_code
action_rejected, the trace records the refusal, and a new run may
start immediately — no human reconcile, no lock. Only an
exception (no result at all) is UNKNOWN_OUTCOME (P7-18 / P7-23).
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18920


def refused_claim(h, job_id, idem_key, expect_status):
    s, run = h.create_run("ember", mode="live", idem=idem_key)
    assert s == 201, (s, run)
    rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
    h.drive_to_authorized("ember", rid, ft, exec_token=et)
    s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                  {"action": {"type": "claim_job", "job_id": job_id,
                              "idempotency_key": idem_key + "-claim"},
                   "fencing_token": ft, "adapter_output_units": 0},
                  token=h.tokens["ember"],
                  extra_headers={"X-Run-Token": et})
    # The action returns the claim core's own status (404 for a
    # missing job, 409 for a refusal) with action_not_committed.
    assert s == expect_status and b.get("error") == "action_not_committed", (s, b)
    assert b["run"]["status"] == "BLOCKED", b
    assert b["run"]["reason_code"] == "action_rejected", b
    assert b["outcome"] == "rejected"
    s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                  token=h.tokens["ember"])
    assert s == 200, (s, b)
    result = [e for e in b["events"]
              if e["event_type"] == "action_result"][0]
    assert result["payload"]["committed"] is False, result
    return rid


def main():
    h = Harness("p7_20", PORT).start()
    try:
        h.clear_rates()
        # (1) The job does not exist: the claim core answers 404.
        rid = refused_claim(h, "job-does-not-exist", "s3-404", 404)
        print("  claim of a missing job -> BLOCKED/action_rejected")
        s, run2 = h.create_run("ember", mode="live", idem="s3-404-next")
        assert s == 201, (s, run2)
        print("  new run immediately after -> 201 (no lock)")
        s, b = h.call("POST",
                      f"/v1/residents/ember/runs/{run2['id']}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200, (s, b)

        # (2) The resident already claimed the job itself: 409.
        job = h.make_job("already claimed quest", tags=["host", "quest"])
        s, b = h.call("POST", f"/v1/jobs/{job['id']}/claim",
                      {"resident_id": "ember",
                       "idempotency_key": "s3-self-claim"},
                      token=h.tokens["ember"])
        assert s == 200, (s, b)
        rid = refused_claim(h, job["id"], "s3-self", 409)
        print("  claim of a job ember already claimed -> "
              "BLOCKED/action_rejected")
        s, run3 = h.create_run("ember", mode="live", idem="s3-self-next")
        assert s == 201, (s, run3)
        print("  new run immediately after -> 201 (no lock)")
        print("P7-20 known refusals are BLOCKED: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
