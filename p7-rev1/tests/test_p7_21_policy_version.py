#!/usr/bin/env python3
"""P7-21 policy_version + run caps are enforced (rev 1, S4).

In v1 policy_version did not exist in the code at all (PROPOSAL.md
§2 and TEST_MAPPING claimed it was required and enforced, but grep
found 0 hits): a run was created 201 without it, and max_steps /
max_wall_ms / max_model_tokens were documented but absent from the
run record. In rev 1 the version is required and must match, the
caps are validated and stored on the run record.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18921


def main():
    h = Harness("p7_21", PORT).start()
    try:
        h.clear_rates()
        # No policy_version at all -> 400.
        s, b = h.call("POST", "/v1/residents/ember/runs",
                      {"idempotency_key": "s4-none", "mode": "dry_run"},
                      token=h.tokens["ember"])
        assert s == 400 and b.get("error") == "policy_version_required", (s, b)
        print("  create without policy_version -> 400 policy_version_required")
        # A wrong version -> 400.
        s, b = h.call("POST", "/v1/residents/ember/runs",
                      {"idempotency_key": "s4-wrong", "mode": "dry_run",
                       "policy_version": "p7-policy-99"},
                      token=h.tokens["ember"])
        assert s == 400 and b.get("error") == "policy_version_mismatch", (s, b)
        print("  create with policy_version p7-policy-99 -> 400 "
              "policy_version_mismatch")
        # Out-of-range caps -> 400 (each bound separately).
        for field, bad in (("max_steps", 0), ("max_steps", 51),
                           ("max_wall_ms", 999), ("max_wall_ms", 900001),
                           ("max_model_tokens", -1),
                           ("max_model_tokens", 4001)):
            s, b = h.call("POST", "/v1/residents/ember/runs",
                          {"idempotency_key": "s4-bad-%s-%s" % (field, bad),
                           "mode": "dry_run", "policy_version": "p7-policy-1",
                           field: bad},
                          token=h.tokens["ember"])
            assert s == 400, (field, bad, s, b)
        print("  max_steps 0/51, max_wall_ms 999/900001, "
              "max_model_tokens -1/4001 -> 400")
        # A valid create stores the version and the caps on the record.
        s, run = h.call("POST", "/v1/residents/ember/runs",
                        {"idempotency_key": "s4-ok", "mode": "dry_run",
                         "policy_version": "p7-policy-1",
                         "max_steps": 7, "max_wall_ms": 60000,
                         "max_model_tokens": 500},
                        token=h.tokens["ember"])
        assert s == 201, (s, run)
        assert run["policy_version"] == "p7-policy-1", run
        assert run["max_steps"] == 7, run
        assert run["max_wall_ms"] == 60000, run
        assert run["max_model_tokens"] == 500, run
        print("  valid create -> record carries policy_version + caps")
        s, b = h.call("POST", f"/v1/residents/ember/runs/{run['id']}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200, (s, b)
        # Defaults when the caps are omitted.
        s, run = h.create_run("ember", mode="dry_run", idem="s4-defaults")
        assert s == 201, (s, run)
        assert run["policy_version"] == "p7-policy-1", run
        assert run["max_steps"] == 10, run
        assert run["max_wall_ms"] == 300000, run
        assert run["max_model_tokens"] == 2000, run
        print("  omitted caps -> defaults 10 / 300000 / 2000")
        print("P7-21 policy_version + run caps enforced: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
