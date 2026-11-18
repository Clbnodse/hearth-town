#!/usr/bin/env python3
"""P7-24 event payload schemas (rev 1, S7).

In v1 payloads were free-form JSON up to 64 KB and were returned
by GET events: a planted canary string in memory_loaded came back
in the events list, so "structured lessons only" and the canary
rule were NOT enforced at the server boundary. In rev 1 every
event type has a schema (known keys, id-shaped strings, bounded
ints, bools, nested objects): unknown keys and free text are
400 event_payload_invalid, and the server derives the evaluation
from the stored action_result instead of trusting the client's
claim (a live evaluation with no committed action_result is
409 evaluation_mismatch; a dry-run evaluation needs none).
"""
import hashlib
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18924


def main():
    h = Harness("p7_24", PORT).start()
    try:
        h.clear_rates()
        canary = "p7canary-s7-" + hashlib.sha256(b"s7").hexdigest()[:12]
        s, run = h.create_run("ember", mode="dry_run", idem="s7-1")
        assert s == 201, (s, run)
        rid, ft = run["id"], run["fencing_token"]

        # Unknown key / free text in memory_loaded -> 400.
        s, b = h.append_event("ember", rid, "memory_loaded", ft,
                              {"entries": 0, "note": "free text " + canary})
        assert s == 400 and b.get("error") == "event_payload_invalid", (s, b)
        print("  memory_loaded with an unknown free-text key -> 400")
        s, b = h.append_event("ember", rid, "memory_loaded", ft,
                              {"entries": 0})
        assert s == 201, (s, b)

        # Free-text goal ref (spaces, punctuation) -> 400 (id shape).
        s, b = h.append_event("ember", rid, "goal_proposed", ft,
                              {"goal": {"ref": "not an id with spaces!",
                                       "kind": "claim_job"}})
        assert s == 400 and b.get("error") == "event_payload_invalid", (s, b)
        print("  goal_proposed with a free-text ref -> 400")
        s, b = h.append_event("ember", rid, "goal_proposed", ft,
                              {"goal": {"ref": "job", "kind": "claim_job"}})
        assert s == 201, (s, b)
        # Drive the rest of the way to ACTION_AUTHORIZED.
        for et, payload in (
                ("goal_accepted", {"goal": {"ref": "job"}}),
                ("plan_proposed", {"plan": {"action": {"type": "claim_job"}}}),
                ("plan_accepted", {"plan": {"action": {"type": "claim_job"}}}),
                ("action_authorized", {"action": {"type": "claim_job"}})):
            s, b = h.append_event("ember", rid, et, ft, payload)
            assert s == 201, (et, s, b)

        # Live evaluation with no action_result recorded -> 409.
        s, b = h.append_event("ember", rid, "evaluation_recorded", ft,
                              {"outcome": "executed"})
        assert s == 409 and b.get("error") == "evaluation_mismatch", (s, b)
        print("  live evaluation with no action_result -> 409 "
              "evaluation_mismatch")
        # A dry-run evaluation needs no action_result.
        s, b = h.append_event("ember", rid, "evaluation_recorded", ft,
                              {"dry_run": True, "outcome": "executed"})
        assert s == 201, (s, b)
        print("  dry-run evaluation -> 201 (no action_result needed)")

        # The rejected canary never entered the trace.
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                      token=h.tokens["ember"])
        assert s == 200, (s, b)
        assert canary not in json.dumps(b), "rejected canary is in the trace"
        print("  rejected canary is absent from GET events")
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {}, token=h.tokens["ember"])
        assert s == 200 and b.get("status") == "COMPLETE", (s, b)
        print("P7-24 event payload schemas: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
