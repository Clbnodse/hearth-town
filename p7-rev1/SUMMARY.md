# P7 revision 1 — summary (api-42)

**Date:** 2026-11-17. **Author:** Muse. **Status:** revision complete, NOT posted to the board, NOT deployed, live server untouched.

## What this is

Revision 1 of the P7 formal proposal (api-42), answering Claude's audit
(REQUEST CHANGES). Claude's audit messages were retrieved fresh from the
board (msg-eb3b9012 + msg-031a2cb8, pointer msg-100441e1) and
byte-compared against the saved copies — identical. The fix list was
checked against the fresh text finding-by-finding; it matches exactly.
The relayed summary (Grok msg-12b7a332) matched the real findings on
every point; the real text adds method detail, the full S1–S9 + R1–R6
list, and Claude's priority order.

Claude could NOT apply the v1 diff (he had no api-41 server.py) and
could NOT run the 18 tests; he extracted the 862 added P7 lines and ran
them unmodified in a stub harness with stubbed helpers. 11/11 probes
reproduced. The v1 failure was a missing base, not a diff defect —
APPLY.md lists the bases with shas so it does not recur.

## What changed

All 15 audit findings fixed (S1–S9 server, R1–R6 runner/model
boundary), plus a false claim in the v1 proposal corrected (S4:
`policy_version` was documented as enforced but did not exist in the
code — 0 hits across all four files).

| Area | Change |
|---|---|
| S1 lock | muse/owner-only reconcile + trace-referencing evidence; resident bypasses (expire / block manual / complete with any evidence) all 403 |
| S1 reachability | **Found by P7-18 while testing this revision:** the muse reconcile was unreachable — the route's binding check rejected muse before the reconcile branch. Entry guard on the 3 reconcile + 3 read routes now lets muse/owner through; cross-resident access still barred |
| S2 | UNKNOWN_OUTCOME never lazily expires |
| S3 | known claim refusals → BLOCKED/action_rejected (new run at once); only exceptions → UNKNOWN_OUTCOME |
| S4 | `policy_version` p7-policy-1 required (400 if missing/wrong); max_steps / max_wall_ms / max_model_tokens validated + stored |
| S5 | server-side per-resident policy record (min cooldown, live_enabled, allowlist); request can only narrow it; muse/owner run-policy endpoint |
| S6 | intent record saved BEFORE the claim executes; startup reconcile resolves ACTION_AUTHORIZED/ACTION_STARTED runs from their trace |
| S7 | per-event-type payload schemas (known keys only); evaluation cross-checked against the stored action_result |
| S8 | chain head anchored on EVERY append; docs state plainly it detects outsiders, not the host account |
| S9 | **Confirmed with the claim-route code:** kill switch stops P7 run actions only; legacy direct-claim route unaffected; P6 cron stopped by the cron/--reason flag |
| R1 | all three test hooks removed from the production path; child env strictly {PATH, HOME, PYTHONPATH}; zero hook names in production (not even comments); fake model moved to a test-only script |
| R2 | Popen + bounded read (kill at cap); oversized → units = cap//4 |
| R3 | claim downgraded to "env-scrubbed only" (no container/user isolation claimed) |
| R4 | minimized model context (wake id/type, memory seq/type, candidates id/title only) |
| R5 | `adapter_tokens` → `adapter_output_units`; server **clamps** (not rejects) at both intake points — **found by P7-14:** an oversized output measures 16,384 units vs a 2,000-unit run cap, so rejecting broke the trace |
| R6 | acknowledged residual: creator and executor are the same OS process; true separate executor identity is a follow-up design |

## Test results

- **Revision suite: 31/31 PASS** (2026-11-18, REV stage, real server/SQLite/subprocesses) — 18 updated v1 tests + 13 new (P7-18…P7-30).
- **V1 baseline re-run: 18/18 PASS** against the v1 code — no regression.
- Five new tests failed on first run; all five fixed (P7-18 was the real S1 reachability bug above; P7-20/21/22/26 were test-side fixes with known remedies).
- Minors run 2026-11-18 (Claude re-review msg-2ef3cacc): P7-29/P7-30 new; P7-00 fixed (63 paths, REV server); P7-02 drive updated for M1; full suite 31/31 with no regression.
- Diff verification: all three rev1 diffs apply cleanly with `patch --fuzz=0 -p1` to fresh api-41 copies; patched files byte-identical to the work files; `py_compile` passes. Regenerating from the DRAFT stage with the build scripts gives byte-identical files.

## Files

Under `~/workspace/game-collab-api/priority7/revision/`:

| File | Purpose |
|---|---|
| `PROPOSAL.md` | full revised proposal (fix list, corrected §2, check orders, §16–§21) |
| `TEST_MAPPING.md` | v1 tests (what changed) + Claude findings → new tests; §E gap 1 CLOSED by P7-21 |
| `APPLY.md` | exact apply commands + order + base/diff shas + Claude harness re-run notes |
| `BOARD_DRAFT.md` | proposal split into 14 board-ready parts (index + 1–13), each under 1900 chars |
| `SUMMARY.md` | this file |
| `diffs/server.py.diff` | 1,797 lines, sha a0e08893… |
| `diffs/bounded_loop.py.diff` | 667 lines, sha e5ee9509… |
| `diffs/reasoning.py.diff` | 120 lines, unchanged v1, sha a360c0d2… |
| `diffs/reasoning_suggest.py` | new file, hook-free, sha 2ed76f1d… |
| `build/apply_server_fixes.py` | produces work/server.py from the DRAFT stage server |
| `build/apply_runner_fixes.py` | produces the runner files from the v1 work files |
| `work/server.py` etc. | patched files (server sha a24b1fd5…; runner d52213c0…; suggest 2ed76f1d…) |
| `work/stage-v17-game-api42-REV/` | REV stage used by the tests |
| `work/audit_messages_fresh.json` | Claude's three audit messages, fresh from the board |
| `tests/p7_harness.py` + `test_p7_*.py` | 31 tests |
| `tests/fake_reasoning_suggest.py` | test-only fake model (never shipped) |

## What was NOT verified

- The legacy bounded-loop suite needs REAL vault tokens and cannot run in this environment (same as v1).
- No live-town verification, by design — nothing here touches the live town.
- No independent re-review yet: Claude's harness re-run + ChatGPT's final gate still gate the deploy. The owner has taken no deploy decision on this revision.
