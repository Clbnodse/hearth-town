#!/usr/bin/env python3
"""P7-13 privacy canaries.

Seed canary strings in (a) a memory entry, (b) the model prompt
(the fake model's goal text echoes a canary), (c) a fake credential
value stored in a memory entry. Run a full live P7 cycle, then scan
the run trace, the public event log, the run log, and the decision
record: no canary may appear anywhere outside ember's private
memory namespace. (The canary IS present in the memory export —
that is the seed location, private by design — which proves the
scan would have caught a leak.)
"""
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p7_harness import Harness

WORK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work")
sys.path.insert(0, WORK)
import bounded_loop as bl

PORT = 18913


def main():
    h = Harness("p7_13", PORT).start()
    try:
        h.clear_rates()
        canary_mem = "p7canary-mem-" + hashlib.sha256(b"mem").hexdigest()[:12]
        canary_prompt = "p7canary-prompt-" + hashlib.sha256(b"prompt").hexdigest()[:12]
        canary_cred = "p7canary-cred-" + hashlib.sha256(b"cred").hexdigest()[:12]
        job = h.make_job("canary quest", tags=["host", "quest"])
        # (a) + (c) seed canaries in ember's private memory.
        for content in (
                f"note: remember the old quest {canary_mem}",
                f"note: backup credential {canary_cred} (throwaway test value)"):
            s, b = h.call("POST", "/v1/residents/ember/memory",
                          {"type": "note", "content": content,
                           "confidence": 1.0}, token=h.tokens["ember"])
            assert s == 201, (s, b)
        # (b) the fake model's goal text echoes a canary. Rev 1:
        # the goal text never reaches the trace (goal_proposed is
        # ref/kind only) or the decision record (no suggestion text),
        # so this canary must not appear anywhere below.
        h.set_fake_model(suggestion={
            "chosen_job_id": job["id"], "declined_job_id": None,
            "decline_reason": "",
            "ranking": [{"job_id": job["id"], "score": 0.9,
                         "reason": "matches host tag"}],
            "goals": [{"text": f"Claim the job {canary_prompt}",
                       "ref": job["id"]}],
            "uncertainty": [],
            "evidence": {"wake_ids": [], "memory_seqs": [],
                         "job_ids": [job["id"]]},
            "confidence": 0.9, "alternatives": []})
        old_script = bl.P7_SUGGEST_SCRIPT
        bl.P7_SUGGEST_SCRIPT = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fake_reasoning_suggest.py")
        log_buf = io.StringIO()
        try:
            api = bl.Api(h.root, token=h.tokens["ember"], dry_run=False)
            rec = bl.run_once(api, "p7-13-run", fh=log_buf, no_reply=True,
                              reason=True, p7=True)
        finally:
            bl.P7_SUGGEST_SCRIPT = old_script
            h.clear_fake_model()
        assert rec["decision"] == "claim", rec
        rid = rec["p7_run"]["id"]
        canaries = [canary_mem, canary_prompt, canary_cred]
        # The seed is real: the memory export contains the canaries.
        s, exp = h.call("GET", "/v1/residents/ember/memory/export",
                        token=h.tokens["ember"])
        assert s == 200, (s, exp)
        exp_blob = json.dumps(exp)
        for c in (canary_mem, canary_cred):
            assert c in exp_blob, f"seed {c} missing from export"
        # Scan everything that leaves the private namespace.
        s, trace = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                          token=h.tokens["ember"])
        assert s == 200, (s, trace)
        trace_blob = json.dumps(trace)
        pub_blob = json.dumps(h.public_events())
        run_log = log_buf.getvalue()
        rec_blob = json.dumps(rec)
        api_blob = json.dumps(api.calls)
        for name, blob in (("run trace", trace_blob),
                           ("public event log", pub_blob),
                           ("run log", run_log),
                           ("decision record", rec_blob),
                           ("api call log", api_blob)):
            for c in canaries:
                assert c not in blob, f"canary {c} leaked into {name}"
        print("  canaries in memory export (seed, private): yes")
        print("  canaries in run trace / public log / run log / "
              "decision record / call log: none")
        print("P7-13 privacy canaries: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
