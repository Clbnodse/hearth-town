#!/usr/bin/env python3
"""P7-31 wake-prefix normalization + cap 400 (owner-approved 2026-11-19).

The live model reads the wake lines ("- wake <id>: ...") and cites
them as "wake-<id>" in evidence and goals refs (measured live 2/2
replies at cap 400). deliberate() must strip one leading "wake-"
before validation — the same defensive-parsing category as the
"null" coercion — while still rejecting an id that was never shown.
Also pins the owner-approved cap: REASONING_MAX_TOKENS == 400.
"""
import json
import os
import sys

WORK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work")
sys.path.insert(0, WORK)
import reasoning as rs

WAKE_ID = "abc123def456"
JOB_ID = "job-603d0dd7"


class StubClient(rs.ModelClient):
    def __init__(self, text):
        self.text = text
        self.name = "stub/test"

    def complete(self, messages, *, max_tokens, timeout):
        return self.text, 150


def wake_items():
    return [{"wake_id": WAKE_ID, "event_type": "message.mentioned",
             "matched_tag": "host", "payload_summary": {}}]


def candidates():
    return [{"id": JOB_ID,
             "title": "Ember posts tonight's hearth check-in",
             "job_tags": ["host"], "created_by": "agent:muse",
             "reward_credits": 5,
             "brief": "Post a short check-in to the lobby board."}]


def suggestion(wake_refs, goals_ref=None):
    return {"chosen_job_id": JOB_ID, "declined_job_id": None,
            "decline_reason": "",
            "ranking": [{"job_id": JOB_ID, "score": 1,
                         "reason": "matches host tag"}],
            "goals": [{"text": "Post check-in to lobby board",
                       "ref": goals_ref or JOB_ID}],
            "uncertainty": [],
            "evidence": {"wake_ids": wake_refs, "memory_seqs": [],
                         "job_ids": [JOB_ID]},
            "confidence": 1, "alternatives": []}


def main():
    # (1) The cap the owner approved.
    assert rs.REASONING_MAX_TOKENS == 400, (
        f"cap is {rs.REASONING_MAX_TOKENS}, expected 400")
    print("PASS cap: REASONING_MAX_TOKENS == 400")

    # (2) Prefixed evidence + goals ref for a SHOWN wake id validates,
    # and the stored block carries the bare id.
    text = json.dumps(suggestion(["wake-" + WAKE_ID],
                                 goals_ref="wake-" + WAKE_ID))
    block = rs.Reasoner(client=StubClient(text)).deliberate(
        wake_items(), [], candidates())
    assert block.get("fallback") is False, (
        f"prefixed shown id rejected: {block.get('fallback_reason')}")
    assert block.get("chosen_job_id") == JOB_ID
    assert block["evidence"]["wake_ids"] == [WAKE_ID], (
        f"evidence not normalized: {block['evidence']['wake_ids']}")
    assert block["goals"][0]["ref"] == WAKE_ID, (
        f"goals ref not normalized: {block['goals'][0]['ref']}")
    print("PASS prefixed shown wake id validates + normalizes to bare id")

    # (3) A prefixed id that was NEVER shown is still rejected —
    # normalization must not launder an unseen citation.
    text = json.dumps(suggestion(["wake-zzz999"]))
    block = rs.Reasoner(client=StubClient(text)).deliberate(
        wake_items(), [], candidates())
    assert block.get("fallback") is True, "unseen wake id accepted"
    assert block.get("reason_code") == "model_error", (
        f"wrong reason_code: {block.get('reason_code')}")
    assert "zzz999" in (block.get("fallback_reason") or ""), (
        f"error does not name the unseen id: "
        f"{block.get('fallback_reason')}")
    print("PASS prefixed unseen wake id still rejected (model_error)")

    # (4) A bare shown id still validates (no regression).
    text = json.dumps(suggestion([WAKE_ID]))
    block = rs.Reasoner(client=StubClient(text)).deliberate(
        wake_items(), [], candidates())
    assert block.get("fallback") is False, (
        f"bare shown id rejected: {block.get('fallback_reason')}")
    print("PASS bare shown wake id still validates")

    print("P7-31 PASS (4/4)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
