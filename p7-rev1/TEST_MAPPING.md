# Priority 7 — test mapping (revision 1)

Every Claude gap (12), every ChatGPT contract acceptance test (12), every
Grok acceptance item (8), every matrix test (14), and every Claude audit
finding (S1–S9, R1–R6) → concrete test file + expected output. All 32 tests
pass; commands are run from
`~/workspace/game-collab-api/priority7/revision/tests/` as
`python3 test_p7_XX_<name>.py`. All tests run against the real server, real
SQLite trace stores, and (where stated) real subprocesses — no mocks of the
server, the store, or the subprocess boundary. The v1 mapping
(`formal-proposal/TEST_MAPPING.md`) still describes the v1 suite; this file
describes the revision: what changed in the 18 v1 tests, and the 13 new ones.

## A. Claude's 12 gaps (msg-fe7dd927) — revision status

| # | Gap | Test | Revision change |
|---|---|---|---|
| 1 | Runner identity: model process holds NO credential; only a separate executor with a per-run allowlist-scoped token can act | P7-01 + P7-02 | P7-01 REWRITTEN (R1): the hooks must NOT reach the child env; production source must contain no hook names. P7-02 updated (minors M1, Nov 18): `drive_to_authorized` takes an `action_type` — the noop-only run now drives with `noop`, since an out-of-allowlist kind is refused at record time. |
| 2 | Fencing, not just leases; test 3 must use real separate processes racing | P7-04 | Policy set at start (rapid runs need min_cooldown 0). Unchanged otherwise. |
| 3 | Kill switch TOCTOU | P7-05 | Policy set at start. Unchanged otherwise. Scope clarified by P7-28 (S9). |
| 4 | UNKNOWN_OUTCOME state; block new runs until reconciled; no automatic retry | P7-06 | REWRITTEN (S3): a known refusal is BLOCKED, not UNKNOWN_OUTCOME; new run immediately possible. The lock itself is now covered by P7-18/P7-19 (S1/S2). |
| 5 | NO_ACTION path in the state machine, with its own trace events | P7-07 | Hook mechanism swapped to the test-only fake script. Unchanged otherwise. |
| 6 | Budgets + cooldown in the envelope; persist spend counters; count model tokens at the adapter, not as reported | P7-10 | REWRITTEN (S5/R5): `model_tokens` refused (400); cooldown 0 does not clear the policy floor; spend field is now `output_units_today`. |
| 7 | Test 9 needs a control run + poisoned-lesson test; lessons structured fields only, never free text in prompts | P7-11 | Hook mechanism swapped. Unchanged otherwise. |
| 8 | Test 4 must go through a raw storage handle; state the mechanism; resident_id from the lease, never from plan/model output | P7-08 | (d): the server now REJECTS a payload naming another resident (400) instead of silently rewriting it. |
| 9 | Tests 11/12 need canaries; dry-run: external adapter constructors NEVER invoked, not merely stubbed | P7-12 + P7-13 | P7-12: dry-run probe uses claim_job (in the allowlist) instead of noop. P7-13: goal_proposed is ref/kind only — the goal-text canary still must not appear anywhere (S7 schemas). |
| 10 | Tamper evidence: chain head anchored outside runner write authority; DB-level append-only enforcement; UPDATE/DELETE test | P7-09 | Anchor count corrected (S8 nuance): 4 anchors (3 client appends + complete), not 6 — creation events and server-internal action events are covered by the next client append's anchor. Tamper/rollback sections unchanged. |
| 11 | Adapter failure modes (timeout/empty/oversized/non-JSON) each need their own reason code | P7-14 | E2E timeout monkeypatches the timeout constant in-process (the env override is gone, R1). The oversized case is the R5 clamp evidence (§2a): the plan_rejected event now flows through the trace instead of breaking it. |
| 12 | Reconcile with P6: extend bounded_loop.py / reasoning.py, do NOT fork a second runner | design + P7-15(3) | Diffs are patches to the P6 files (no new runner); P7-15 prints `legacy path (p7=False): claim (dry_run), no run record`. Anchor count corrected: 8 anchors. |

## B. ChatGPT contract acceptance tests (msg-9c8ab502, tests 1–12) — revision status

| # | Contract test | Test | Revision change |
|---|---|---|---|
| 1 | Ember completes one dry-run cycle, full ordered trace | P7-15 | Anchor count 8. Hook mechanism swapped. |
| 2 | Same idempotency key twice → one execution only | P7-03 + **P7-30** | Unchanged (create_run now also sends policy_version). P7-30 (minors M2, Nov 18): a replay with a different body is 409 `idempotency_body_mismatch`; same-body replay still 200, no token re-issue. |
| 3 | Concurrent workers cannot both claim/execute one run | P7-03 + P7-04 | Unchanged. |
| 4 | Cross-resident memory read/write rejected at storage boundary | P7-08 | See A8. |
| 5 | Kill switch flipped after planning but before action blocks execution | P7-05 | Unchanged. |
| 6 | Unknown action, malformed model output, missing policy, missing memory, expired lease, budget exhaustion each fail closed with distinct reason codes | P7-02 + P7-14 + P7-04 + P7-10 + **P7-21** | Missing policy is now TESTED (P7-21) — §E gap 1 CLOSED. Missing memory: see §E. |
| 7 | Model-proposed goal requesting new permissions is rejected | P7-16 | Hook mechanism swapped. |
| 8 | Model claim of success without matching action evidence → unknown/failure, not success | P7-06 + **P7-24** | P7-06 rewritten (S3); P7-24 proves the server cross-checks evaluation against the stored action_result (S7). |
| 9 | Restart loads the lesson and changes the next candidate decision; evidence references the prior run | P7-11 | Unchanged. |
| 10 | Export/restore preserves event-chain validity and resident isolation | P7-17 | Final anchor == trace head (S8 nuance). |
| 11 | Dry-run mode cannot reach any external side-effect adapter | P7-12 | See A9. |
| 12 | Logs contain hashes/metadata but no raw prompts, private memory, tokens, or credentials | P7-13 + **P7-26** | P7-26 adds the canary AT the model-input boundary (R4): the exact stdin the model receives. |

## C. Grok's acceptance items (msg-924d7cb2, minimum 8) — revision status

Unchanged from v1 (P7-04, P7-05, P7-06, P7-07, P7-11, P7-12, P7-10, P7-00 all pass in the revision). P7-06's meaning changed per S3 (known refusal → BLOCKED, not UNKNOWN_OUTCOME); the lock behaviour it used to cover now lives in P7-18/P7-19. P7-00 now checks the REV server (not the v1 DRAFT) and expects 63 OpenAPI paths — rev 1 added the run-policy route (minors, Nov 18).

## D. ChatGPT 14-test matrix (msg-23742ec0) → files (revision)

Same 14 files as v1, updated as described in §A. Extra v1 tests: P7-00, P7-15, P7-16, P7-17. New in rev1: P7-18…P7-28 (see §G) + P7-29/P7-30 (see §H) + P7-31 (see §I).

## E. Gaps — enforced in code, no dedicated test (NOT claimed as passing)

1. ~~**Contract test 6, "missing policy"**~~ — **CLOSED in rev1 by P7-21** (missing → 400 `policy_version_required`, wrong → 400 `policy_version_mismatch`, valid → 201 with caps on the record).
2. **Contract test 6, "missing memory":** the memory load is server-side and always present in the fixture; there is no distinct failure path to test against. If reviewers want a simulated memory-store failure, it needs a fault-injection hook in the server.
3. **Contract state `WAKE_REQUESTED`:** not added as a run state. A wake is an inbox event that precedes run creation; the run starts at LEASED.
4. **Legacy runner suite unverified:** `test_bounded_loop.py`, `test_fixes*.py`, `test_reasoning.py` require REAL vault tokens and cannot run in this environment. Noted as unverified, not as passing. The P7 runner changes are additive behind `--p7`; P7-15(3) proves the legacy path still runs.
5. **R6 (separate executor identity):** acknowledged residual, not a test gap — creator and executor are the same OS process by design in this slice. True separate executor identity is a follow-up design, documented in PROPOSAL.md §3/R6, not claimed here.

## F. Full-suite tally (this session, 2026-11-18)

**31/31 PASS** against the REV stage, run in one pass from `tests/`:

```
test_p7_00_html_hash: PASS
test_p7_01_model_isolation: PASS
test_p7_02_executor_allowlist: PASS
test_p7_03_lease_idempotency: PASS
test_p7_04_fencing_race: PASS
test_p7_05_kill_switch: PASS
test_p7_06_unknown_outcome: PASS
test_p7_07_no_action: PASS
test_p7_08_storage_isolation: PASS
test_p7_09_append_only: PASS
test_p7_10_budgets_cooldown: PASS
test_p7_11_poisoned_lesson: PASS
test_p7_12_dry_run: PASS
test_p7_13_canaries: PASS
test_p7_14_adapter_failures: PASS
test_p7_15_happy_path_cycle: PASS
test_p7_16_permission_goal: PASS
test_p7_17_export_restore: PASS
test_p7_18_unknown_outcome_lock: PASS
test_p7_19_no_lazy_expiry: PASS
test_p7_20_known_refusals: PASS
test_p7_21_policy_version: PASS
test_p7_22_server_policy: PASS
test_p7_23_crash_reconcile: PASS
test_p7_24_event_schemas: PASS
test_p7_25_bounded_read: PASS
test_p7_26_model_input_canary: PASS
test_p7_27_no_hooks_in_production: PASS
test_p7_28_kill_switch_scope: PASS
test_p7_29_record_allowlist: PASS
test_p7_30_idempotency_mismatch: PASS
test_p7_31_wake_prefix: PASS
```

Addendum 2026-11-19: P7-31 added (owner-approved cap 400 + wake-prefix
normalization). Full re-run this session: **32/32 PASS** (P7-00…P7-31).

V1 baseline re-run against the v1 code (same session): **18/18 PASS** — no regression in the baseline record.

Diff verification: `patch --fuzz=0 -p1` applies all three rev1 diffs cleanly to fresh api-41 copies; patched files are byte-identical to the work files; `py_compile` passes on all. Regenerating the fixed files with `build/apply_server_fixes.py` (from the DRAFT stage server) + `build/apply_runner_fixes.py` produces byte-identical files.

## H. Claude re-review minors (msg-2ef3cacc, Nov 18) → new tests

| Minor | Test | File | Result |
|---|---|---|---|
| M1 record-time allowlist: out-of-allowlist kind refused at append (400 `event_kind_not_in_allowlist`) | P7-29 | `test_p7_29_record_allowlist.py` | `P7-29 record-time allowlist: PASS` (+ goal/plan/action with kind send_money on a claim_job run → 400; goal None → 201; rejected kinds absent from GET events) |
| M2 idempotency body mismatch: replay with a different body is 409 | P7-30 | `test_p7_30_idempotency_mismatch.py` | `P7-30 idempotency body mismatch: PASS` (+ same-body replay → 200, no token re-issue; mode/allowlist/max_steps variants → 409; original run untouched; fresh live key on a default-policy resident → 403 live_not_enabled) |

## I. Owner-approved cap raise (Nov 19) → new test

| Change | Test | File | Result |
|---|---|---|---|
| REASONING_MAX_TOKENS 160→400; `wake-` prefixed evidence/goals refs for a shown wake id normalize to the bare id before validation (same defensive-parsing category as the `"null"` coercion); an unseen prefixed id is still rejected | P7-31 | `test_p7_31_wake_prefix.py` | `P7-31 PASS (4/4)` (+ cap pinned at 400; prefixed shown id validates + normalizes; prefixed unseen id still rejected model_error; bare shown id still validates) |

## G. Claude's audit findings (msg-eb3b9012 + msg-031a2cb8) → new tests

| Finding | Test | File | Expected output |
|---|---|---|---|
| S1 lock bypassable (3 ways) | P7-18 | `test_p7_18_unknown_outcome_lock.py` | `P7-18 UNKNOWN_OUTCOME lock cannot be bypassed: PASS` (+ resident expire/block/complete → 403 reconcile_requires_muse; muse bad evidence → 400; muse real event id → 200 + new run 201; muse can GET run + events) |
| S2 lock evaporates | P7-19 | `test_p7_19_no_lazy_expiry.py` | `P7-19 UNKNOWN_OUTCOME never lazily expires: PASS` |
| S3 refusal mislabelled | P7-20 | `test_p7_20_known_refusals.py` | `P7-20 known refusals are BLOCKED: PASS` (+ missing job → 404 action_not_committed; self-claimed → 409; new run 201 right after) |
| S4 policy_version absent | P7-21 | `test_p7_21_policy_version.py` | `P7-21 policy_version + run caps enforced: PASS` |
| S5 limits caller-chosen | P7-22 | `test_p7_22_server_policy.py` | `P7-22 server-side run policy: PASS` (+ live gate; cooldown floor; allowlist subset; noop action + evaluation + complete under policy) |
| S6 crash window | P7-23 | `test_p7_23_crash_reconcile.py` | `P7-23 crash reconcile on startup: PASS` (+ started/no result → UNKNOWN_OUTCOME; committed result → ACTION_EXECUTED; refused result → BLOCKED) |
| S7 client-asserted policy | P7-24 | `test_p7_24_event_schemas.py` | `P7-24 event payload schemas enforced: PASS` (+ unknown key/free text → 400; live evaluation without action_result → 409; dry-run evaluation → 201; canary absent from GET events) |
| S8 anchor only at terminal | P7-09 (updated) | `test_p7_09_append_only.py` | Anchor on every client append (4 in P7-09, 8 in P7-15). Tamper/rollback detection unchanged. |
| S9 kill-switch scope | P7-28 | `test_p7_28_kill_switch_scope.py` | `P7-28 kill switch scope (P7 only): PASS` (+ legacy direct claim → 200 while ON; P7 /action → 403 kill_switch_on; after OFF → 200) |
| R1 test hooks in prod | P7-27 (+ P7-01) | `test_p7_27_no_hooks_in_production.py` | `P7-27 no test hooks in production: PASS` (+ zero hook names in all four production files; child env exactly {PATH, HOME, PYTHONPATH}) |
| R2 whole output buffered | P7-25 | `test_p7_25_bounded_read.py` | `P7-25 bounded model-output read: PASS` (+ unbounded stream → oversized fast, units 16384, latency < 10 s; silent child → timeout) |
| R3 "no credential" only env | — (docs) | PROPOSAL.md §3/R3 | Claim downgraded to "env-scrubbed only". No test can prove a separation that does not exist. |
| R4 full memory to model | P7-26 | `test_p7_26_model_input_canary.py` | `P7-26 canary at the model-input boundary: PASS` (+ brief/memory canaries absent from captured stdin; claim still completes) |
| R5 adapter_tokens fake | P7-14 + P7-10 | `test_p7_14_adapter_failures.py`, `test_p7_10_budgets_cooldown.py` | Renamed to adapter_output_units; server clamps (not rejects) at both intake points — the P7-14 oversized case is the evidence. |
| R6 token still in runner | — (docs) | PROPOSAL.md §3/R6 | Acknowledged residual; follow-up design. See §E item 5. |
