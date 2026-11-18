#!/usr/bin/env python3
"""P7-12 dry-run.

  - A run created without a mode defaults to dry_run.
  - /action in dry_run mode is refused (409 mode_dry_run).
  - In dry-run mode the P7 loop NEVER invokes the model adapter:
    the subprocess is not spawned (verified by recording the real
    spawn call), so no model client constructor can run anywhere —
    not merely stubbed. The plan is the deterministic pick, traced
    as source "deterministic", and no /action is attempted.
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

PORT = 18912


def main():
    h = Harness("p7_12", PORT).start()
    try:
        h.clear_rates()
        job = h.make_job("dry run quest", tags=["host", "quest"])

        # Default mode is dry_run.
        s, run = h.create_run("ember", idem="dr-1")
        assert s == 201, (s, run)
        assert run["mode"] == "dry_run", run
        print("  run created without mode -> dry_run (default)")
        rid, ft, et = run["id"], run["fencing_token"], run["executor_token"]
        h.drive_to_authorized("ember", rid, ft, exec_token=et)
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/action",
                      {"action": {"type": "claim_job", "job_id": job["id"],
                                  "idempotency_key": "dr-claim"},
                       "fencing_token": ft, "adapter_output_units": 0},
                      token=h.tokens["ember"],
                      extra_headers={"X-Run-Token": et})
        assert s == 409 and b.get("error") == "mode_dry_run", (s, b)
        print("  /action in dry_run mode -> 409 mode_dry_run")
        s, b = h.call("POST", f"/v1/residents/ember/runs/{rid}/block",
                      {"reason_code": "manual"}, token=h.tokens["ember"])
        assert s == 200, (s, b)

        # Dry-run loop: the model subprocess is never spawned.
        # (Rev 1: file side-channel + Popen recording.)
        h.set_fake_model(suggestion={
            "chosen_job_id": job["id"], "declined_job_id": None,
            "decline_reason": "",
            "ranking": [{"job_id": job["id"], "score": 0.9,
                         "reason": "matches host tag"}],
            "goals": [{"text": "Claim the job", "ref": job["id"]}],
            "uncertainty": [],
            "evidence": {"wake_ids": [], "memory_seqs": [],
                         "job_ids": [job["id"]]},
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
            rec = bl.run_once(api, "p7-12-dry", fh=None, no_reply=True,
                              reason=True, p7=True)
        finally:
            bl.subprocess.Popen = real_popen
            bl.P7_SUGGEST_SCRIPT = old_script
            h.clear_fake_model()
        assert spawn_calls == [], \
            f"model subprocess spawned in dry-run mode: {spawn_calls}"
        print("  dry-run loop: model subprocess never spawned "
              "(0 spawn calls)")
        assert rec["decision"] == "claim", rec
        assert rec["action"]["dry_run"] is True, rec
        assert rec["reasoning"]["called"] is False, rec
        assert not [c for c in api.calls if c[0] == "POST"
                    and c[1].endswith("/action")], api.calls
        print("  dry-run loop: decision claim (dry_run), no /action call")
        rid = rec["p7_run"]["id"]
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                      token=h.tokens["ember"])
        types = [e["event_type"] for e in b["events"]]
        assert "action_started" not in types, types
        plan = [e for e in b["events"]
                if e["event_type"] == "plan_proposed"][0]
        assert plan["payload"]["source"] == "deterministic", plan
        assert b["chain_ok"] is True
        s, b = h.call("GET", f"/public/jobs/{job['id']}")
        assert b.get("status") == "open" and not b.get("claimed_by"), b
        print("  dry-run trace: deterministic plan, no action_started, "
              "job still open")
        print("P7-12 dry-run: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
