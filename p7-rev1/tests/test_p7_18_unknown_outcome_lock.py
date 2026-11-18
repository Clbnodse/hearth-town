#!/usr/bin/env python3
"""P7-18 UNKNOWN_OUTCOME lock cannot be bypassed (rev 1, S1).

Claude's audit showed the v1 lock was bypassable three ways with
only the resident's own token: (a) POST /expire -> 200, new run
201; (b) POST /block reason_code=manual -> BLOCKED, new run 201;
(c) POST /complete reconciled:true evidence:{"anything":1} -> 200,
new run 201. The contract says only a human or Muse may
reconcile, and the evidence must reference the action_result event
id. In rev 1 all three are 403 reconcile_requires_muse for the
resident, arbitrary evidence is 400 reconciliation_evidence_invalid
even for muse, and a muse complete with evidence naming the
action_started trace event reconciles the run to COMPLETE.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18918


def crash_run(h):
    """Build a genuine UNKNOWN_OUTCOME run: drive to
    ACTION_AUTHORIZED, write action_started straight to the trace
    (simulating the crash after the intent record), restart. The
    startup reconcile moves it to UNKNOWN_OUTCOME."""
    s, run = h.create_run("ember", mode="live", idem="s1-1")
    assert s == 201, (s, run)
    rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
    h.drive_to_authorized("ember", rid, ft, exec_token=et)
    store = h.run_store("ember")
    try:
        ev = store.append(rid, "action_started",
                          {"action_type": "claim_job"})
    finally:
        store.close()
    h.restart()
    s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                  token=h.tokens["ember"])
    assert s == 200 and b["status"] == "UNKNOWN_OUTCOME", (s, b)
    assert b["reason_code"] == "unknown_outcome", b
    return rid, ev["event_id"]


def main():
    h = Harness("p7_18", PORT).start()
    try:
        h.clear_rates()
        rid, started_id = crash_run(h)
        print("  crash run is UNKNOWN_OUTCOME after restart")

        # (a) the resident cannot expire its way out of the lock.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/expire",
                      {}, token=h.tokens["ember"])
        assert s == 403 and b.get("error") == "reconcile_requires_muse", (s, b)
        print("  (a) resident /expire -> 403 reconcile_requires_muse")
        # (b) the resident cannot block its way out either.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 403 and b.get("error") == "reconcile_requires_muse", (s, b)
        print("  (b) resident /block manual -> 403 reconcile_requires_muse")
        # (c) the resident cannot complete with arbitrary evidence.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {"reconciled": True, "evidence": {"anything": 1}},
                      token=h.tokens["ember"])
        assert s == 403 and b.get("error") == "reconcile_requires_muse", (s, b)
        print("  (c) resident /complete reconciled + arbitrary evidence "
              "-> 403 reconcile_requires_muse")
        # The lock holds: no new run while it is open.
        s, b = h.create_run("ember", mode="live", idem="s1-2")
        assert s == 409 and b.get("error") == "unknown_outcome_blocked", (s, b)
        print("  new run while locked -> 409 unknown_outcome_blocked")

        # Muse can read the run and its trace — the reads a
        # reconcile needs (the entry guard lets muse/owner through;
        # one resident still cannot read another's run, P7-08).
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                      token=h.tokens["muse"])
        assert s == 200 and b["status"] == "UNKNOWN_OUTCOME", (s, b)
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                      token=h.tokens["muse"])
        assert s == 200, (s, b)
        assert [e for e in b["events"]
                if e["event_id"] == started_id], b
        print("  muse can GET the run + events (reconcile is reachable)")

        # Even muse needs evidence that names a real trace event.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {"reconciled": True, "evidence": {"anything": 1}},
                      token=h.tokens["muse"])
        assert s == 400 and b.get("error") == "reconciliation_evidence_invalid", (s, b)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {"reconciled": True,
                       "evidence": {"action_started_event_id": "revt-does-not-exist"}},
                      token=h.tokens["muse"])
        assert s == 400 and b.get("error") == "reconciliation_evidence_invalid", (s, b)
        print("  muse /complete with arbitrary / unknown evidence -> 400")

        # Muse reconciles with evidence naming the action_started event.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {"reconciled": True,
                       "evidence": {"action_started_event_id": started_id,
                                    "outcome": "not_committed"}},
                      token=h.tokens["muse"])
        assert s == 200 and b.get("status") == "COMPLETE", (s, b)
        print("  muse /complete with the action_started event id "
              "-> 200 COMPLETE")

        # New runs are possible again.
        s, run2 = h.create_run("ember", mode="live", idem="s1-2")
        assert s == 201, (s, run2)
        print("  after reconcile, new run -> 201")
        print("P7-18 UNKNOWN_OUTCOME lock cannot be bypassed: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
