#!/usr/bin/env python3
"""P7-03 lease / idempotency.

  - The same idempotency key returns the same run (200), never a
    second run — and never re-issues the executor token (shown once).
  - A second open lease for the same resident is rejected (409).
  - Fencing tokens are monotonic per resident.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18903


def main():
    h = Harness("p7_03", PORT).start()
    try:
        h.clear_rates()
        s, run = h.create_run("ember", mode="dry_run", idem="k1")
        assert s == 201, (s, run)
        assert run.get("executor_token"), "token not issued at creation"
        assert run["fencing_token"] == 1, run
        rid = run["id"]
        print(f"  run A created: {rid} fencing=1")

        # Same key -> same run, 200, no token re-issue.
        s, again = h.create_run("ember", mode="dry_run", idem="k1")
        assert s == 200, (s, again)
        assert again["id"] == rid, (again["id"], rid)
        assert "executor_token" not in again, "token re-issued on replay"
        print("  same idempotency key -> same run (200), no token re-issue")

        # Second open lease -> 409.
        s, b = h.create_run("ember", mode="dry_run", idem="k2")
        assert s == 409 and b.get("error") == "lease_already_open", (s, b)
        assert b.get("run_id") == rid
        print("  second open lease -> 409 lease_already_open")

        # A different resident is unaffected (its own lease).
        s, run_n = h.create_run("nimbus", mode="dry_run", idem="k1")
        assert s == 201 and run_n["fencing_token"] == 1, (s, run_n)
        print("  nimbus has its own lease (fencing=1, independent)")

        # Complete run A -> a new lease is possible, fencing advances.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200 and b.get("status") == "BLOCKED", (s, b)
        s, run2 = h.create_run("ember", mode="dry_run", idem="k2")
        assert s == 201, (s, run2)
        assert run2["id"] != rid and run2["fencing_token"] == 2, run2
        print(f"  after BLOCKED, new lease: {run2['id']} fencing=2")

        # Replay of k2 returns run 2, still no token.
        s, again2 = h.create_run("ember", mode="dry_run", idem="k2")
        assert s == 200 and again2["id"] == run2["id"], (s, again2)
        assert "executor_token" not in again2
        print("  replay of k2 -> same run 2, no token re-issue")
        print("P7-03 lease / idempotency: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
