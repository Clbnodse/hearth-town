#!/usr/bin/env python3
"""P7-15 happy-path cycle (extra test, ChatGPT contract test 1).

(1) A full dry-run cycle with the complete ordered trace
run_created -> lease_claimed -> memory_loaded -> goal_proposed ->
goal_accepted -> plan_proposed -> plan_accepted -> action_authorized
-> evaluation_recorded -> run_completed; job still open, no model
call, no /action.
(2) A full LIVE cycle with the deterministic fake model: the trace
also carries action_started -> action_result; the job is claimed
via /action; the run COMPLETES; the chain verifies and the public
anchor matches the head.
(3) The untouched deterministic path (p7=False) still works.
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

PORT = 18915
DRY_TRACE = ["run_created", "lease_claimed", "memory_loaded",
             "goal_proposed", "goal_accepted", "plan_proposed",
             "plan_accepted", "action_authorized", "evaluation_recorded",
             "run_completed"]


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


def trace_types(h, rid, token):
    s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                  token=token)
    assert s == 200, (s, b)
    assert b["chain_ok"], b
    return [e["event_type"] for e in b["events"]], b


def main():
    h = Harness("p7_15", PORT).start()
    try:
        h.clear_rates()
        job_dry = h.make_job("dry-run quest", tags=["host", "quest"])
        job_live = h.make_job("live quest", tags=["host", "quest"])
        # (1) dry-run cycle.
        api = bl.Api(h.root, token=h.tokens["ember"], dry_run=True)
        rec = bl.run_once(api, "p7-15-dry", fh=None, no_reply=True,
                          reason=True, p7=True)
        assert rec["decision"] == "claim" and rec["p7_run"], rec
        rid = rec["p7_run"]["id"]
        types, b = trace_types(h, rid, h.tokens["ember"])
        assert types == DRY_TRACE, types
        assert not [c for c in api.calls if c[1].endswith("/action")], api.calls
        s, b = h.call("GET", f"/public/jobs/{job_dry['id']}")
        assert b.get("status") == "open", b
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                      token=h.tokens["ember"])
        assert b["status"] == "COMPLETE", b
        print("  dry-run cycle: ordered trace 10/10, job open, no /action")
        # (2) live cycle with the fake model. (Rev 1: file side-channel.)
        h.clear_rates()
        h.set_fake_model(suggestion=fake_suggestion(job_live["id"]))
        old_script = bl.P7_SUGGEST_SCRIPT
        bl.P7_SUGGEST_SCRIPT = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fake_reasoning_suggest.py")
        try:
            api = bl.Api(h.root, token=h.tokens["ember"], dry_run=False)
            rec = bl.run_once(api, "p7-15-live", fh=None, no_reply=True,
                              reason=True, p7=True)
        finally:
            bl.P7_SUGGEST_SCRIPT = old_script
            h.clear_fake_model()
        assert rec["decision"] == "claim", rec
        assert rec["reasoning"]["called"] is True, rec
        assert rec["reasoning"]["fallback"] is False, rec
        assert rec["action"]["kind"] == "claim", rec
        assert rec["action"]["job_id"] == job_live["id"], rec
        rid = rec["p7_run"]["id"]
        types, b = trace_types(h, rid, h.tokens["ember"])
        assert types == ["run_created", "lease_claimed", "memory_loaded",
                         "goal_proposed", "goal_accepted", "plan_proposed",
                         "plan_accepted", "action_authorized",
                         "action_started", "action_result",
                         "evaluation_recorded", "run_completed"], types
        s, b = h.call("GET", f"/public/jobs/{job_live['id']}")
        assert b.get("status") == "claimed" and b.get("claimed_by") == ["ember"], b
        s, b = h.call("GET", f"/v1/residents/ember/runs/{rid}",
                      token=h.tokens["ember"])
        assert b["status"] == "COMPLETE" and b["actions_taken"] == 1, b
        # Rev 1 (S8): the head is anchored on every CLIENT append
        # and terminal transition — 8 here, not 12: the two creation
        # events and the two server-internal action events
        # (action_started, action_result) carry no anchor of their
        # own and are covered by the next client append's anchor.
        # The LAST anchor (matching the final head) is the one that
        # must equal the trace head.
        anchors = [e for e in h.public_events()
                   if e.get("type") == "run.chain_anchored"
                   and e.get("payload", {}).get("run_id") == rid]
        assert len(anchors) == 8, anchors
        s, b2 = h.call("GET", f"/v1/residents/ember/runs/{rid}/events",
                       token=h.tokens["ember"])
        final = [a for a in anchors
                 if a["payload"]["head_hash"] == b2["head_hash"]]
        assert len(final) == 1, final
        assert final[0]["payload"]["events"] == b2["count"], final
        print("  live cycle: ordered trace 12/12, job claimed, "
              "COMPLETE, public anchor == head")
        # (3) untouched deterministic path.
        api = bl.Api(h.root, token=h.tokens["ember"], dry_run=True)
        rec = bl.run_once(api, "p7-15-legacy", fh=None, no_reply=True,
                          reason=False, p7=False)
        assert rec["decision"] == "claim" and rec.get("p7_run") is None, rec
        print("  legacy path (p7=False): claim (dry_run), no run record")
        print("P7-15 happy-path cycle: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
