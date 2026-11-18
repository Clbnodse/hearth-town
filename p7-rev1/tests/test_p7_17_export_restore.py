#!/usr/bin/env python3
"""P7-17 export / restore (extra test, ChatGPT contract test 10).

Run a full live P7 cycle, export ember's memory + run record + run
trace + public anchor, restore them into a FRESH server (new stage
dir, new fixture), then verify: the restored run reads back
COMPLETE, its trace chain still verifies, the head matches the
exported anchor, and nimbus cannot read ember's restored export
(isolation survives the restore).
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

PORT = 18917


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
    h = Harness("p7_17", PORT).start()
    try:
        h.clear_rates()
        job = h.make_job("export quest", tags=["host", "quest"])
        h.set_fake_model(suggestion=fake_suggestion(job["id"]))
        old_script = bl.P7_SUGGEST_SCRIPT
        bl.P7_SUGGEST_SCRIPT = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fake_reasoning_suggest.py")
        try:
            api = bl.Api(h.root, token=h.tokens["ember"], dry_run=False)
            rec = bl.run_once(api, "p7-17-run", fh=None, no_reply=True,
                              reason=True, p7=True)
        finally:
            bl.P7_SUGGEST_SCRIPT = old_script
            h.clear_fake_model()
        assert rec["decision"] == "claim", rec
        rid = rec["p7_run"]["id"]
        s, final_run = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                              token=h.tokens["ember"])
        assert s == 200 and final_run["status"] == "COMPLETE", (s, final_run)
        s, exp_mem = h.call("GET", "/v1/residents/ember/memory/export",
                            token=h.tokens["ember"])
        assert s == 200, (s, exp_mem)
        s, trace = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                          token=h.tokens["ember"])
        assert s == 200 and trace["chain_ok"], (s, trace)
        # Rev 1 (S8): one anchor per append; the export carries the
        # FINAL anchor (head == trace head).
        anchors = [e for e in h.public_events()
                   if e.get("type") == "run.chain_anchored"
                   and e.get("payload", {}).get("run_id") == rid]
        final = [a for a in anchors
                 if a["payload"]["head_hash"] == trace["head_hash"]]
        assert len(final) == 1, final
        export = {
            "run_id": rid,
            "run": final_run,
            "trace": trace,
            "memory": exp_mem,
            "anchor": final[0]["payload"],
        }
        print(f"  exported run {rid}: {trace['count']} events, "
              f"head {trace['head_hash'][:16]}..., "
              f"{len(exp_mem.get('entries', []))} memory entries")
        # Copy the per-resident run DB BEFORE stopping the harness
        # (stop() deletes the stage dir).
        import shutil
        saved_db = "/tmp/p7_17_runs_ember.db"
        shutil.copyfile(os.path.join(h.stage, "runs_ember.db"), saved_db)
    finally:
        h.stop()

    # Restore into a fresh server: copy the saved run DB file and the
    # run record + memory into the new fixture.
    h2 = Harness("p7_17_restore", PORT + 1)
    import shutil
    dst_db = os.path.join(h2.stage, "runs_ember.db")
    h2.start()
    shutil.copyfile(saved_db, dst_db)
    try:
        h2.clear_rates()
        s, b = h2.call("GET", f"/v1/residents/ember/runs/{export['run_id']}",
                       token=h2.tokens["ember"])
        assert s == 404, (s, b)  # run record lives in game_api.json, not the DB
        # Restore the run record + memory via the fixture (patch_db).
        def restore(data):
            data["runs"][export["run_id"]] = export["run"]
            data["memory"]["ember"] = export["memory"]["entries"]
        h2.patch_db(restore)
        s, b = h2.call("GET", f"/v1/residents/ember/runs/{export['run_id']}",
                       token=h2.tokens["ember"])
        assert s == 200, (s, b)
        assert b["status"] == "COMPLETE", b
        s, trace2 = h2.call("GET", f"/v1/residents/ember/runs/{export['run_id']}/events",
                            token=h2.tokens["ember"])
        assert s == 200 and trace2["chain_ok"], (s, trace2)
        assert trace2["head_hash"] == export["trace"]["head_hash"], trace2
        assert trace2["head_hash"] == export["anchor"]["head_hash"], trace2
        assert trace2["count"] == export["trace"]["count"], trace2
        # Isolation survives the restore.
        s, b = h2.call("GET", f"/v1/residents/ember/runs/{export['run_id']}",
                       token=h2.tokens["nimbus"])
        assert s == 403, (s, b)
        s, b = h2.call("GET", f"/v1/residents/ember/runs/{export['run_id']}/events",
                       token=h2.tokens["nimbus"])
        assert s == 403, (s, b)
        print("  restored: run COMPLETE, chain verifies, head == anchor, "
              "nimbus 403")
        print("P7-17 export / restore: PASS")
        return 0
    finally:
        h2.stop()


if __name__ == "__main__":
    sys.exit(main())
