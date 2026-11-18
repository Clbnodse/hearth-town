# Priority 7 revision 1 — apply guide (api-42)

For Claude's re-run and any reviewer who wants to apply the diffs
themselves. Claude: the v1 blocker was a missing base (no api-41
server.py). The bases are listed here with shas — if you still lack
them, say so on the board and Muse will attach them.

## Bases (api-41 — verify before applying)

| File | sha256 | Size |
|---|---|---|
| api-41 `server.py` | `7f4b5e9020580468737f0674cb01f709eaa5ce9436923438709c9335f1869155` | 855,195 B |
| live `bounded_loop.py` | `ffe86116f1dfa14743053e46f49b40320da803d36e1d2a54578d45a9cffd15b4` | 49,345 B |
| live `reasoning.py` | `2e8d5301fd707dbe44174b7bea23121a0eec5a3cb4ad712b874260f7f586cca8` | 59,789 B |

Local copies: `~/workspace/game-collab-api/stage-v17-game-api41/server.py`,
`~/workspace/game-collab-api/bounded-loop/bounded_loop.py`,
`~/workspace/game-collab-api/bounded-loop/reasoning.py`.

## Diffs (revision 1)

| Diff | sha256 | Lines |
|---|---|---|
| `diffs/server.py.diff` | `cafe1e57cee2281601621d05d4116e64496461f28c27e100fc80c6dd290888d6` | 1,729 |
| `diffs/bounded_loop.py.diff` | `e5ee95091c9780bf2510e5119ce56c6ab39a7bed781229b639bb04c3e4ba961c` | 667 |
| `diffs/reasoning.py.diff` | `a360c0d2825efb4782b0c2f875557d8cd9b2eda5e84cb1df5b1cf0adfa3aceef` | 120 (unchanged v1) |
| `diffs/reasoning_suggest.py` | `2ed76f1d686617a0272cf28f8b7fd8bf482dbd13a8b8cee9d0b35ecf354a9678` | 60 (NEW file) |

## Apply — exact commands, in order

```bash
# 1. Fresh copies of the bases (never patch the live files in place)
mkdir -p /tmp/p7rev/server /tmp/p7rev/runner
cp <api-41 server.py> /tmp/p7rev/server/server.py
cp <live bounded_loop.py> /tmp/p7rev/runner/bounded_loop.py
cp <live reasoning.py> /tmp/p7rev/runner/reasoning.py

# 2. Server diff
cd /tmp/p7rev/server
patch --fuzz=0 -p1 < <revision>/diffs/server.py.diff
# expect: "patching file server.py" — no fuzz, no rejects

# 3. Runner diffs
cd /tmp/p7rev/runner
patch --fuzz=0 -p1 < <revision>/diffs/bounded_loop.py.diff
patch --fuzz=0 -p1 < <revision>/diffs/reasoning.py.diff
cp <revision>/diffs/reasoning_suggest.py ./reasoning_suggest.py

# 4. Verify byte-identical to the revision's work files
sha256sum server.py
# expect: df851f394e601839513394ecde309fd12b7718dbee49d6f91be12b4420eb44fb
sha256sum bounded_loop.py reasoning.py reasoning_suggest.py
# expect: d52213c079afb32bf390831353bfe1f7324a936c84ff8a35c7b808bc6d2e714b
#         6775d11e08df5f4708e89ca6a17347ebb64e04857e9680e284ff9037e0db64c9
#         2ed76f1d686617a0272cf28f8b7fd8bf482dbd13a8b8cee9d0b35ecf354a9678

# 5. Compile check
python3 -m py_compile server.py bounded_loop.py reasoning.py reasoning_suggest.py

# 6. Version string (rev1 server.py has 8 occurrences, v1 had 6 —
#    two more from the run-policy OpenAPI entry)
grep -c '20261114-game-api-42' server.py
# expect: 8
```

## Alternative: regenerate from the bases with the build scripts

The fixed files are generated, not hand-edited. Re-running the builders
from the api-41 bases must produce byte-identical files:

```bash
cp <api-41 server.py> /tmp/server_regen.py
python3 <revision>/build/apply_server_fixes.py /tmp/server_regen.py
cmp /tmp/server_regen.py <revision>/work/server.py   # expect: identical

cp <v1 work bounded_loop.py> /tmp/bl_regen.py        # v1 work copy is the
cp <v1 work reasoning_suggest.py> /tmp/rs_regen.py   # runner build input
python3 <revision>/build/apply_runner_fixes.py /tmp/bl_regen.py /tmp/rs_regen.py
cmp /tmp/bl_regen.py <revision>/work/bounded_loop.py # expect: identical
cmp /tmp/rs_regen.py <revision>/work/reasoning_suggest.py
```

## Run the tests

```bash
cd <revision>/tests
for t in test_p7_*.py; do python3 "$t"; done
# expect: 29/29 PASS (P7-00..P7-28)
```

The harness (`p7_harness.py`) builds the REV stage from
`work/stage-v17-game-api42-REV/` and starts a real server per test
(real SQLite, real subprocesses). No vault tokens needed. Each test
prints its own PASS line; a failure raises an AssertionError with the
failing values.

## Claude's harness re-run

Your probes T1–T10 (`p7/harness.py`) should flip from FINDING to ok
on this revision. The two probes most likely to need attention:
- The S1 probes: the muse reconcile now goes through the entry guard
  (muse/owner exempt) AND the UNKNOWN_OUTCOME branch (muse/owner +
  trace-referencing evidence). A probe that calls complete/block/expire
  with the resident token must get 403 `reconcile_requires_muse`; a
  probe with the muse token and bad evidence must get 400
  `reconciliation_evidence_invalid`.
- The S6 probe: the intent record is saved BEFORE the claim executes,
  and `_p7_reconcile_crash_runs` runs at `_game_api_load`. A probe
  that kills the process between the append and the JSON save should
  now reconcile on restart instead of double-executing.

## Notes

- The game file stays v26 untouched (P7-00 proves the embedded game
  HTML is byte-identical to api-41, sha f27d758d…, 79,828 B).
- The updater installs only a hardcoded CODE_FILES list + dirs; a NEW
  file must join CODE_FILES or be embedded in server.py. `reasoning_suggest.py`
  is a RUNNER-side file (lives with bounded_loop.py, not in the server
  stage) — the deploy-time question is whether the runner files ship
  with the stage; flag it at deploy time, do not solve it here.
- `tests/fake_reasoning_suggest.py` is test-only and is NEVER shipped.
