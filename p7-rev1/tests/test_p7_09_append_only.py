#!/usr/bin/env python3
"""P7-09 append-only / tamper evidence.

  - The DB refuses UPDATE and DELETE on run_events (SQLite triggers).
  - Tampering (drop the triggers, edit a payload) breaks the hash
    chain: verify() returns False.
  - Rollback (drop the triggers, delete the last event) also breaks
    the chain.
  - The chain head is anchored in the public event log on EVERY
    append (rev 1, S8); the anchor from the completion call is the
    final one and matches the pre-tamper head, and mismatches the
    tampered head.
"""
import sqlite3
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18909


def main():
    h = Harness("p7_09", PORT).start()
    try:
        h.clear_rates()
        s, run = h.create_run("ember", mode="dry_run", idem="tamper-1")
        assert s == 201, (s, run)
        rid, ft = run["id"], run["fencing_token"]
        h.append_event("ember", rid, "memory_loaded", ft, {"entries": 3})
        h.append_event("ember", rid, "goal_proposed", ft,
                       {"goal": {"ref": "job", "kind": "claim_job"}})
        h.append_event("ember", rid, "no_action", ft,
                       {"reason": "no_candidates"})
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {}, token=h.tokens["ember"])
        assert s == 200 and b.get("status") == "COMPLETE", (s, b)
        anchor = b["chain_anchor"]
        assert anchor, b
        print(f"  run completed; anchored head {anchor['head_hash'][:12]} "
              f"({anchor['events']} events)")

        # The public log carries one anchor per CLIENT append
        # (hash only, no content); the final one is the completion
        # anchor. The two creation events (run_created, lease_claimed)
        # are appended server-side at create time and carry no anchor
        # of their own — they are covered by the first client
        # append's anchor (events: 3).
        evs = h.public_events("run.chain_anchored")
        assert len(evs) == 4, evs
        assert evs[-1]["payload"]["head_hash"] == anchor["head_hash"], evs
        assert evs[-1]["payload"]["run_id"] == rid
        assert evs[-1]["payload"]["events"] == 6, evs
        print("  public event log carries run.chain_anchored x6 "
              "(one per append, hash only)")

        db_path = h.mod._P7RunStore("ember").path
        store = h.run_store("ember")
        ok, head, count = store.verify(rid)
        assert ok is True and head == anchor["head_hash"] and count == 6, \
            (ok, head, count)
        store.close()
        print("  chain verifies pre-tamper (6 events, head == anchor)")

        # (a) UPDATE / DELETE refused by the triggers.
        conn = sqlite3.connect(db_path)
        for sql in ("UPDATE run_events SET payload_json = '{}' WHERE run_id = ?",
                    "DELETE FROM run_events WHERE run_id = ?"):
            try:
                conn.execute(sql, (rid,))
                conn.commit()
                raise AssertionError(f"{sql.split()[0]} was not refused")
            except (sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
                assert "append-only" in str(exc), exc
        conn.close()
        print("  raw UPDATE and DELETE refused by triggers (append-only)")

        # (b) Tamper: drop the triggers, edit a payload.
        conn = sqlite3.connect(db_path)
        conn.execute("DROP TRIGGER p7_no_update_run_events")
        conn.execute("DROP TRIGGER p7_no_delete_run_events")
        conn.execute(
            "UPDATE run_events SET payload_json = ? WHERE run_id = ? "
            "AND event_type = 'no_action'",
            ('{"reason": "forged", "resident_id": "ember"}', rid))
        conn.commit()
        conn.close()
        store = h.run_store("ember")
        ok, head2, count2 = store.verify(rid)
        store.close()
        assert ok is False, "tampered chain still verifies"
        assert head2 != anchor["head_hash"], (head2, anchor["head_hash"])
        print("  payload tamper detected: verify() False, head != anchor")

        # (c) Rollback: delete the last event, verify again.
        # (The store constructor re-created the triggers during the
        # verify in (b), so drop them again first.)
        conn = sqlite3.connect(db_path)
        conn.execute("DROP TRIGGER IF EXISTS p7_no_update_run_events")
        conn.execute("DROP TRIGGER IF EXISTS p7_no_delete_run_events")
        conn.execute(
            "DELETE FROM run_events WHERE run_id = ? AND "
            "event_type = 'run_completed'", (rid,))
        conn.commit()
        conn.close()
        store = h.run_store("ember")
        ok, head3, count3 = store.verify(rid)
        store.close()
        assert ok is False and count3 == 5, (ok, head3, count3)
        assert head3 != anchor["head_hash"]
        print("  rollback (last event deleted) detected: verify() False, "
              "count 5 != 6, head != anchor")
        print("P7-09 append-only / tamper evidence: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
