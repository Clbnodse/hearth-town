#!/usr/bin/env python3
"""P7-32 timeout raise 90/120 -> 150/180 (owner-approved 2026-11-19).

The first live claim (07:53 ET, job-603d0dd7, 85.9s) barely fit the
90 s client timeout, and the 07:38 tick timed out at 90.3 s with the
model at 244 tokens mid-reply. The owner approved raising the limits
so a full reply can finish. Pins:
  REASONING_TIMEOUT_S == 150 (OllamaClient / Reasoner default)
  P7_MODEL_TIMEOUT_S == 180 (subprocess spawn timeout)
Hierarchy, with headroom at each step, against the server run wall
budget default (_P7_DEFAULT_MAX_WALL_MS == 300000 ms in the api-42
server): 150 s client < 180 s subprocess < 300 s server wall.
Also pins that a default Reasoner() carries the 150 s timeout.
"""
import os
import re
import sys

REV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(REV, "work")
sys.path.insert(0, WORK)
import bounded_loop as bl
import reasoning as rs

REV_SERVER = os.path.join(
    WORK, "stage-v17-game-api42-REV", "server.py")


def main():
    # (1) The client timeout the owner approved.
    assert rs.REASONING_TIMEOUT_S == 150, (
        f"client timeout is {rs.REASONING_TIMEOUT_S}, expected 150")
    print("PASS client: REASONING_TIMEOUT_S == 150")

    # (2) The subprocess timeout the owner approved.
    assert bl.P7_MODEL_TIMEOUT_S == 180, (
        f"subprocess timeout is {bl.P7_MODEL_TIMEOUT_S}, expected 180")
    print("PASS subprocess: P7_MODEL_TIMEOUT_S == 180")

    # (3) Hierarchy: client < subprocess, with headroom for the
    # spawn + read around the model call.
    assert rs.REASONING_TIMEOUT_S < bl.P7_MODEL_TIMEOUT_S, (
        "client timeout must be below the subprocess timeout")
    assert bl.P7_MODEL_TIMEOUT_S - rs.REASONING_TIMEOUT_S >= 20, (
        "subprocess headroom over client timeout is under 20 s")
    print("PASS hierarchy: 150 s client < 180 s subprocess (>=20 s gap)")

    # (4) Both fit inside the server run wall budget (300 s default
    # in the api-42 server); a model call that fits its own timeout
    # can never trip the run wall.
    with open(REV_SERVER) as fh:
        server_src = fh.read()
    m = re.search(r"_P7_DEFAULT_MAX_WALL_MS\s*=\s*(\d+)", server_src)
    assert m, "server wall default not found in REV server.py"
    wall_s = int(m.group(1)) // 1000
    assert wall_s == 300, f"server wall is {wall_s} s, expected 300"
    assert bl.P7_MODEL_TIMEOUT_S < wall_s, (
        "subprocess timeout must fit inside the server wall budget")
    print("PASS server wall: 180 s subprocess < 300 s run wall")

    # (5) A default Reasoner() carries the new timeout.
    assert rs.Reasoner().timeout_s == 150, (
        f"default Reasoner timeout is {rs.Reasoner().timeout_s}")
    print("PASS default Reasoner().timeout_s == 150")

    print("P7-32 PASS (5/5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
