#!/usr/bin/env python3
"""Priority 7 model subprocess entry point (production).

Reads a context JSON on stdin, runs the real model (Ollama / Meta
API via reasoning.Reasoner), writes {"suggestion": ..., "reason_code":
...} to stdout. It holds NO credential: no bearer token, no connector
name, no API base, no board client, no DB handle, no executor socket.
Communication is stdin/stdout JSON only.

Revision 1 (R1): the fake-model env hooks (JSON / RAW / SLEEP) are
GONE from this file. The production suggest script never reads them
and never fakes a suggestion; anyone who can set the cron env can no
longer inject arbitrary "model output" into a live run. Fake-model
behaviour lives only in the test-only script
tests/fake_reasoning_suggest.py (driven by a file, never by env),
selected in tests by monkeypatching bounded_loop.P7_SUGGEST_SCRIPT.
The real path constructs the Reasoner (Ollama / MetaApiClient) inside
this process only — the executor never builds a model client itself.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reasoning import (Reasoner, classify_adapter_output)


def main():
    raw = sys.stdin.buffer.read()
    code = classify_adapter_output(raw)
    if code is not None:
        print(json.dumps({"suggestion": None, "reason_code": code}))
        return 0
    try:
        context = json.loads(raw.decode("utf-8"))
    except ValueError:
        print(json.dumps({"suggestion": None, "reason_code": "non-json"}))
        return 0
    # Real model, constructed HERE (inside the subprocess). The
    # executor never sees the client, the prompt, or the raw reply —
    # only the validated suggestion dict on stdout.
    reasoner = Reasoner()
    wake = context.get("wake") or []
    memory = context.get("memory") or []
    candidates = context.get("candidates") or []
    block = reasoner.deliberate(wake, memory, candidates)
    if block.get("reason_code"):
        print(json.dumps({"suggestion": None,
                          "reason_code": block["reason_code"]}))
        return 0
    suggestion = {k: block.get(k) for k in (
        "chosen_job_id", "declined_job_id", "decline_reason", "ranking",
        "goals", "uncertainty", "evidence", "confidence", "alternatives")}
    print(json.dumps({"suggestion": suggestion, "reason_code": None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
