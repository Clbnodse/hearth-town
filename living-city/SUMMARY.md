# Hearth Living City — Stages 2, 3, 4: build summary

**Status: BUILT + AUDITED, 0 fails on all three stages. NOT posted to the board,
NOT merged, NOT deployed, live server untouched. Local files only.**
Built 2026-11-17 (evening ET) under the owner's "Build everything".
Base: game v26 (`hearth-3d-game-v2-v26.html`, 79,828 B, sha `f27d758d…`).
Stack order: Stage 2 applies to v26; Stage 3 to v26+Stage 2; Stage 4 to v26+Stage 2+Stage 3.

## Per-stage tallies

| | Stage 2 Market | Stage 3 Civic | Stage 4 Park |
|---|---|---|---|
| Patched file | `hearth-3d-game-v2-v26s2.html` | `hearth-3d-game-v2-v26s2s3.html` | `hearth-3d-game-v2-v26s2s3s4.html` |
| Size / sha | 83,139 B, `24337e78…` | 83,519 B, `7a312ae2…` | 85,963 B, `ca9c7470…` |
| Step diff | `v26-to-stage2.diff` (81 lines) | `v26s2-to-stage3.diff` (13 lines) | `v26s2s3-to-stage4.diff` (53 lines) |
| Cumulative diff | `v26-to-stage2.diff` | `v26-to-stage3.diff` (85 lines) | `v26-to-stage4.diff` (122 lines) |
| New houses | 4 shops | Library, Academy, Maker Space | Growth B, Growth C |
| New kit | 2 stalls, plaza+fountain, 2 benches | — | pond, 4 benches, 3 lamps, ring path + strip, 6 trees |
| Mesh delta | **+158** | **+62** | **+80** |
| Sprite delta | **+1** | **+0** | **+4** |
| Draw-call delta | +159 (792 → 951) | +62 (951 → 1,013) | +84 (1,013 → 1,097) |
| Occluder delta | +7 (64 → 71) | +3 (71 → 74) | +2 (74 → 76) |
| Materials | 764 → 909 | 909 → 964 | 964 → 1,045 |
| Lights | 3 → 3 (no new lights) | 3 → 3 | 3 → 3 |
| Houses (cumulative) | 12 → 16 | 16 → 19 | 19 → 21 |
| Collision discs, TRUE model (cumulative) | 14 → 18 | 18 → 21 | 21 → 23 |
| Audit fails | **0** | **0** | **0** |
| Corridor samples | 40/40 clear | 40/40 clear | 40/40 clear |
| Quest points reachable ≤8u | 24/24 | 24/24 | 24/24 |
| node --check | PASS | PASS | PASS |
| External refs / money words | none / none | none / none | none / none |
| Phone CSS / JS | untouched | untouched | untouched |
| Hall max top-y | 17.8 (unchanged) | 17.8 | 17.8 |
| Scatter (trees/bushes/boulders) | 30/11/11 (unchanged) | 30/11/11 | 36/11/11 (+6 park trees) |

Cumulative: v26 751 meshes + 41 sprites = 792 draw calls → all three stages
**1,051 meshes + 46 sprites = 1,097 draw calls** (+300 meshes, +5 sprites, +305 draw calls).
Per-house mesh counts (node counter, real three-r128): shop 30, gable 18, flat 28,
dome 16, porch 18, hall 32 — all match the Stage 1 measured kit values.

## Built-vs-planned inventory (16 PROP entries)

- Stage 1 (live in v26): 3/16 — Hearth Hall, Ziri's CRT Nook, Growth A.
- After Stage 2: **10/16** — + Bakery, Café, Workshop, General Store, 2 market stalls, plaza+fountain.
- After Stage 3: **13/16** — + Library, Academy, Maker Space.
- After Stage 4: **16/16 — full plan built** — + Growth B, Growth C, City Park.
- Machine-readable: `inventory.json` (derived from the audit results + measured counts).

## What was built (per stage)

**Stage 2 — Market District.** New `shop` roofType branch: flat parapet roof
(kit) + striped awning + chimney; shops get the second window row (2 storeys).
Two new stalls extend the existing `stalls[]` kit (same builder + interact,
flavour-only lines, no trading). Plaza: cobble disc r6 + fountain (basin joins
`cameraOccluders`, like the fire base, per CITY_AUDIT.md) + centre stone +
glow sprite + 2 benches at (±4.5,92) facing the fountain. Bench positions are
pinned at build time — the proposal pins the plaza and the benches but not
their coordinates; rule used: flanking the plaza's south edge, facing the
fountain. Shop colours are build-time choices (proposal pins footprints,
heights, roof types, not colours): Bakery 0xc2703d, Café 0x7a8a4a,
Workshop 0x5a7a9a, General Store 0x9a6a2a.

**Stage 3 — Civic / learning (west).** Library (-70,-28) 12×9 h9 gable;
Academy (-70,28) 12×9 h9 flat; Maker Space (-88,32) 10×8 h7 dome. Plain
`houses[]` entries — the kit handles heights generically. Correction to the
plan: the kit gives every house ONE window row; the second row is flat/hall/
shop only, so the Library (gable) has the standard single row despite its
12u width — verified by the counter (Library 18 = the standard gable count).
NOT built: west-street lamps/planters — no coordinates pinned in the proposal
(see Open items).

**Stage 4 — Park.** Growth B (-38,38) 8×8 h5 gable; Growth C (52,-28) 8×8 h5
porch. City Park (70,32) 40×25: pond disc r5 + centre stone + glow sprite;
4 benches facing the pond (north pair backrest north, south pair backrest
south); 3 `plazaLantern`s (58,22), (82,22), (70,44); ring path (4 walkPlane
segments around the pond — NOT one plane across it, which would lay cobble
over the water: the path plane sits at y 0.06, above the pond disc at y 0.04)
+ strip `walkPlane(1,20,70,10)` joining the east path; 6 park trees with
FIXED values (they must not consume the global `rnd()` sequence, or scatter
positions shift). The pond centre stone is NOT an occluder (small rock inside
a no-collision pond); only the fountain basin joins occluders.

## Audit method

`audit_stage234.py` adapts `stage1_audit.py` + `city_audit.py`, with two
corrections to the v24 audit's collision model (verified against the live v26
movement code, lines 982–983): (1) houses wider than 12u get collision
circles every 6u along x — the Hall (w18) is 3 centres, so v26 has **14**
radius-6 discs, not 12; (2) the centre-spacing rule is checked per-circle
(min distance between any two circles of different buildings ≥ 12u).
`houses[]`/`stalls[]` are parsed from the patched file and cross-checked
against the PROP list (audit what's built, not what's claimed). Scatter
positions are the real engine values from the node counter
(`mesh_count_234.js`, real three-r128), cross-checked against an independent
LCG replication (6.15e-05 u — the documented value, from the counter's
4-decimal rounding; CITY_AUDIT.md §3). Mesh reconciliation uses the
code-derived component table, not summed buckets — per-house buckets and
rect counts overcount by adjacency (grass tufts inside buckets/rects;
awning+posts outside the rect), same class as Stage 1's documented artefacts.

## Corrections made during this build (audit bugs, not game bugs)

- `Café` label: the build first wrote it as the JS escape `Caf\u00e9`; the
  audit parses raw source, so it now writes the literal `Café` (file is UTF-8).
- `Growth A`: the audit's expected list said "Growth home A" — the v26 file's
  label is "Growth A". Same for Stage 4: built labels are "Growth B"/"Growth C".
- LCG threshold was 1e-6; the documented match is 6.15e-05 u (4-decimal rounding).
- Plaza/park self-checks: a kit must not be checked against its own furniture
  (plaza vs its benches; park vs its trees/benches/pond).
- Inventory lists are cumulative per stage (Stage 3's first run missed the
  Stage 2 shops).
- Stage 4 anchor: the `});` anchor Stage 2 used was consumed by Stage 2's own
  replacement — Stage 4 anchors on the plaza IIFE close `})();` + comment.
- Stage 2's "no money" comment contained the word "money" and tripped the
  no-money grep — reworded to "no trading".

## Sign fix — 2026-11-17 evening (post-build, pre-deploy)

Teleport screenshot verification found a real defect: the **Academy and
Library showed no name sign** (Maker Space, Porch, Claude's Study did).
Root cause in the house kit: signs were placed at the FIXED offset
`h.z+4.15`, but the front face sits at `h.z + h.d/2`. For d=8 that is 0.15u
proud of the wall (fine); the new d=9 Library/Academy signs landed 0.35u
INSIDE the body and were invisible. Fix (R2 in `build_stage3.py`): the sign
now sits at `front+0.15` for every depth — byte-identical placement for d=8
houses and the Hall, and the two d=9 signs move out of the wall.

New shas (rebuilt + re-audited 2026-11-17 evening): Stage 3
`36941466…` (83,548 B), Stage 4 `cfc824dd…` (85,992 B). Audits re-run:
**0 fails** both stages; mesh counts unchanged (971+42 / 1051+46). All three
step diffs re-verified: apply cleanly `patch --fuzz=0`, reproduce the Stage 4
file byte-for-byte. The Stage 4 step diff is unchanged by the fix (the sign
line is identical in the Stage 3 and Stage 4 files).

Also resolved from the source (no change): the Academy roof "red block" is
the flat-roof kit's rooftop box (4×1.6×3, 0x7c2d12), standard on the Press
Office + Grok's Lab in live v26 — its bright top face is the sunset light,
not a wrong material. The east "hill" is Ziri's CRT Nook roof (v24, unchanged)
seen up close as the player walked into it — not terrain, not a tree (the
fixed v24 tree at (42,8) is a separate round orange canopy). Visual sign
re-check running on teleport staging
(https://hearth-build-pcpygu1qu-clbnodses-projects.vercel.app,
dpl_3j7Rcd79PZgtmtZZXsaPdNDXrEhx) — deploy waits on it.

## Open items / blockers

1. **West-street lamps/planters (Stage 3 §3): NOT built.** No coordinates are
   pinned in the proposal, so there is no executable spec. Needs pinned
   coordinates (or an explicit "skip") before anyone builds them.
2. **Mansard roof option: NOT built.** Mentioned as an option in the proposal,
   not pinned; all Stage 2–4 roofs use the existing kit.
3. **Park trees vs park footprint (spec quirk, not a build error).** The
   proposal pins the park at 40×25 (x 50..90) AND pins trees at (91,28) and
   (95,44), which stand 1u / 5u east of that footprint. The trees are built
   exactly where the proposal pins them; all their clearances pass (pond
   ≥13.0u, coin ≥13.6u, existing tree ≥19.9u). The footprint/tree mismatch is
   in the spec itself — flagging for the reviewers, not fixing by moving trees.
4. **No visual / browser verification of the new stages.** The node counter
   verifies the scene graph (meshes, positions, counts); nobody has seen the
   shops, plaza, civic buildings, or park rendered. Phone P1–P12 + measured
   FPS remain untested (as for v26). A browser screenshot pass is the next
   verification step before any deploy.
5. **Not deployed.** Owner 2026-11-17 17:15 ET: "Deploy when ready" — Stage 2–4
   game builds to deploy staged (api-45/46/47) once diffs built + audits pass +
   Muse verifies live between stages. The diffs + audits are now done; the
   deploy itself needs the owner's per-version go (per the standing approval
   rule) and the live verification between stages. P7 deploy is still gated
   separately (ChatGPT final gate + Claude re-review).
6. **Board drafts not posted.** `BOARD_DRAFT.md` holds the proposal texts in
   board-ready parts (<1900 chars each). Nothing posted — posting is the
   owner's / parent agent's call.

## Files (all under `~/workspace/game-collab-api/city-proposal/stage234/`)

- Builders: `build_stage2.py`, `build_stage3.py`, `build_stage4.py`
- Patched HTMLs: `hearth-3d-game-v2-v26s2.html`, `hearth-3d-game-v2-v26s2s3.html`,
  `hearth-3d-game-v2-v26s2s3s4.html`
- Step diffs: `v26-to-stage2.diff`, `v26s2-to-stage3.diff`, `v26s2s3-to-stage4.diff`
- Cumulative diffs: `v26-to-stage3.diff`, `v26-to-stage4.diff`
- Counter + specs: `mesh_count_234.js`, `spec_v26.json`, `spec_stage2.json`,
  `spec_stage3.json`, `spec_stage4.json`
- Counts: `counts_v26.json`, `counts_stage2.json`, `counts_stage3.json`, `counts_stage4.json`
- Audit: `audit_stage234.py`, `audit_stage2.log`, `audit_stage3.log`, `audit_stage4.log`,
  `results_stage2.json`, `results_stage3.json`, `results_stage4.json`
- Tables: `inventory.json` (+ `gen_inventory.py`), `SUMMARY.md`, `BOARD_DRAFT.md`
