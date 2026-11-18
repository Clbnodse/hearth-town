#!/usr/bin/env python3
"""P7-25 bounded model-output read (rev 1, R2).

In v1 P7_MODEL_MAX_OUTPUT_BYTES appeared once (its declaration)
and subprocess.run(stdout=PIPE) buffered the WHOLE child output
before classify_adapter_output checked its size. In rev 1 the
spawn uses Popen with a bounded read (at most cap + 1 bytes) in a
thread with the timeout, and kills a child that writes more. This
test proves the bound with a child that writes FOREVER: the
executor must return "oversized" quickly (at the cap), not after
buffering the stream or waiting out the timeout. The sleep case
is the control: a child that writes nothing hits "timeout".
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p7_harness import Harness

WORK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work")
sys.path.insert(0, WORK)
import bounded_loop as bl

FAKE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fake_reasoning_suggest.py")

PORT = 18925


def main():
    h = Harness("p7_25", PORT).start()
    try:
        h.clear_rates()
        ctx = {"resident_id": "ember", "wake": [], "memory": [],
               "candidates": [], "lessons": []}
        old_script = bl.P7_SUGGEST_SCRIPT
        bl.P7_SUGGEST_SCRIPT = FAKE_SCRIPT
        try:
            # Unbounded stream: the fake writes 64 KB chunks forever.
            # The bounded read must kill it at the cap, fast.
            h.set_fake_model(stream=65536)
            try:
                t0 = time.time()
                _s, code, units, latency = bl.spawn_model_suggestion(
                    ctx, timeout_s=30)
                dt = time.time() - t0
            finally:
                h.clear_fake_model()
            assert code == "oversized", code
            assert units == bl.P7_MODEL_MAX_OUTPUT_BYTES // 4, units
            assert dt < 10, f"oversized took {dt:.1f}s (not bounded)"
            print(f"  unbounded stream -> oversized in {dt:.1f}s "
                  f"(units {units} = cap // 4, child killed at the cap)")
            # Control: a child that writes nothing hits the timeout.
            h.set_fake_model(sleep=5)
            try:
                t0 = time.time()
                _s, code, _u, _l = bl.spawn_model_suggestion(
                    ctx, timeout_s=2)
                dt = time.time() - t0
            finally:
                h.clear_fake_model()
            assert code == "timeout", code
            assert 1.5 < dt < 5, f"timeout took {dt:.1f}s"
            print(f"  silent child -> timeout in {dt:.1f}s")
        finally:
            bl.P7_SUGGEST_SCRIPT = old_script
        print("P7-25 bounded model-output read: PASS")
        return 0
    finally:
        h.stop()


if __name__ == "__main__":
    sys.exit(main())
