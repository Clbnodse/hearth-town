#!/usr/bin/env python3
"""P7-26 canary at the model-input boundary (rev 1, R4).

In v1 the model context was {memory: entries, candidates:
candidates} — full memory entries and job briefs went to the
model. In rev 1 the executor builds a minimised context: wake
items shrink to wake_id + event_type, memory entries to seq +
type, candidates to id + title (titles are public board text;
briefs are excluded), lessons are already structured {key,
job_id} pairs. This test plants canaries in a memory entry's
content and in a job brief, runs a full live P7 cycle, and reads
the exact stdin payload the fake model received (the fake
captures it to a file before anything else): neither canary may
appear, and the captured context must carry only the allowed
fields. (Wake summaries are already redacted server-side — no
free text — so the wake leg is structural: no payload_summary
key reaches the model.)
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p7_harness import Harness, FAKE_CAPTURE_FILE

WORK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work")
sys.path.insert(0, WORK)
import bounded_loop as bl

PORT = 18926


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
    h = Harness("p7_26", PORT).start()
    try:
        h.clear_rates()
        canary_mem = "p7canary-r4-mem-" + hashlib.sha256(b"r4mem").hexdigest()[:12]
        canary_brief = "p7canary-r4-brief-" + hashlib.sha256(b"r4brief").hexdigest()[:12]
        # (a) canary in a memory entry's content.
        s, b = h.call("POST", "/v1/residents/ember/memory",
                      {"type": "note",
                       "content": f"remember the old quest {canary_mem}",
                       "confidence": 1.0}, token=h.tokens["ember"])
        assert s == 201, (s, b)
        # (b) canary in a job brief (custom brief, not the harness default).
        s, job = h.call("POST", "/v1/jobs",
                        {"title": "r4 boundary quest",
                         "brief": f"do the thing: {canary_brief}",
                         "reward_credits": 5, "max_claimants": 1,
                         "idempotency_key": "p7-26-job",
                         "job_tags": ["host", "quest"]},
                        token=h.tokens["muse"])
        assert s == 201, (s, job)
        # The seeds are real: the memory export and the job record
        # both contain their canary.
        s, exp = h.call("GET", "/v1/residents/ember/memory/export",
                        token=h.tokens["ember"])
        assert canary_mem in json.dumps(exp), "memory seed missing"
        s, jb = h.call("GET", f"/public/jobs/{job['id']}")
        assert canary_brief in json.dumps(jb), "brief seed missing"
        print("  seeds verified: memory content + job brief hold canaries")

        h.set_fake_model(suggestion=fake_suggestion(job["id"]))
        old_script = bl.P7_SUGGEST_SCRIPT
        bl.P7_SUGGEST_SCRIPT = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fake_reasoning_suggest.py")
        try:
            api = bl.Api(h.root, token=h.tokens["ember"], dry_run=False)
            rec = bl.run_once(api, "p7-26-run", fh=None, no_reply=True,
                              reason=True, p7=True)
            assert rec["decision"] == "claim", rec
            # The exact model input, as the fake received it. Read
            # here: clear_fake_model() below deletes the capture file.
            with open(FAKE_CAPTURE_FILE) as f:
                captured = json.load(f)
        finally:
            bl.P7_SUGGEST_SCRIPT = old_script
            h.clear_fake_model()
        blob = json.dumps(captured)
        for c in (canary_mem, canary_brief):
            assert c not in blob, f"canary {c} reached the model input"
        print("  neither canary appears in the captured model input")
        # Structure: only the allowed fields.
        assert set(captured) <= {"resident_id", "wake", "memory",
                                 "candidates", "lessons"}, captured.keys()
        for e in captured.get("memory", []):
            assert set(e) == {"seq", "type"}, e
        for c in captured.get("candidates", []):
            assert set(c) == {"id", "title"}, c
        for w in captured.get("wake", []):
            assert set(w) == {"wake_id", "event_type"}, w
        assert "brief" not in blob and "content" not in blob \
            and "payload_summary" not in blob, blob
        print("  captured context: memory {seq,type}, candidates "
              "{id,title}, wake {wake_id,event_type} — no brief, no "
              "content, no payload_summary")
        print("P7-26 canary at the model-input boundary: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
