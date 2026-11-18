#!/usr/bin/env python3
"""P7-23 crash reconcile at startup (rev 1, S6).

In v1 SQLite committed per append but game_api.json was saved
once at the end, so a process death after the append and before
the JSON save left the persisted run in ACTION_AUTHORIZED with a
trace holding action_started + action_result — and after restart
the executor could run the action again (double action, spend
never charged for the first). In rev 1 the intent record
(action_started + adapter charge) is saved BEFORE the claim
executes, and startup reconciles any run left in
ACTION_AUTHORIZED / ACTION_STARTED from its trace:
  (a) action_started, no action_result -> UNKNOWN_OUTCOME
      (the claim may or may not have committed);
  (b) action_result committed -> ACTION_EXECUTED (honoured);
  (c) action_result refused -> BLOCKED / action_rejected.
The simulation appends straight to the trace (the v1 crash
shape); the fixed code's intent-save is what makes the spend
side correct, and the reconcile resolves the status from the
trace either way.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18923


def crash_case(h, name, idem, result_payload):
    """Drive a run to ACTION_AUTHORIZED, write the trace events a
    crash would leave behind, restart, and return the run."""
    s, run = h.create_run("ember", mode="live", idem=idem)
    assert s == 201, (s, run)
    rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
    h.drive_to_authorized("ember", rid, ft, exec_token=et)
    store = h.run_store("ember")
    try:
        store.append(rid, "action_started",
                     {"action_type": "claim_job"})
        if result_payload is not None:
            store.append(rid, "action_result", result_payload)
    finally:
        store.close()
    h.restart()
    s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                  token=h.tokens["ember"])
    assert s == 200, (s, b)
    return b


def main():
    # (a) action_started, no result -> UNKNOWN_OUTCOME.
    h = Harness("p7_23a", PORT).start()
    try:
        h.clear_rates()
        b = crash_case(h, "a", "s6-a", None)
        assert b["status"] == "UNKNOWN_OUTCOME", b
        assert b["reason_code"] == "unknown_outcome", b
        print("  (a) started, no result -> UNKNOWN_OUTCOME")
    finally:
        h.stop()
    # (b) stored committed result -> ACTION_EXECUTED.
    h = Harness("p7_23b", PORT + 1).start()
    try:
        h.clear_rates()
        b = crash_case(h, "b", "s6-b",
                       {"committed": True, "outcome": "executed"})
        assert b["status"] == "ACTION_EXECUTED", b
        print("  (b) stored committed result -> ACTION_EXECUTED")
    finally:
        h.stop()
    # (c) stored refused result -> BLOCKED / action_rejected.
    h = Harness("p7_23c", PORT + 2).start()
    try:
        h.clear_rates()
        b = crash_case(h, "c", "s6-c",
                       {"committed": False, "outcome": "rejected"})
        assert b["status"] == "BLOCKED", b
        assert b["reason_code"] == "action_rejected", b
        print("  (c) stored refused result -> BLOCKED/action_rejected")
    finally:
        h.stop()
    print("P7-23 crash reconcile at startup: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
