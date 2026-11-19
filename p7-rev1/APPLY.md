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
| `diffs/server.py.diff` | `a0e08893f54644924a244acba20a5601175fd80334228ea018b2a09fe865fc2e` | 1,797 |
| `diffs/bounded_loop.py.diff` | `e5ee95091c9780bf2510e5119ce56c6ab39a7bed781229b639bb04c3e4ba961c` | 667 |
| `diffs/reasoning.py.diff` | `d0cf72f98a3ad63b0bfc0b449a1961f7f6594af585ad9c2fca59a3abfa7a77f3` | 160 (cap 400 + wake-prefix normalization, 2026-11-19) |
| `diffs/reasoning_suggest.py` | `2ed76f1d686617a0272cf28f8b7fd8bf482dbd13a8b8cee9d0b35ecf354a9678` | 60 (NEW file) |

## Revision 1 + Claude re-review minors (msg-2ef3cacc, Nov 18)

Claude re-ran his review on rev 1 and returned APPROVE with two
minors fixed before deploy. Both are fixed in this package (the diff
above is the minors version; the pre-minors diff was 1,729 lines,
sha cafe1e57…):

- **M1 — record-time allowlist** (`event_kind_not_in_allowlist`,
  400): a goal/plan/action carrying a kind outside the run's
  allowlist is now refused when appended, not only at `/action` —
  so the trace can never show e.g. `action_authorized send_money`.
  A goal with no candidate (goal None) is unaffected. Covered by
  new test P7-29; P7-02's noop-only run now drives with `noop`.
- **M2 — idempotency body mismatch** (`idempotency_body_mismatch`,
  409): replaying a run-creation key with a different body (mode,
  allowlist, policy_version, max_steps, max_wall_ms,
  max_model_tokens, lease_seconds) is now 409 instead of a silent
  200 of the original run. The fingerprint is stored with the key
  (legacy string records keep the old behaviour). Covered by new
  test P7-30; P7-00 now checks the REV server and expects 63
  OpenAPI paths (rev 1 added the run-policy route).

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
# expect: a24b1fd5a4c70ddee018a2960c9dd8c616e0ad0583e1c08aab01d0f1d13f5966
sha256sum bounded_loop.py reasoning.py reasoning_suggest.py
# expect: d52213c079afb32bf390831353bfe1f7324a936c84ff8a35c7b808bc6d2e714b
#         42ffe7b0407e6f381a1865105fe35e02455954cf430fb7150c4ce2b8bd3f8c11
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
must produce byte-identical files. Note the chain: the server builder
takes the **DRAFT** stage server (api-41 + the v1 formal-proposal
diffs, `stage-v17-game-api42-DRAFT/server.py`) — NOT the bare api-41
base, which has no P7 code for the anchors to match:

```bash
cp <DRAFT server.py> /tmp/server_regen.py
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
# expect: 32/32 PASS (P7-00..P7-31)
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
