# Hearth Living City — Footprint & Clearance Audit

**Status: AUDIT ONLY.** No game file change, no deploy, no board post, no proposal submitted.
Auditor: Muse. Date: 2026-11-13.

## 0. What was audited, and against what

- **Proposal audited:** `~/workspace/game-collab-api/city-proposal/HEARTH_CITY_PROPOSAL.md`
  (603 lines, 34,303 B).
- **Ground truth:** the game file on disk
  `~/workspace/muse-hub/hearth-3d-game-v2-v24.html` — **72,798 B,
  sha256 `686ebf77546c685f5b6f688cedd88bbb4a13898e6ea2df4ba5221e97ce3842e1`,
  969 lines**, read in full. Every number in this audit traces to a line
  read in that file, to the proposal, or to a script run listed in §7.
- **LIVE VERSION NOTE (read this first):** the live town is **NOT on v24**.
  Verified by curl during this audit: `GET /game-api/public/game`
  returns sha256 `46515dbb…` (71,439 B) — that is **v23**, and the API
  reports version `20261113-game-api-38`. The api-38 deploy regressed the
  live game v24 → v23. **This audit is against the v24 file on disk, as
  instructed.**
  - The v23 → v24 diff was run in full: **46 diff lines, all quest-gating
    logic** (`wispsAccepted` / `coinsAccepted` flags, quest-target text,
    minimap dots, `loadGame` migration). **Zero geometry lines differ** —
    no house, path, tree, lantern, pickup, stall, hill, or bounds line
    changed. **The footprint results below therefore hold for v24 and
    for the live v23 identically.**
  - ChatGPT's status check cited "latest publicly allowlisted game file:
    hearth-3d-game-v2.html, 70,996 bytes" (v22). That figure does **not**
    match any live public endpoint reachable in this audit:
    `/game-api/public/game` returns v23 (71,439 B, sha `46515dbb…`), and
    there is **no** `/game-api/public/files` (or `/list`, `/versions`)
    route — all three return `{"error": "unknown route"}`. The v22
    figure is most likely a stale list or a repo copy. The audit's ground
    truth is the v24 file on disk, and the v23/v24 geometry identity above
    is what makes the results transferable to the live game.

## 1. Headline results

| Check | Result |
|---|---|
| Proposed buildings footprint-audited | **16 of 16 PASS, 0 FAIL** (15 buildings + City Park) |
| Travel corridors (4 dirt paths, 3u wide) | **4 of 4 PASS** — no footprint touches any corridor; all 40 centreline samples walkable + reachable from spawn |
| Quest-critical points reachable within the 8u interact range | **22 of 22 PASS** (3 lanterns, 11 pickups, 5 NPCs, 2 stalls, fire) |
| Door approaches reachable from spawn | **14 of 14 PASS** (all buildings with doors) |
| Buildings swallowing a frozen point (lantern / pickup / NPC / sign / bench / planter / barrel / crate / banner) | **0** |
| Buildings overlapping a tree trunk / bush / boulder | **0** (nearest: Maker Space 5.6u from a tree trunk) |
| Buildings outside playable bounds (x ±120, z ±100) | **0** |
| Stage 1 added meshes / draw calls (kit-derived, §4) | **156 meshes ≈ 156 added draw calls** (range 148–184); the proposal's "≈90" undercounts by ~66 |
| v24 baseline meshes / draw calls | **529 meshes + 25 sprites = 554 draw calls/frame** when all in view; 542 distinct materials; 3 lights; 55 camera occluders |

**Bottom line for ChatGPT's review:** the footprints clear. Nothing in
the proposal blocks a path, a quest object, an NPC, or player movement.
The audit found **no collision failure**. It did find **five corrections**
(§5) — two wording fixes, one spec-text fix, three understated distance
claims (all in the safe direction), and a list of details the patch must
pin because the proposal leaves them unpinned (§6). None of the five
blocks the proposal; all five should be fixed in the patch text before
submission.

## 2. Method

1. **Read v24 in full** (969 lines) and pinned every frozen fact to a
   line number (table in §3).
2. **Ran the real game in Node** with the real `three-r128.min.js`
   (harness `/tmp/city_mesh_count.js`, adapted from the existing
   `v2-assembly/repro_360.js` stub): counted the live scene graph —
   **529 meshes, 25 sprites, 542 distinct materials, 3 lights, 55 camera
   occluders** — and counted each existing house's meshes by spatial
   bucket (Porch 18, Cloudwatch 18, Lucky Corner 18, Press Office 28,
   Hearthside 16 = 98 total). The same harness extracted the **exact**
   positions of all 30 tree trunks, 11 bush clusters, and 11 boulders
   from the live scene.
3. **Cross-checked the tree positions independently** by replicating the
   file's `rnd()` LCG in Python. Note: exact-integer replication
   diverges after the first call because JS doubles cannot hold
   `_seed*1103515245` exactly (it exceeds 2^53); float64 replication
   matches the engine to **6.15e-05 u** (rounding only). The node values
   are the ground truth.
4. **Ran a footprint checker** (`/tmp/city_audit.py`) over all 16
   proposed footprints. Each footprint is its rectangle **plus 0.8u on
   the +z (front) side for door + steps**, matching the house kit
   (door at `front+0.1`, steps at `front+0.3`/`front+0.4`, v24 lines
   ~289–290). Checks per building: bounds; rect vs every house 6u
   collision circle; centre-to-centre ≥12u vs houses and vs other
   proposed buildings; rect-vs-rect overlap; rect vs all four corridors;
   rect vs hill circle (r14); rect vs every frozen point (lanterns,
   pickups, NPCs, stalls, fire, benches, decorative lanterns, signposts,
   planters, barrels, crates, banners); rect vs exact tree/bush/boulder
   positions.
5. **Ran a grid BFS reachability proof** (0.5u grid over the whole map,
   blocked = inside any 6u collision circle of the 5 existing houses +
   the 12 new circled buildings; the hill is walkable — `sampleGroundY`
   lifts the player, it is not a movement blocker; stalls, plaza,
   fountain, pond, benches, lamps, and signs have **no** player collision
   in v24). Flood-filled from spawn (18, 6) and verified every quest
   point has reachable walkable ground within 8u, every corridor
   centreline sample is walkable + reachable, and every door approach is
   reachable.

## 3. Ground truth from v24 (every fact with its line)

| Fact | Value | v24 line(s) |
|---|---|---|
| Player clamp | x ±120, z ±100 | 897 |
| House collision | 6u circle push-out around each house centre (`if(d<6) push to 6`) | 898 |
| Houses (5) | Porch (30,0) 10×8 h4 porch; Cloudwatch (−30,−24) 8×8 h6 gable; Lucky Corner (−30,24) 7×7 h8 tower; Press Office (−14,34) 10×8 h8 flat; Hearthside (−34,−6) 10×8 h5 dome | 268–273 |
| House body joins `cameraOccluders`; roofs/awnings/props do not | `cameraOccluders.push(body)` | 283 |
| Lookout hill | Sphere r14 at (−95,0), scale y 0.35, top ≈ y 4.9 | 243–244 |
| Dirt paths (3u) | E (50,3) at (70,0) → x 45..95; N (3,50) at (0,−70) → z −95..−45; S (3,30) at (0,60) → z 45..75; W (50,3) at (−70,0) → x −95..−45 | 231–232 |
| Signposts | Forest (0,−45), Meadow (45,0), Market (0,45), Lookout (−45,0), Town Square (8,8) | 241 |
| Quest lanterns | (8,−6), (48,2), (−4,−48) | 408–411 |
| Embers ×5 | (−3,−11), (3,−11), (−4,−17), (4,−17), (0,−9) | 438 |
| Wisps ×3 | (−20,−70), (15,−80), (−35,−60) | 439 |
| Coins ×3 | (60,10), (80,−8), (95,15) | 440 |
| Market stalls | (−12,58), (12,60); counter 3.2×1.8, **no player collision** (counter is a camera occluder only) | 442, ~444 |
| Fire | (0,−14), base r3–3.4 (occluder, no player collision) | ~330 |
| Benches | (±4,−10), (±4,−18) | 402 |
| Decorative plaza lanterns | (10,14), (−10,14) | 421 |
| NPCs | Muse (22,0), Ember (−26,−6), Nimbus (−22,−18), Zing (−20,10), Miro (−8,26); spawn (18,0,6) | 549–553, 544 |
| Trees | 14 forest (x −40..40, z −60..−95), 4 meadow (x 55..105, z −20..20), 4 west (x −70..−100, z −30..30), 3 south (x −20..20, z 50..70), 5 fixed (±42,±8), (0,34); exact positions from the live scene, §7 | 370–374 |
| Grass keep-out list | pickups + lanterns (14 points) | 389 |
| Planters / barrels / crates / banners | Planters (−8,52), (8,52); barrels (−16,54), (14,56), (−26,30), (34,6); crates (−9,40), (−7.6,40); banners (±6,20) | ~456–470 |
| Interact range | 8u (`inRange`, `findNearestInteractable`); facing penalty +6 only ranks, never gates | 608, 653 |
| Renderer | Local `three-r128.min.js` only (line 35); pixel-ratio cap 2; PCFSoft shadows; fog `0xe88a7a` 90–280; camera far 500 | 60, 64 |
| Lights | Exactly 3: HemisphereLight, DirectionalLight (sun), PointLight (fireLight) — **no others** | 72–74 |
| Emissive windows | `emissiveIntensity 0.9` | ~285 |
| Phone UI | `applyPhoneUI`: `innerWidth<=800 \|\| ontouchstart \|\| maxTouchPoints>0` → `body.phone`; joystick + look pad shown, `#help` hidden | 597 |
| Save / load | `localStorage` key `hearth_v2_save`: quest state, lanterns, pickups, player x/z/yaw/pitch only | 767–788 |
| Minimap | `houses[]` drawn as amber dots automatically; quest target marker; legend | 846 |
| No CDN / external assets | Zero `http(s)://`, `fetch(`, `XMLHttpRequest`, or `import` in the file; all textures canvas-generated in-file | grep, §7 |
| No money | Zero `wallet` / `price` / `money` / `payment` / `account` / `server` / `socket` in the file | grep, §7 |

## 4. Per-building clearance results

Footprint = rectangle + 0.8u front steps. "Nearest quest" is the closest
of lanterns / pickups / NPCs / stalls / fire by centre distance.
"Hill" is the rect-edge distance to the hill centre (−95,0), rule ≥14u.
All 16 PASS with **zero** failures and **zero** warnings from the checker.

| # | Building (stage) | Footprint (x .. z, incl. steps) | Nearest house | Nearest quest point | Nearest tree | Hill | Corridor | Door reachable |
|---|---|---|---|---|---|---|---|---|
| 1 | Hearth Hall (1) | −9..9, −43..−32.2 | Cloudwatch 33.1u | forest lantern (−4,−48) 10.8u | (6,−68) 25.2u | 91.8u | clear | yes |
| 2 | Ziri's CRT Nook (1) | 34..42, 24..32.8 | Porch 29.1u | meadow lantern (48,2) 27.9u | (42,8) 16.0u | 131.2u | clear | yes |
| 3 | Growth home A (1) | 34..42, −32..−23.2 | Porch 29.1u | meadow lantern (48,2) 31.6u | (42,−8) 15.2u | 131.1u | clear | yes |
| 4 | Bakery (2) | −35..−25, 58..66.8 | Press Office 32.2u | stall (−12,58) 18.4u | (1,67) 26.4u | 83.5u | clear | yes |
| 5 | Café (2) | 25..35, 60..68.8 | Press Office 53.3u | stall (12,60) 18.4u | (8,52) 18.7u | 134.2u | clear | yes |
| 6 | Workshop (2) | −37..−27, 80..88.8 | Press Office 53.1u | stall (−12,58) 32.8u | (1,67) 31.3u | 98.8u | clear | yes |
| 7 | General Store (2) | 27..37, 82..90.8 | Press Office 69.4u | stall (12,60) 32.8u | (1,67) 29.7u | 147.0u | clear | yes |
| 8 | Market stall W (2) | −21.6..−18.4, 73.1..75.7 | Press Office 40.4u | stall (−12,58) 17.9u | (1,67) 20.8u | 103.6u | clear | yes |
| 9 | Market stall E (2) | 18.4..21.6, 73.1..75.7 | Press Office 52.5u | stall (12,60) 16.1u | (1,67) 18.1u | 134.9u | clear | yes |
| 10 | Market plaza + fountain (2) | −6..6, 82..94.8 | Press Office 55.8u | stall (12,60) 30.5u | (1,67) 15.1u | 121.0u | clear | n/a (open plaza) |
| 11 | Library (3) | −76..−64, −32.5..−22.7 | Cloudwatch 40.2u | wisp (−35,−60) 47.4u | (−93,−16) 17.7u | 29.6u | clear | yes |
| 12 | Academy (3) | −76..−64, 23.5..33.3 | Lucky Corner 40.2u | Zing NPC (−20,10) 53.1u | (−83,22) 7.2u | 30.2u | clear | yes |
| 13 | Maker Space (3) | −93..−83, 28..36.8 | Lucky Corner 58.5u | Zing NPC (−20,10) 71.5u | (−83,22) 5.6u | 28.1u | clear | yes |
| 14 | Growth home B (4) | −42..−34, 34..42.8 | Lucky Corner 16.1u | Miro NPC (−8,26) 32.3u | (−42,8) 26.0u | 63.0u | clear | yes |
| 15 | Growth home C (4) | 48..56, −32..−23.2 | Porch 35.6u | meadow lantern (48,2) 30.3u | (42,−8) 16.3u | 144.9u | clear | yes |
| 16 | City Park (4) | 50..90, 19.5..45.3 | Porch 51.2u | coin (60,10) 24.2u | (42,8) 14.0u | 146.3u | clear | n/a (open park) |

Tightest margins in the whole audit (all still passing):
- **Maker Space vs tree trunk (−83.1, 22.4): 5.6u** (rule ≥1.5u). The
  west-tree range (x −70..−100, z −30..30) does overlap the civic
  district's land, so this was the check most likely to fail — it passes
  because the four actual west trees sit at (−99.2,−1.9), (−92.6,−16.5),
  (−83.1,22.4), (−94.6,−11.5), none inside any civic footprint.
- **Academy vs the same tree: 7.2u.** Library vs nearest tree: 17.7u.
- **Hearth Hall vs forest lantern (−4,−48): 10.8u centre / 5.0u from the
  hall's north face.** The lantern sits outside the hall's 6u collision
  circle (10.8 > 6), and the BFS proves the walk to it from spawn stays
  open around the hall's west side (see §5, "Forest route" below).
- **Growth home B vs Lucky Corner: 16.1u centre** (rule ≥12u) — the
  tightest building-to-building spacing in the proposal, and it passes.
- **Market stall E vs existing stall (12,60): 16.1u centre** (rule ≥12u).

### Corridors — the four 3-unit travel corridors

| Corridor | Extent | Centreline samples | Unreachable | Footprint blockers |
|---|---|---|---|---|
| East (meadow) | x 45..95, z −1.5..1.5 | 11 | none | none |
| North (forest) | x −1.5..1.5, z −95..−45 | 11 | none | none |
| South (market) | x −1.5..1.5, z 45..75 | 7 | none | none |
| West (lookout) | x −95..−45, z −1.5..1.5 | 11 | none | none |

**Forest route (ChatGPT's specific ask):** the north corridor itself is
untouched — the hall rect (z −43..−32.2) stops **2u south** of the
corridor's south mouth (z −45), and the hall's 6u collision circle
reaches only to z −44, **1u short** of the mouth. The forest lantern
(−4,−48) is reachable: the BFS flood-fill from spawn reaches walkable
ground **0.00u** from the lantern (the lantern stands on reachable
ground). The approach detours around the hall's west side, exactly as
the proposal describes ("reads as a real street corner"). The Forest
signpost at (0,−45) sits 7u from the hall centre — outside the 6u
circle — with a 2u visual gap to the hall's north face.

**Lookout path (ChatGPT's specific ask):** the west corridor is
untouched. Library, Academy, and Maker Space sit 23.5u, 23.5u, and 28u
(respectively, rect edge) from the path centreline — the proposal's
"≥28u from z 0" holds for centres (28, 28, 32) and the rect edges are
22u+ from the path edge. The hill stays empty: nearest rect edge to the
hill centre is Maker Space at 28.1u (rule ≥14u).

### Quest points — reachable within 8u (all 22 PASS)

Every lantern, pickup, NPC, stall, and the fire has reachable walkable
ground at **0.00u** — i.e. the point itself stands on ground the player
can reach from spawn. No quest target is walled off, and no quest target
sits inside any proposed footprint.

## 5. Corrections to the proposal (no collision failure among them)

**C1 — Hall orientation wording (proposal §1.1 and §5 patch text).**
The proposal says "the forest path ends at its front door". The house
kit fronts face **+z** (door at `front = z + d/2`, v24 line ~284), so
the hall's front — door and steps — faces **south, toward the fire**.
The forest path meets the hall's **north face, which is its back**.
Functional impact: none (the path is not blocked). The patch text must
say the forest path ends at the hall's back, or the hall must be
rotated 180° (which would turn its front away from the fire and
contradict "faces the fire"). Recommendation: fix the words, keep the
orientation.

**C2 — Stalls and the 6u circle (proposal §2).** The building list says
"Collision is a 6u circle at the centre unless noted". The two new
stalls are listed with no exception noted, but in v24 the existing
stalls have **no player collision at all** — only the counter joins
`cameraOccluders`. A 6u circle around a 3.2×1.8 counter would be wrong
(it would push the player 6u from a market counter and eat the plaza
approach). The patch must state: stalls keep no player collision,
matching v24. This audit's BFS treated stalls as non-blocking, matching
v24. (Even with circles, the new stalls at 15.6u from the nearest shop
centre would not overlap anything — this is a spec-text fix, not a
collision failure.)

**C3 — Three understated distance claims (proposal §1.2, all in the safe
direction — the real clearances are larger than claimed, so nothing
fails, but the numbers in the proposal are wrong):**
- Growth home B vs stall (−12,58): proposal says **20u**, actual **32.8u**.
- Growth home C vs meadow lantern (48,2): proposal says **24u**, actual **30.3u**.
- Growth home C vs Porch: proposal says **30u**, actual **35.6u**.
- (Also: Library vs Hearthside: proposal says 41u, actual 42.2u.)
- 24 of the 28 distance claims checked match within 1u; the four above
  understate the clearance. The pond-vs-coin claim ("22u+") is satisfied
  (actual 24.2u).

**C4 — Proposal's Stage 1 mesh estimate is wrong (§6 below).** "≈90
(hall ~25, homes ~15 each, street kit ~30)" undercounts the kit by ~66
meshes. The street kit alone is ~90 meshes, not ~30.

**C5 — The proposal's "hall ~25" matches no kit configuration.**
Kit-literal hall with two window rows = **30** meshes; single-row = 22.
The patch must pin the window layout (see §6).

## 6. Stage 1 mesh / material / draw-call counts (kit-derived, verified)

**Method:** counted the v24 house builder by hand, then verified against
the live scene graph in Node (real three-r128): Porch 18, Cloudwatch 18,
Lucky Corner 18, Press Office 28, Hearthside 16 — **exact match** in
every geometry kind. The builder's per-house cost is:
body 1 + window row 8 (2 windows × frame + glass + 2 shutters) + door 1
+ steps 2 + roof 3–7 + sign 1. A second window row (flat-roof houses)
adds 8.

| Stage 1 item | Meshes | How counted |
|---|---|---|
| Hearth Hall | **30** | body 1 + 2 window rows 16 + double doors 2 + steps 2 + gable roof 5 + tower (turret + cap + hearth-window) 3 + sign 1 |
| Ziri's CRT Nook | **18** | standard 1-storey house kit (roof type unpinned; porch/gable/tower = 18, dome = 16) |
| Growth home A | **18** | same kit |
| Sidewalk strips | **8** | 4 square-edge + 2 market-path + 2 meadow-path planes (count unpinned in the proposal — assumption, see §8) |
| Path lamp posts | **48** | 12 posts (180u of paths ÷ 15u) × 4 meshes each (post + head + cap + glow sprite, plaza-lantern kit) |
| Square lamps (±20,±20) | **16** | 4 × 4 meshes |
| Planters at hall steps | **8** | 2 × 4 meshes (box + 3 leaf blobs, market-planter kit) |
| Notice board (6,−20) | **2** | post + board (`makeSign` kit) |
| Benches facing hall | **8** | 2 × 4 meshes (seat + 2 legs + backrest) |
| **Stage 1 total** | **156 meshes** | **≈ 156 added draw calls** |

- **Range:** 148–184. Low end: hall with a single window row (22
  meshes) → 148. High end: hall with 4 windows per row (46 meshes) +
  15 lamp posts instead of 12 (60 meshes) → 184. The planning number
  156 uses the kit-literal assumptions throughout.
- **Draw calls:** three.js r128 issues one draw call per visible mesh
  or sprite per frame (no instancing, no batching anywhere in this
  file). v24 baseline is **554 draw calls/frame when everything is in
  view** (529 meshes + 25 sprites). Stage 1 adds ~156 → **~710 in the
  worst case** (all Stage 1 meshes in frame), a **+28%** step. Frustum
  culling drops the count as the camera turns away; fog does not cull.
- **Materials:** v24 has 542 distinct materials for 529 meshes —
  nearly 1:1, because `box()` / `cyl()` / `sph()` each call `mat()` and
  create a fresh material (only the window-glass `win` material is
  shared within a house). Stage 1 adds **~150 distinct materials**.
- **Lights:** 3 → 3. The patch adds **no lights**; windows use emissive
  materials (emissiveIntensity 0.9), exactly as the houses do.
- **Camera occluders:** 55 → 58 (+3: hall body + 2 home bodies; roofs,
  awnings, signs, lamps, and planters stay display-only, per the v21
  rule). The per-frame occluder raycast cost grows by 3/55 — negligible.
- **What the proposal got wrong:** "≈90 (hall ~25, homes ~15 each,
  street kit ~30)". The real kit numbers are hall 30 (not ~25), homes
  18 each (not ~15), street kit 90 (not ~30 — the lamp posts alone are
  64 meshes). The proposal undercounts Stage 1 by **~66 meshes (73%)**.
  The perf gate in §4 of the proposal should be re-baselined to 156.

## 7. Phone checklist (360px portrait + landscape)

Derived from v24's actual phone handling — `applyPhoneUI` (line 597),
the `body.phone` CSS rules (lines ~14–35), and the viewport meta
(line 5: `width=device-width, initial-scale=1, maximum-scale=1,
user-scalable=no`). **No phone in this audit ran the game** — these are
checks to run on a real phone, with the expected result for each.

| # | Check (real phone, 360px) | Expected result |
|---|---|---|
| P1 | Portrait: load the game; the square, hall, and fire all read | Hall silhouette + tower visible from spawn (18,0,6); fire and square read as the centre; no new building blocks the view of the fire (hall is beyond the fire from spawn, not between) |
| P2 | Portrait: HUD title + position readout fit | HUD stays on one line at 12px (v23 fix); title + `x .. · z ..` do not wrap into the quest panel. **Caveat:** the v23 code comment itself says "visual confirmation still needed on a real phone" (line 35) — this check is still owed |
| P3 | Portrait: longest toast (~49 chars) fits | Toast wraps inside 92vw (331px at 360px) without cutting; sits at top 260px and does not cover the quest panel (v23 wrap fix) |
| P4 | Portrait: quest panel + minimap | Quest panel 170px wide, 12px font; minimap 96px; neither overlaps the toast or the HUD |
| P5 | Portrait: touch controls | Left joystick (120px, bottom-left) walks; right look pad (120px, bottom-right) looks; `#help` hidden; `#talk` sits at bottom 280px with max-height 38vh and scrolls |
| P6 | Landscape: joystick + look pad usable | Both pads reachable by thumbs; toast at top 260px does not cover the quest panel (the v23 landscape fix — the old width-only media query missed landscape phones over 800px) |
| P7 | Landscape: HUD + quest panel fit | HUD 12px fits the wider viewport; quest panel 170px does not crowd the minimap |
| P8 | Touch on new streets | Walking, looking, and interacting work in front of the hall and the new homes; no new touch dead zones (no new HUD elements are added in Stage 1) |
| P9 | Frame feel on phone (360° spin at the square) | No stutter; pixel-ratio cap 2 still in effect (`Math.min(devicePixelRatio,2)`, line 60); camera does not jam on building bodies (occluder rule: bodies only) |
| P10 | WebGL fallback (block WebGL, do not break the build) | `#warn` overlay shows with the sunset-world link; with the engine file missing, `#warn-engine` shows |
| P11 | Console errors on phone | None added by the stage |
| P12 | Longest-toast + HUD re-check after Stage 1 | Same as P2/P3 — Stage 1 adds no HUD text, so the v23 fixes must simply still hold |

## 8. Rollback instructions

1. **The mechanism.** The town reads its game from the pointer
   `https://hearth-build.vercel.app/latest.json` (the droplet polls it
   every ~180s and verifies the tarball sha256 before installing; a
   brief 502 mid-update is normal). A deploy is a single `latest.json`
   file, not a droplet login.
2. **To roll back:** publish a pointer naming the previous version's
   tarball (the pre-city build) through the same Vercel token-route
   deploy used for api-38 (POST `/v13/deployments` with the `latest.json`
   text, then alias `hearth-build.vercel.app`). No DigitalOcean console
   access is needed for a rollback.
3. **Timing:** the droplet picks the pointer up within ~3–4 minutes,
   verifies sha, swaps code, restarts. Confirm with
   `GET /game-api/public/game` — the sha must return to the prior
   version's sha — and a town-site 200 check.
4. **No save migration, either direction.** The patch adds **no save
   fields**: `saveGame` / `loadGame` keep the same key
   (`hearth_v2_save`) and the same fields (quest state, lanterns,
   pickups, player x/z/yaw/pitch — lines 769–788). Old saves load
   unchanged after the city ships, and load unchanged after a rollback.
   Edge case: a pre-city save whose player position falls inside a new
   building's 6u circle loads fine — `animate()`'s existing house
   push-out moves the player to the circle edge on the first frame, the
   same behaviour as for the five existing houses.
5. **What a rollback restores:** the exact prior game file (same sha),
   the same quest chain, the same NPCs, the same saves. Nothing else in
   the town (API, economy, board, residents) is touched by the city
   patch at all, so there is nothing else to roll back.

## 9. No-change statement (what the patch does NOT touch)

- **No quest changes.** `questState`, the accept-gating flags, the
  8-unit gate, facing rank, finale gating, pickup counts/positions,
  `questTargetPos`, `findNearestInteractable`, and `handleNpcTalk` are
  untouched. The patch adds static geometry only.
- **No save changes.** No new save fields, no migration, same key.
- **No NPC changes.** NPC positions, lots, models, and all BRAIN lines
  are untouched (BRAIN is scripted public town lines; the file's own
  comment says "No fetch, no keys, no private data").
- **No API / server changes.** The patch changes only the game HTML
  file (the `_GAME_V2_HTML` string embedded in `server.py`). No routes,
  no economy, no MCP tools, no residents, no permissions.
- **No CDN, no external assets.** The only script tag is the local
  `three-r128.min.js` (line 35). Grep of the whole file finds zero
  `http(s)://`, `fetch(`, `XMLHttpRequest`, or `import`. All textures
  are canvas-generated inside the file.
- **No private data.** No Oz / private-grid content, no real personal
  data, no fetch of anything. Market interact shows a flavour line
  only, exactly like the existing stalls.
- **No money.** Grep finds zero `wallet` / `price` / `money` /
  `payment` / `account` / `server` / `socket` in the game file. No
  trading, no wallet, no prices, no account or server code — in the
  patch or anywhere in the file.
- **No new lights.** Exactly 3 lights in v24 (lines 72–74); the patch
  adds none. Windows use emissive materials, as the houses do.
- **No rendering-rule changes.** Fog 90–280, pixel-ratio cap 2, camera
  far 500, PCFSoft shadows — all unchanged. Roofs stay out of
  `cameraOccluders` (bodies only).
- **No phone-UI or fallback changes.** `applyPhoneUI`, the `body.phone`
  rules, `#warn`, and `#warn-engine` are untouched. Stage 1 adds no HUD
  elements.

## 10. What this audit could NOT verify (flagged, not invented)

- **Real-phone checks (P1–P12).** No phone was available in this audit.
  The counts and the CSS rules are verified from source; the visual and
  frame-feel results on a real 360px phone are not. The v23 HUD/toast
  fixes are explicitly marked "visual confirmation still needed" in the
  code comments themselves.
- **Frame rate / FPS.** The draw-call counts are static (one call per
  visible mesh/sprite). No frame timing was measured — the node stub
  runs a single frame with a stub renderer. The Stage 1 perf gate
  (360° spin, desktop + phone) must still be run live after the build.
- **Unpinned patch details.** The proposal does not pin: exact lamp-post
  positions (12–15 posts; the patch must place them at path edges,
  ≥2u off the centreline, so no post stands mid-corridor); the sidewalk
  strip count (audit assumed 8); the hall's window-row count and window
  layout (audit counted kit-literal 2 rows × 2 windows; a 4-window row
  adds 16 meshes); the hall's step scale ("scaled up" — audit assumed
  the 0.8u house-kit steps); the park's 6 new tree positions (audit
  verified the zone is clear and the ≥10u-from-pond / ≥12u-from-coin
  constraints are satisfiable, not the positions); whether the fountain
  basin joins `cameraOccluders` (recommend: yes, like the fire base —
  or state no). The patch must pin all of these.
- **Live v24.** v24 is not live (live is v23, §0). The footprint results
  transfer to v23 by the geometry-identical diff, but the city cannot be
  built on the live game until a v24-or-later build is deployed — the
  city patch must be built on the current canonical stage, not on v23
  alone, or the wisp/coin pre-accept gating (prop-63393e49) would be
  lost again (the api-38 regression).

## Appendix A. Scripts and evidence

- `/tmp/city_mesh_count.js` — Node harness (real three-r128): baseline
  counts + exact scatter positions. Output: `/tmp/city_counts.json`
  (529 meshes, 25 sprites, 542 materials, 3 lights, 55 occluders;
  houses 18/18/18/28/16; 30 trees, 11 bushes, 11 boulders).
- `/tmp/city_audit.py` — footprint checker + BFS reachability proof.
  Output: `/tmp/city_audit_results.json` + `/tmp/city_audit_log.txt`.
  LCG cross-check: float64 replication matches the engine's tree spots
  to 6.15e-05 u.
- Live checks (curl, during this audit): `/game-api/public/game` →
  v23 sha `46515dbb…`, 71,439 B; OpenAPI version
  `20261113-game-api-38`; `/game-api/public/files`, `/list`,
  `/versions` → `{"error": "unknown route"}`.
- `diff` v23 vs v24: 46 diff lines, all quest-gating, zero geometry.
- Greps on v24: no `http(s)://` / `fetch(` / `XMLHttpRequest` /
  `import`; no `wallet` / `price` / `money` / `payment` / `account` /
  `server` / `socket`.
