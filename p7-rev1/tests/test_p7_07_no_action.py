#!/usr/bin/env python3
"""P7-07 NO_ACTION.

A P7 loop with no candidate writes an explicit terminal NO_ACTION
trace and does NOT claim, does NOT call the model adapter, and
spends nothing (no action, no adapter output units).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p7_harness import Harness

WORK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work")
sys.path.insert(0, WORK)
import bounded_loop as bl

PORT = 18907


def main():
    h = Harness("p7_07", PORT).start()
    try:
        h.clear_rates()
        # No jobs at all: the loop has no candidate. The fake is
        # set defensively (rev 1: file side-channel + monkeypatched
        # script); the recording wrapper proves Popen is never called.
        h.set_fake_model(suggestion={
            "chosen_job_id": None, "declined_job_id": None,
            "decline_reason": "", "ranking": [], "goals": [],
            "uncertainty": [], "evidence": {"wake_ids": [],
                                            "memory_seqs": [],
                                            "job_ids": []},
            "confidence": 0.9, "alternatives": []})
        spawn_calls = []
        real_popen = bl.subprocess.Popen

        def recording_popen(*args, **kwargs):
            spawn_calls.append(args)
            return real_popen(*args, **kwargs)

        old_script = bl.P7_SUGGEST_SCRIPT
        bl.P7_SUGGEST_SCRIPT = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fake_reasoning_suggest.py")
        bl.subprocess.Popen = recording_popen
        try:
            api = bl.Api(h.root, token=h.tokens["ember"], dry_run=True)
            rec = bl.run_once(api, "p7-07-run", fh=None, no_reply=True,
                              reason=True, p7=True)
        finally:
            bl.subprocess.Popen = real_popen
            bl.P7_SUGGEST_SCRIPT = old_script
            h.clear_fake_model()
        assert rec["decision"] == "noop", rec
        assert "NO_ACTION" in rec["reason"], rec
        assert spawn_calls == [], "model adapter was called on a NO_ACTION run"
        assert rec.get("p7_run"), rec
        rid = rec["p7_run"]["id"]
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                      token=h.tokens["ember"])
        assert s == 200, (s, b)
        types = [e["event_type"] for e in b["events"]]
        assert types == ["run_created", "lease_claimed", "memory_loaded",
                         "goal_proposed", "no_action", "run_completed"], types
        assert b["chain_ok"] is True
        no_action = [e for e in b["events"]
                     if e["event_type"] == "no_action"][0]
        assert no_action["payload"]["reason"] == "no_candidates"
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                      token=h.tokens["ember"])
        assert b["status"] == "COMPLETE", b
        # No claim, no adapter call, no action spend.
        assert not [c for c in api.calls if c[0] == "POST"
                    and c[1].endswith("/action")], api.calls
        spend = h.read_db().get("spend", {}).get("ember", {})
        assert spend.get("actions_today", 0) == 0, spend
        assert spend.get("output_units_today", 0) == 0, spend
        print("P7-07 NO_ACTION: PASS (explicit terminal trace, no claim, "
              "no adapter call, no spend)")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
