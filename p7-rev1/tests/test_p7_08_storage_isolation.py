#!/usr/bin/env python3
"""P7-08 storage isolation.

  - A raw per-resident store handle refuses cross-resident writes:
    an event payload naming another resident is rejected, and a
    run id from another resident has no rows in this resident's file.
  - The server takes resident_id from the LEASE, never the body: an
    event payload naming another resident is rejected by the
    per-event-type schema (rev 1, S7); a clean payload is stored
    under the lease's resident.
  - Another resident's token cannot append to this resident's run.
"""
import sqlite3
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18908


def main():
    h = Harness("p7_08", PORT).start()
    try:
        h.clear_rates()
        s, run_e = h.create_run("ember", mode="dry_run", idem="iso-e")
        assert s == 201, (s, run_e)
        s, run_n = h.create_run("nimbus", mode="dry_run", idem="iso-n")
        assert s == 201, (s, run_n)
        rid_e, ft_e = run_e["id"], run_e["fencing_token"]
        rid_n = run_n["id"]

        # (a) raw ember store: a payload naming nimbus is refused.
        store_e = h.run_store("ember")
        try:
            store_e.append(rid_e, "memory_loaded",
                           {"resident_id": "nimbus", "entries": 0})
            raise AssertionError("cross-resident payload was accepted")
        except Exception as exc:
            assert "does not match this store" in str(exc), exc
        print("  raw ember store refuses a nimbus payload")
        # A payload naming ember (or none) is stored under ember.
        ev = store_e.append(rid_e, "memory_loaded",
                            {"resident_id": "ember", "entries": 0})
        assert ev["payload"]["resident_id"] == "ember", ev
        ev2 = store_e.append(rid_e, "memory_loaded", {"entries": 1})
        assert ev2["payload"]["resident_id"] == "ember", ev2
        print("  raw ember store forces resident_id to the lease's resident")
        # (b) a nimbus run id has no rows in ember's file.
        assert store_e.list_events(rid_n) == [], "cross-resident rows visible"
        store_e.close()
        # (c) the two files are separate on disk.
        assert h.mod._P7RunStore("ember").path != \
            h.mod._P7RunStore("nimbus").path
        conn = sqlite3.connect(h.mod._P7RunStore("ember").path)
        rows = conn.execute(
            "SELECT COUNT(*) FROM run_events WHERE run_id = ?",
            (rid_n,)).fetchone()[0]
        conn.close()
        assert rows == 0, rows
        print("  nimbus run id has zero rows in ember's trace file")

        # (d) server (rev 1, S7): a payload naming another resident
        # is REJECTED by the event schema, not silently rewritten.
        # (The raw appends above did not move the server's run state,
        # so drive the state machine properly first.)
        s, b = h.append_event("ember", rid_e, "memory_loaded", ft_e,
                              {"entries": 0})
        assert s == 201, (s, b)
        s, b = h.append_event("ember", rid_e, "goal_proposed", ft_e,
                              {"resident_id": "nimbus",
                               "goal": {"ref": "job", "kind": "claim_job"}})
        assert s == 400 and b.get("error") == "event_payload_invalid", (s, b)
        print("  server rejects a payload naming nimbus: 400")
        s, b = h.append_event("ember", rid_e, "goal_proposed", ft_e,
                              {"goal": {"ref": "job", "kind": "claim_job"}})
        assert s == 201, (s, b)
        # The store forces resident_id into the STORED payload from
        # the lease (the schema only governs the input, where the
        # key is refused) — so it reads back as ember, never nimbus.
        assert b["event"]["payload"]["resident_id"] == "ember", b
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid_e}/events",
                      token=h.tokens["ember"])
        assert s == 200, (s, b)
        goals = [e for e in b["events"]
                 if e["event_type"] == "goal_proposed"]
        assert len(goals) == 1, b
        assert goals[0]["payload"]["goal"] == {"ref": "job",
                                               "kind": "claim_job"}, goals
        print("  server stores the clean event under the lease's resident")

        # (e) nimbus's token cannot append to ember's run.
        s, b = h.append_event("ember", rid_e, "goal_accepted", ft_e,
                              {"goal": {"ref": "job"}},
                              token=h.tokens["nimbus"])
        assert s == 403 and b.get("error") == "token_not_bound_to_resident", (s, b)
        print("  nimbus token cannot append to ember's run: 403")

        # (f) nimbus cannot even read ember's run.
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid_e}",
                      token=h.tokens["nimbus"])
        assert s == 403, (s, b)
        print("  nimbus token cannot read ember's run: 403")
        print("P7-08 storage isolation: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
