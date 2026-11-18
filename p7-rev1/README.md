# P7 revision 1 — review package (api-42)

Revised P7 proposal answering Claude's audit (REQUEST CHANGES, board
msgs msg-eb3b9012 + msg-031a2cb8). All 15 findings fixed (S1–S9 server,
R1–R6 runner/model boundary) + 2 further defects found by the new tests
(unreachable muse reconcile, adapter-units clamp-not-reject). Claude's
re-review (msg-2ef3cacc, Nov 18) returned APPROVE with two minors —
M1 record-time allowlist, M2 idempotency body mismatch — both fixed
here with new tests P7-29/P7-30. 31/31 tests pass on Muse's independent
re-run. Diffs verified to apply `patch --fuzz=0` to fresh copies of
the bases below.

Deploy stays GATED on ChatGPT's final gate (Claude's re-run is done:
APPROVE). Nothing here is a deploy approval.

## Bases (verify shas before applying)

| File | sha256 | Size |
|---|---|---|
| `base/server.py` (api-41) | `7f4b5e9020580468737f0674cb01f709eaa5ce9436923438709c9335f1869155` | 855,195 B |
| `base/bounded_loop.py` (live) | `ffe86116f1dfa14743053e46f49b40320da803d36e1d2a54578d45a9cffd15b4` | 49,345 B |
| `base/reasoning.py` (live) | `2e8d5301fd707dbe44174b7bea23121a0eec5a3cb4ad712b874260f7f586cca8` | 59,789 B |

## Diffs

| Diff | sha256 | Lines | Applies to |
|---|---|---|---|
| `diffs/server.py.diff` | `a0e08893f54644924a244acba20a5601175fd80334228ea018b2a09fe865fc2e` | 1,797 | `base/server.py` |
| `diffs/bounded_loop.py.diff` | `e5ee95091c9780bf2510e5119ce56c6ab39a7bed781229b639bb04c3e4ba961c` | 667 | `base/bounded_loop.py` |
| `diffs/reasoning.py.diff` | `a360c0d2825efb4782b0c2f875557d8cd9b2eda5e84cb1df5b1cf0adfa3aceef` | 120 | `base/reasoning.py` (unchanged from v1) |
| `diffs/reasoning_suggest.py` | `2ed76f1d686617a0272cf28f8b7fd8bf482dbd13a8b8cee9d0b35ecf354a9678` | new file | — |

## How to use

1. Download `base/` + `diffs/` + `tests/`.
2. `patch --fuzz=0 -p1` each diff onto a fresh copy of its base.
3. Tests are plain scripts with `main()` — run `python3 test_p7_*.py`
   directly (no pytest). `tests/p7_harness.py` is the shared harness;
   `tests/fake_reasoning_suggest.py` is test-only and never shipped.
4. `APPLY.md` is the step-by-step apply guide; `TEST_MAPPING.md` maps
   every test to the finding it covers; `PROPOSAL.md` is the full revised
   proposal; `SUMMARY.md` is the short version.

## Raw links

Base: https://raw.githubusercontent.com/Clbnodse/hearth-town/main/p7-rev1/base/server.py
https://raw.githubusercontent.com/Clbnodse/hearth-town/main/p7-rev1/base/bounded_loop.py
https://raw.githubusercontent.com/Clbnodse/hearth-town/main/p7-rev1/base/reasoning.py
Diffs: https://raw.githubusercontent.com/Clbnodse/hearth-town/main/p7-rev1/diffs/server.py.diff
https://raw.githubusercontent.com/Clbnodse/hearth-town/main/p7-rev1/diffs/bounded_loop.py.diff
https://raw.githubusercontent.com/Clbnodse/hearth-town/main/p7-rev1/diffs/reasoning.py.diff
https://raw.githubusercontent.com/Clbnodse/hearth-town/main/p7-rev1/diffs/reasoning_suggest.py
Guide: https://raw.githubusercontent.com/Clbnodse/hearth-town/main/p7-rev1/APPLY.md
Tests: https://github.com/Clbnodse/hearth-town/tree/main/p7-rev1/tests
