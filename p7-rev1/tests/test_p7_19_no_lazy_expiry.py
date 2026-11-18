#!/usr/bin/env python3
"""P7-19 UNKNOWN_OUTCOME never lazily expires (rev 1, S2).

In v1 _p7_maybe_expire treated UNKNOWN_OUTCOME as expirable: after
the lease passed (<=1h) a plain GET set it EXPIRED and a new run
was 201 — the lock evaporated by itself. In rev 1 the lock holds
until a human or Muse reconciles it (P7-18), however stale the
lease is.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18919


def main():
    h = Harness("p7_19", PORT).start()
    try:
        h.clear_rates()
        s, run = h.create_run("ember", mode="live", idem="s2-1")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        store = h.run_store("ember")
        try:
            store.append(rid, "action_started",
                         {"action_type": "claim_job"})
        finally:
            store.close()
        h.restart()
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                      token=h.tokens["ember"])
        assert s == 200 and b["status"] == "UNKNOWN_OUTCOME", (s, b)
        print("  crash run is UNKNOWN_OUTCOME after restart")

        # Force the lease long past expiry (the lease is 600 s; the
        # test must not wait an hour).
        def lapse(data):
            data["runs"][rid]["lease_expires_at"] = "2020-01-01T00:00:00Z"
        h.patch_db(lapse)
        # A plain GET must NOT expire it.
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                      token=h.tokens["ember"])
        assert s == 200, (s, b)
        assert b["status"] == "UNKNOWN_OUTCOME", b
        print("  GET with a lapsed lease -> still UNKNOWN_OUTCOME")
        # And a new run is still refused: the lock did not evaporate.
        s, b = h.create_run("ember", mode="live", idem="s2-2")
        assert s == 409 and b.get("error") == "unknown_outcome_blocked", (s, b)
        print("  new run with a lapsed lease -> 409 unknown_outcome_blocked")
        # A second GET also leaves it stuck (no lazy expiry on read).
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                      token=h.tokens["ember"])
        assert b["status"] == "UNKNOWN_OUTCOME", b
        print("  second GET -> still UNKNOWN_OUTCOME (no lazy expiry)")
        print("P7-19 UNKNOWN_OUTCOME never lazily expires: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
