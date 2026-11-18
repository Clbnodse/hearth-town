#!/usr/bin/env python3
"""TEST-ONLY fake model subprocess for the Priority 7 (api-42, rev 1)
tests. This file is NOT part of the proposal and is NEVER shipped:
it is selected in tests by monkeypatching bounded_loop.P7_SUGGEST_SCRIPT.

Revision 1 (R1): the fake is driven by a FILE, never by env vars.
The production spawn passes a strict env (PATH, HOME, PYTHONPATH
only), so no env-based fake can reach a production child. The test
writes the control file (see Harness.set_fake_model), the fake reads
it, and the fake records the stdin payload it received so tests can
assert what the model was actually shown (R4 canary test).

Control file /tmp/p7_fake_model.json (one of "json" / "raw" / "stream",
plus optional "sleep"):
  {"json": <suggestion dict>}  -> stdout {"suggestion": <dict>,
                                          "reason_code": None}
  {"raw": "<verbatim stdout>"} -> stdout is the raw string verbatim
                                  (empty / oversized / non-JSON cases)
  {"stream": <chunk bytes>}    -> write that many bytes in a loop,
                                  forever (until killed): proves the
                                  bounded read (P7-25) — the executor
                                  must kill the child at the cap, not
                                  buffer the whole stream.
  {"sleep": <seconds>}         -> sleep first (timeout case)

Capture file /tmp/p7_fake_captured_input.json: the exact stdin
payload (the minimised model context) the fake received, written
before any sleep/raw handling, so a test can inspect it even when
the adapter fails.

If the control file is absent the fake exits 2 with an error on
stderr, so a test that forgets to set it fails loudly instead of
silently passing with a fake suggestion.
"""
import json
import os
import sys
import time

FAKE_MODEL_FILE = "/tmp/p7_fake_model.json"
FAKE_CAPTURE_FILE = "/tmp/p7_fake_captured_input.json"


def main():
    try:
        raw = sys.stdin.buffer.read()
    except Exception as exc:
        sys.stderr.write("fake: stdin unreadable: %s\n" % exc)
        return 2
    # Capture the model input first (R4: what was the model shown?).
    try:
        with open(FAKE_CAPTURE_FILE, "w") as f:
            f.write(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        sys.stderr.write("fake: capture failed: %s\n" % exc)
        return 2
    try:
        with open(FAKE_MODEL_FILE) as f:
            doc = json.load(f)
    except FileNotFoundError:
        sys.stderr.write("fake: no control file %s\n" % FAKE_MODEL_FILE)
        return 2
    except Exception as exc:
        sys.stderr.write("fake: control file unreadable: %s\n" % exc)
        return 2
    if doc.get("sleep") is not None:
        time.sleep(float(doc["sleep"]))
    if "stream" in doc:
        # Unbounded output: write forever until the parent kills us.
        # The bounded read must stop us at the cap (P7-25).
        chunk = b"x" * int(doc["stream"])
        while True:
            try:
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            except (BrokenPipeError, OSError):
                return 0
    if "raw" in doc:
        sys.stdout.write(doc["raw"])
        sys.stdout.flush()
        return 0
    if "json" in doc:
        print(json.dumps({"suggestion": doc["json"],
                          "reason_code": None}))
        return 0
    sys.stderr.write("fake: control file has neither json nor raw\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
