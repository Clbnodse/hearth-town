#!/usr/bin/env python3
"""P7-06 known refusal is BLOCKED, not UNKNOWN_OUTCOME (rev 1).

Revision 1 (Claude audit S3): a claim the server refuses with a
definite answer (here: the job is already claimed by another agent,
409 from the claim core) is a KNOWN refusal. The run is BLOCKED
with reason_code action_rejected — it is not stuck, no human
reconcile is needed, and a new run may start immediately. Only an
exception (no result at all) leaves a run UNKNOWN_OUTCOME; that
case is P7-18 / P7-23.

Checks:
  - refused claim after action_started -> 409 action_not_committed,
    run BLOCKED, outcome "rejected";
  - a new run starts immediately (no unknown_outcome_blocked);
  - the adapter output units were still charged (the model ran);
  - the trace holds action_started + action_result (committed False).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p7_harness import Harness

WORK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work")
sys.path.insert(0, WORK)
import bounded_loop as bl

PORT = 18906


def main():
    h = Harness("p7_06", PORT).start()
    try:
        h.clear_rates()
        job = h.make_job("unknown outcome quest", tags=["host", "quest"])
        # Claim it directly first, so the run's claim is refused.
        s, b = h.call("POST", f"/v1/jobs/{job['id']}/claim",
                      {"resident_id": "nimbus",
                       "idempotency_key": "p7-06-direct"},
                      token=h.tokens["nimbus"])
        assert s == 200, (s, b)

        s, run = h.create_run("ember", mode="live", idem="uo-1")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        # The claim is refused (job fully claimed) AFTER action_started.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "claim_job", "job_id": job["id"],
                                  "idempotency_key": "uo-claim"},
                       "fencing_token": ft, "adapter_output_units": 7},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 409 and b.get("error") == "action_not_committed", (s, b)
        assert b["run"]["status"] == "BLOCKED", b
        assert b["run"]["reason_code"] == "action_rejected", b
        assert b["outcome"] == "rejected"
        assert b["run"]["adapter_output_units_used"] == 7, b
        print("  refused action after action_started -> BLOCKED/action_rejected")

        # The trace records both the intent and the known refusal.
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                      token=h.tokens["ember"])
        assert s == 200, (s, b)
        types = [e["event_type"] for e in b["events"]]
        assert "action_started" in types and "action_result" in types, types
        result = [e for e in b["events"]
                  if e["event_type"] == "action_result"][0]
        assert result["payload"]["committed"] is False, result
        assert result["payload"]["outcome"] == "rejected", result
        assert b["chain_ok"] is True
        print("  trace holds action_started + action_result (not committed)")

        # No lock: a new run starts immediately.
        s, run2 = h.create_run("ember", mode="live", idem="uo-2")
        assert s == 201, (s, run2)
        print("  new run after a known refusal -> 201 (no lock)")

        # The adapter units were charged at intent time (the model ran),
        # even though the claim was refused.
        spend = h.read_db().get("spend", {}).get("ember", {})
        assert spend.get("output_units_today", 0) == 7, spend
        assert spend.get("actions_today", 0) == 0, spend
        print("  adapter output units charged (7), no action charged")
        print("P7-06 known refusal is BLOCKED: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
