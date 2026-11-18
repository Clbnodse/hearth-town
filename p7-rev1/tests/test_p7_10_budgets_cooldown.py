#!/usr/bin/env python3
"""P7-10 budgets / cooldown (rev 1).

  - Cooldown: an action sets last_action_at; a new run with a
    cooldown longer than the elapsed time is refused (409
    cooldown_active). In rev 1 (S5) the request can only ask for
    MORE than the policy minimum, never less: cooldown_ms=0 does
    NOT clear the 60000 ms policy minimum — only muse/owner
    lowering the policy minimum does.
  - Budgets persist through a process restart (the counters live in
    game_api.json, not in memory).
  - Model-reported token counts are REFUSED (400
    event_payload_invalid), not merely ignored: only the executor's
    adapter-measured adapter_output_units is charged, and an
    over-cap report is clamped to the run's max_model_tokens and
    the remaining daily budget (R5, refined in testing).
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18910


def spend_of(h, resident="ember"):
    return h.read_db().get("spend", {}).get(resident, {})


def main():
    h = Harness("p7_10", PORT).start()
    try:
        h.clear_rates()
        # Rev 1 (S5): this test uses a noop action, so the policy
        # allowlist must include it. The cooldown minimum stays at
        # the 60000 ms default for the cooldown checks below.
        s, b = h.set_run_policy("ember",
                                {"allowlist": ["claim_job", "noop"]})
        assert s == 200, (s, b)
        job = h.make_job("budget quest", tags=["host", "quest"])

        # Run 1: live, one noop action with adapter_output_units=100.
        s, run = h.create_run("ember", mode="live", idem="bud-1")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "noop"}, "fencing_token": ft,
                       "adapter_output_units": 100},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 200, (s, b)
        sp = spend_of(h)
        assert sp.get("actions_today") == 1, sp
        assert sp.get("output_units_today") == 100, sp
        assert sp.get("last_action_at"), sp
        print("  after 1 action: actions_today=1 output_units_today=100")

        # A model-reported token count is REFUSED at the boundary.
        s, b = h.append_event("ember", rid, "evaluation_recorded", ft,
                              {"outcome": "executed", "adapter_output_units": 50,
                               "model_tokens": 999999}, exec_token=et)
        assert s == 400 and b.get("error") == "event_payload_invalid", (s, b)
        print("  event carrying model_tokens=999999 -> 400 "
              "(model counts refused, not trusted)")
        # The clean append charges only the executor-measured units.
        s, b = h.append_event("ember", rid, "evaluation_recorded", ft,
                              {"outcome": "executed", "adapter_output_units": 50},
                              exec_token=et)
        assert s == 201, (s, b)
        sp = spend_of(h)
        assert sp.get("output_units_today") == 150, sp
        print("  event with adapter_output_units=50 -> "
              "output_units_today 150")
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {}, token=h.tokens["ember"])
        assert s == 200, (s, b)

        # Cooldown: 60 s since the last action -> refused.
        s, b = h.create_run("ember", mode="live", idem="bud-2",
                            cooldown_ms=60000)
        assert s == 409 and b.get("error") == "cooldown_active", (s, b)
        print("  new run with cooldown_ms=60000 -> 409 cooldown_active")
        # Rev 1 (S5): cooldown_ms=0 does NOT clear the policy
        # minimum (60000) — the request can only narrow upward.
        s, b = h.create_run("ember", mode="live", idem="bud-2",
                            cooldown_ms=0)
        assert s == 409 and b.get("error") == "cooldown_active", (s, b)
        print("  same key with cooldown_ms=0 -> still 409 "
              "(policy minimum 60000 applies)")
        # Only muse/owner lowering the policy minimum clears it.
        s, b = h.set_run_policy("ember", {"min_cooldown_ms": 0})
        assert s == 200, (s, b)
        s, run2 = h.create_run("ember", mode="live", idem="bud-2",
                               cooldown_ms=0)
        assert s == 201, (s, run2)
        print("  policy minimum lowered to 0 -> same key, cooldown 0 -> 201")

        # Budgets persist through a process restart.
        before = spend_of(h)
        h.restart()
        after = spend_of(h)
        assert after == before, (before, after)
        print(f"  after restart: spend unchanged {after}")
        # And the restarted server still enforces the cooldown:
        # a request for MORE than the (now 0) minimum is honoured.
        s, b = h.call("POST", f"/v1/residents/ember/runs/{run2['id']}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200, (s, b)
        s, b = h.create_run("ember", mode="live", idem="bud-3",
                            cooldown_ms=60000)
        assert s == 409 and b.get("error") == "cooldown_active", (s, b)
        print("  after restart, cooldown still enforced (last_action_at "
              "survived the restart; a 60000 request still refuses)")
        print("P7-10 budgets / cooldown: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
