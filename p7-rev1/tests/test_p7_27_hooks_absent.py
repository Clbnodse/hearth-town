#!/usr/bin/env python3
"""P7-27 test hooks are absent from production code (rev 1, R1).

P7-01 proves the hooks do not reach a live child even when the
parent env sets them. This test is the static complement: the
hook names must not appear anywhere in the production files at
all — not in code, not in a comment, not in a docstring. The
production suggest script must contain no "FAKE" substring, and
the spawn's child-env construction must name only PATH, HOME and
PYTHONPATH. (The test-only fake script lives in tests/ and is
selected by monkeypatching, never by env.)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WORK = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "work")
PROD_FILES = ("bounded_loop.py", "reasoning_suggest.py",
              "reasoning.py", "server.py")


def main():
    for name in PROD_FILES:
        path = os.path.join(WORK, name)
        src = open(path).read()
        assert "P7_FAKE_MODEL" not in src, f"{name} contains a hook name"
        assert "P7_FAKE" not in src, f"{name} contains P7_FAKE"
        print(f"  {name}: no P7_FAKE_MODEL / P7_FAKE substring")
    # The production suggest script has no fake behaviour at all.
    suggest = open(os.path.join(WORK, "reasoning_suggest.py")).read()
    assert "FAKE" not in suggest, "suggest script mentions FAKE"
    assert "Reasoner" in suggest and "deliberate" in suggest, suggest
    print("  reasoning_suggest.py: no FAKE, builds a real Reasoner")
    # The spawn builds the child env from exactly three keys.
    bl = open(os.path.join(WORK, "bounded_loop.py")).read()
    m = re.search(r"env = \{([^}]*)\}", bl)
    assert m, "spawn env construction not found"
    assert set(re.findall(r'"([A-Z_]+)"', m.group(1))) == {
        "PATH", "HOME", "PYTHONPATH"}, m.group(1)
    assert "P7_MODEL_TIMEOUT_S" not in m.group(0), m.group(0)
    print("  spawn child env is exactly {PATH, HOME, PYTHONPATH}")
    # No hook pass-through anywhere in the runner.
    assert "os.environ.get(\"P7_FAKE" not in bl, "hook pass-through in runner"
    assert "P7_FAKE_MODEL_JSON" not in bl
    print("P7-27 test hooks absent from production code: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
