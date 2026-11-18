#!/usr/bin/env python3
"""P7-30 idempotency body mismatch (Claude re-review msg-2ef3cacc,
minor 2).

In rev 1 replaying a run-creation idempotency key with a different
body returned the original run with 200 — a silent success that hid
the mismatch (Claude's example: mode=live vs dry_run). The server
now fingerprints the run-defining request fields (mode, allowlist,
policy_version, max_steps, max_wall_ms, max_model_tokens,
lease_seconds) at creation; a replay with a different fingerprint is
409 idempotency_body_mismatch, while a replay with the same body
still returns the same run (200, no token re-issue).
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18930


def main():
    h = Harness("p7_30", PORT).start()
    try:
        h.clear_rates()
        s, run = h.create_run("ember", mode="dry_run", idem="m2-1")
        assert s == 201, (s, run)
        rid = run["id"]
        assert run.get("executor_token"), "token not issued at creation"
        print(f"  run created: {rid} mode=dry_run")

        # Same key, same body -> same run, 200, no token re-issue.
        s, again = h.create_run("ember", mode="dry_run", idem="m2-1")
        assert s == 200 and again["id"] == rid, (s, again)
        assert "executor_token" not in again, "token re-issued on replay"
        print("  same key, same body -> same run (200), no token re-issue")

        # Same key, mode live -> 409 (not a silent 200, and not the
        # live gate: the replay check runs first).
        s, b = h.create_run("ember", mode="live", idem="m2-1")
        assert s == 409 and b.get("error") == "idempotency_body_mismatch", (s, b)
        print("  same key, mode live -> 409 idempotency_body_mismatch")

        # Same key, different allowlist -> 409.
        s, b = h.create_run("ember", mode="dry_run", allowlist=["noop"],
                            idem="m2-1")
        assert s == 409 and b.get("error") == "idempotency_body_mismatch", (s, b)
        print("  same key, allowlist [noop] -> 409 "
              "idempotency_body_mismatch")

        # Same key, different max_steps -> 409.
        s, b = h.call("POST", "/v1/residents/ember/runs",
                      {"idempotency_key": "m2-1", "mode": "dry_run",
                       "policy_version": "p7-policy-1", "max_steps": 5},
                      token=h.tokens["ember"])
        assert s == 409 and b.get("error") == "idempotency_body_mismatch", (s, b)
        print("  same key, max_steps 5 -> 409 idempotency_body_mismatch")

        # The original run is untouched by the mismatched replays.
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                      token=h.tokens["ember"])
        assert s == 200 and b.get("mode") == "dry_run", (s, b)
        assert b.get("max_steps") == 10, b
        print("  original run untouched (mode dry_run, max_steps 10)")

        # Block the run; a FRESH key with mode live still hits the
        # live gate (403) — for nimbus, whose policy the harness
        # leaves at the default live_enabled=False (ember has live
        # enabled by the harness, so it cannot prove the gate).
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200 and b.get("status") == "BLOCKED", (s, b)
        s, b = h.create_run("nimbus", mode="live", idem="m2-2")
        assert s == 403 and b.get("error") == "live_not_enabled", (s, b)
        print("  fresh key, mode live (nimbus) -> 403 live_not_enabled "
              "(live gate intact)")
        print("P7-30 idempotency body mismatch: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
