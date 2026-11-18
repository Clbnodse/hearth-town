#!/usr/bin/env python3
"""P7-22 server-side run policy (rev 1, S5).

In v1 the limits were chosen by the party they limit:
cooldown_ms came from the request body (0 accepted), mode=live was
accepted from the resident token alone, and the allowlist was
caller-chosen. In rev 1 a per-resident policy record is held
server-side (min cooldown, live_enabled default false, allowlist)
and a run request can only narrow it: live needs the policy to
enable it, the effective cooldown is the policy minimum or the
request, whichever is greater, and the allowlist must be a subset
of the policy allowlist. Only muse/owner may set the policy.

Note the create-run check order (cooldown before live before
allowlist): the live gate is tested before any action sets
last_action_at, and the allowlist test clears the cooldown first,
so each assertion sees the error it names.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.abspath(__file__)))
from p7_harness import Harness

PORT = 18922


def main():
    h = Harness("p7_22", PORT).start()
    try:
        h.clear_rates()
        job = h.make_job("policy quest", tags=["host", "quest"])

        # Live mode without the policy enabling it -> 403.
        # (Tested before any action, so the cooldown cannot mask it.)
        s, b = h.set_run_policy("ember", {"live_enabled": False})
        assert s == 200, (s, b)
        s, b = h.create_run("ember", mode="live", idem="s5-live-off")
        assert s == 403 and b.get("error") == "live_not_enabled", (s, b)
        print("  live create with live_enabled=false -> 403 live_not_enabled")
        # Dry-run does not need the live flag.
        s, run = h.create_run("ember", mode="dry_run", idem="s5-dry-ok")
        assert s == 201, (s, run)
        print("  dry-run create with live disabled -> 201")
        s, b = h.call("POST", f"/v1/residents/ember/runs/{run['id']}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200, (s, b)

        # One real action, so last_action_at is set (cooldown test).
        s, b = h.set_run_policy("ember", {"live_enabled": True,
                                          "allowlist": ["claim_job", "noop"]})
        assert s == 200, (s, b)
        s, run = h.create_run("ember", mode="live", idem="s5-1")
        assert s == 201, (s, run)
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "noop"}, "fencing_token": ft,
                       "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 200, (s, b)
        s, b = h.append_event("ember", rid, "evaluation_recorded", ft,
                              {"outcome": "executed"}, exec_token=et)
        assert s == 201, (s, b)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/complete",
                      {}, token=h.tokens["ember"])
        assert s == 200, (s, b)
        print("  one noop action taken (last_action_at set)")

        # Cooldown: the request cannot go below the policy minimum.
        # (The policy minimum is still the 60000 ms default.)
        s, b = h.create_run("ember", mode="dry_run", idem="s5-cool",
                            cooldown_ms=0)
        assert s == 409 and b.get("error") == "cooldown_active", (s, b)
        print("  create with cooldown_ms=0, policy minimum 60000 "
              "-> 409 cooldown_active")

        # Allowlist: the request cannot exceed the policy allowlist.
        # (Clear the cooldown first — it is checked before allowlist.)
        s, b = h.set_run_policy("ember", {"min_cooldown_ms": 0,
                                          "allowlist": ["claim_job"]})
        assert s == 200, (s, b)
        s, b = h.create_run("ember", mode="dry_run", idem="s5-wide",
                            allowlist=["claim_job", "noop"])
        assert s == 400 and b.get("error") == "allowlist_exceeds_policy", (s, b)
        print("  allowlist wider than the policy -> 400 "
              "allowlist_exceeds_policy")

        # Only muse/owner may set the policy.
        s, b = h.set_run_policy("ember", {"live_enabled": True},
                                token=h.tokens["ember"])
        assert s == 403 and b.get("error") == "admin_only", (s, b)
        print("  resident setting its own policy -> 403 admin_only")
        s, b = h.set_run_policy("ember", {"live_enabled": True,
                                          "min_cooldown_ms": 0,
                                          "allowlist": ["claim_job"]})
        assert s == 200, (s, b)
        assert b["policy"]["live_enabled"] is True, b
        print("  muse setting the policy -> 200")

        # Live works again once the policy enables it.
        s, run = h.create_run("ember", mode="live", idem="s5-live-on")
        assert s == 201, (s, run)
        print("  live create with live_enabled=true -> 201")
        print("P7-22 server-side run policy: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
