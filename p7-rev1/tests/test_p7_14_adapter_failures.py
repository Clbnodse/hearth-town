#!/usr/bin/env python3
"""P7-14 adapter failures.

Each of the four adapter failure modes — timeout, empty output,
oversized output, non-JSON output — must produce its explicit
reason code, BLOCK the run, and never claim or act. Verified both
at the spawn level (spawn_model_suggestion) and end-to-end through
the P7 loop (live mode, real server, real subprocess).
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

PORT = 18914

FAKE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fake_reasoning_suggest.py")


def spawn_with_fake(ctx, timeout_s=None):
    """Run spawn_model_suggestion against the test-only fake script."""
    old_script = bl.P7_SUGGEST_SCRIPT
    bl.P7_SUGGEST_SCRIPT = FAKE_SCRIPT
    try:
        return bl.spawn_model_suggestion(ctx, timeout_s=timeout_s)
    finally:
        bl.P7_SUGGEST_SCRIPT = old_script


def fake_suggestion(job_id):
    return {"chosen_job_id": job_id, "declined_job_id": None,
            "decline_reason": "",
            "ranking": [{"job_id": job_id, "score": 0.9,
                         "reason": "matches host tag"}],
            "goals": [{"text": "Claim the job", "ref": job_id}],
            "uncertainty": [],
            "evidence": {"wake_ids": [], "memory_seqs": [],
                         "job_ids": [job_id]},
            "confidence": 0.9, "alternatives": []}


def main():
    h = Harness("p7_14", PORT).start()
    try:
        h.clear_rates()
        # Spawn level: each failure mode maps to its reason code.
        # (Rev 1: the fake is the file side-channel, never env vars.)
        ctx = {"resident_id": "ember", "wake": [], "memory": [],
               "candidates": [], "lessons": []}
        h.set_fake_model(sleep=5)
        try:
            _s, code, _t, _l = spawn_with_fake(ctx, timeout_s=2)
            assert code == "timeout", code
            print("  spawn timeout (5s sleep, 2s budget) -> timeout")
        finally:
            h.clear_fake_model()
        h.set_fake_model(raw="")
        try:
            _s, code, _t, _l = spawn_with_fake(ctx)
            assert code == "empty", code
            print("  spawn empty stdout -> empty")
        finally:
            h.clear_fake_model()
        h.set_fake_model(raw="x" * 70000)
        try:
            _s, code, _t, _l = spawn_with_fake(ctx)
            assert code == "oversized", code
            print("  spawn 70000-byte stdout -> oversized")
        finally:
            h.clear_fake_model()
        h.set_fake_model(raw="not json at all {")
        try:
            _s, code, _t, _l = spawn_with_fake(ctx)
            assert code == "non-json", code
            print("  spawn non-JSON stdout -> non-json")
        finally:
            h.clear_fake_model()

        # End-to-end: each failure blocks the run, never claims.
        job = h.make_job("adapter failure quest", tags=["host", "quest"])
        cases = [
            ("timeout", {"sleep": 5}),
            ("empty", {"raw": ""}),
            ("oversized", {"raw": "x" * 70000}),
            ("non-json", {"raw": "not json at all {"}),
        ]
        for i, (code, fake) in enumerate(cases):
            h.clear_rates()
            h.set_fake_model(**fake)
            # The timeout case needs a short spawn budget: the loop
            # uses the module constant (120 s), so shrink it in
            # process for this case (rev 1: the env override is gone).
            old_timeout = bl.P7_MODEL_TIMEOUT_S
            old_script = bl.P7_SUGGEST_SCRIPT
            bl.P7_SUGGEST_SCRIPT = FAKE_SCRIPT
            if code == "timeout":
                bl.P7_MODEL_TIMEOUT_S = 2
            try:
                api = bl.Api(h.root, token=h.tokens["ember"], dry_run=False)
                rec = bl.run_once(api, f"p7-14-{code}", fh=None,
                                  no_reply=True, reason=True, p7=True)
            finally:
                bl.P7_MODEL_TIMEOUT_S = old_timeout
                bl.P7_SUGGEST_SCRIPT = old_script
                h.clear_fake_model()
            assert rec["decision"] == "noop", (code, rec)
            assert rec["reason"] == f"model adapter failed: {code}", rec
            assert rec["reasoning"]["reason_code"] == code, rec
            rid = rec["p7_run"]["id"]
            s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                          token=h.tokens["ember"])
            assert b["status"] == "BLOCKED", (code, b)
            assert b["reason_code"] == code, b
            s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                          token=h.tokens["ember"])
            rejected = [e for e in b["events"]
                        if e["event_type"] == "plan_rejected"]
            assert len(rejected) == 1, b
            assert rejected[0]["payload"]["reason_code"] == code, rejected
            assert not [c for c in api.calls if c[0] == "POST"
                        and c[1].endswith("/action")], api.calls
            s, b = h.call("GET", f"/public/jobs/{job['id']}")
            assert b.get("status") == "open" and not b.get("claimed_by"), b
            print(f"  loop {code}: noop + run BLOCKED({code}) + no claim")
        print("P7-14 adapter failures: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
