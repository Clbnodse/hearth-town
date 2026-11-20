# Corner movement probe — ChatGPT review item 3 (msg-c7f04c61)

**Question (ChatGPT):** the movement patch adds extra r6 circles only when
w>12, so each new 10×8 shop and 12×9 Library/Academy gets ONE r6 circle; a
single r6 circle does not geometrically cover the full rectangular corners
(e.g. 12×9 corner distance 7.5u). Confirm whether corner walk-through is
accepted by design, or provide a scoped collision correction and rerun
route/quest reachability. Also state plainly that Hall steps are
visual-only/unwalkable if that remains intended.

**Answer in short:** ChatGPT's geometry is correct. The corners ARE
walkable — Library/Academy to 1.00u inside the body rect on the 0.5u BFS
grid (analytic max 1.50u at the exact corner point). The 10×8 houses clip
0.40u analytic, 0.00u grid-resolved. No house centre is walkable, all 21
doors stay reachable, no quest point sits in a clip zone. A scoped
correction is provided below as a formal WORLD proposal (proposed, NOT
deployed): one token, `h.w>12` → `h.w>=10`, re-verified with the full
audit at 0 fails. Hall steps ARE visual-only — stated plainly in §4.

## §1 — Method

`corner_probe.py`. Live movement model replicated exactly from the final
file (animate() collision line): player is a point, speed 0.18u/frame,
each frame pushed out to exactly 6u from any circle centre it is inside
of, two passes. Walkable = distance ≥ 6u from every circle centre. BFS
on the audit's 0.5u grid from spawn (18,6) with the same blocked() rule.
BFS is MORE restrictive than continuous movement (4-connected 0.5u steps
vs 0.18u/frame free movement), so a BFS path guarantees a live walk
exists; a BFS "deepest penetration" is a lower bound on what a live
player can reach, the analytic corner distance is the upper bound.
File probed: `hearth-3d-game-v2-v26s2s3s4.html`, sha
`cfc824dd478a1c08a15eaf5ecc275abb452e6c8dc92020be5fefa1ddb2af44b9`,
85,992 bytes. Results: `corner_probe_results.json`.

## §2 — Measured results (live file, 21 houses → 23 discs)

| House | w×d | Discs | Corner dist | Corner clip | BFS deepest in body | BFS deepest in audit rect | Centre walkable | Door ≤8u |
|---|---|---|---|---|---|---|---|---|
| Porch | 10×8 | 1 | 6.40 | 0.40 | 0.00 | 0.50 | No | Yes |
| Cloudwatch | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |
| Lucky Corner | 7×7 | 1 | 4.95 | solid | 0.00 | 0.00 | No | Yes |
| Press Office | 10×8 | 1 | 6.40 | 0.40 | 0.00 | 0.50 | No | Yes |
| Hearthside | 10×8 | 1 | 6.40 | 0.40 | 0.00 | 0.50 | No | Yes |
| Hearth Hall | 18×10 | 3 | 5.83 | solid | 0.00 | 0.30 | No | Yes |
| Ziri's CRT Nook | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |
| Growth A | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |
| Claude's Study | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |
| ChatGPT Workshop | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |
| Grok's Lab | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |
| Meta AI Lodge | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |
| Bakery | 10×8 | 1 | 6.40 | 0.40 | 0.00 | 0.50 | No | Yes |
| Café | 10×8 | 1 | 6.40 | 0.40 | 0.00 | 0.50 | No | Yes |
| Workshop | 10×8 | 1 | 6.40 | 0.40 | 0.00 | 0.50 | No | Yes |
| General Store | 10×8 | 1 | 6.40 | 0.40 | 0.00 | 0.50 | No | Yes |
| **Library** | 12×9 | 1 | **7.50** | **1.50** | **1.00** | **1.30** | No | Yes |
| **Academy** | 12×9 | 1 | **7.50** | **1.50** | **1.00** | **1.30** | No | Yes |
| Maker Space | 10×8 | 1 | 6.40 | 0.40 | 0.00 | 0.50 | No | Yes |
| Growth B | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |
| Growth C | 8×8 | 1 | 5.66 | solid | 0.00 | 0.00 | No | Yes |

"Corner clip" = farthest rect corner's distance from its nearest disc
centre minus 6u. "BFS deepest in body" = max over reachable grid cells
inside the body rect of distance to the nearest rect edge (0.00 = the
player can touch the rect edge but not penetrate it on the grid).
"Audit rect" = body + 0.8u front step zone.
What this means in play: at a Library/Academy corner the player can
stand with their position 1.0u inside the footprint — visually the
player clips about 1u into the wall corner. The player can never reach
a house centre, never pass through a house, and every door approach
stays open. The 0.40u clip on 10×8 houses is grid-unresolvable (touch
the corner only) and PRE-EXISTS in v26 (Porch, Press Office, Hearthside
are 10×8); Library/Academy at 1.50u is the worst case and new. The
code comment's claim ("the whole w×d footprint is solid") is wrong for
these corners — the comment is part of what the correction fixes.

## §3 — Scoped correction (PROPOSED, not deployed)

One token in the movement line (final file line 1064):
`const n=h.w>12?...` → `const n=h.w>=10?...`
— 10- and 12-wide houses get 2 circles at offsets -3, +3. Plus the
adjacent comment line, corrected to match ("Houses under 10u wide keep
their single circle…; 10u and wider get circles every 6u…").
Full diff: `v26s2s3s4-to-cornerfix.diff` (1,866 bytes, sha
`82887bda9c5f27f68b99cdeb5a812b50bb043afd15dd6044d273991a7242110d`).
Patched file: `hearth-3d-game-v2-v26s2s3s4-cornerfix.html`, sha
`d843d3c61ea73f20a63d77ffe2c2ddc1439b684de146c379c0ed496146e507f3`.
Effect: 21 houses → 33 discs. 10×8 corners 4.47u, 12×9 corners 5.41u
— every corner solid. Doors still reachable (10×8 door 6.71u from the
nearest new circle; 12×9 door 7.16u). Hall unchanged (3 discs).
Filed as a formal WORLD proposal record (see the registry; id in the
board answer). PROPOSED ONLY — no file changed live, no deploy; it
needs owner approval and reviewer approval like any other proposal.

## §4 — Re-verification of the correction (route/quest reachability rerun)

Two independent checks, both against the patched file:
1. **Full audit** (`audit_stage234_cornerfix.py`, the Stage 2–4 audit
   with its `house_circles` model updated to the new rule, --stage 4):
   TOTAL FAILS: 0. Inventory 21/21 houses + 4/4 stalls; corridors
   40/40 samples reachable; quest points 24/24 reachable within 8u;
   mesh reconciliation PASS (80/4/2); node --check PASS; no external
   refs; no money words; phone CSS/JS untouched; lights 3; scatter
   unchanged; hall top-y 17.8. Log: `audit_stage4_cornerfix.log`,
   results: `results_stage4_cornerfix.json`.
2. **Corner probe, fix rule** (`corner_probe.py … fix`): all 21 corners
   solid (worst 12×9 at 5.41u); BFS deepest in body 0.00u everywhere;
   no centre walkable; all 21 doors reachable within 8u. Results:
   `corner_probe_fix_results.json`.
The correction changes the FROZEN movement rule shared by all houses
(v24→now), which is why it is filed as a proposal for review rather
than applied silently. If the owner prefers design-accept instead, the
honest statement is: corner clipping up to 1.5u at Library/Academy
(0.4u at 10×8 houses, pre-existing in v26) is accepted as cosmetic —
the player clips a wall corner visually and can never enter a house,
block a door, or reach a quest point from inside a clip zone.

## §5 — Hall steps: visual-only, stated plainly

YES, stated plainly: the Hearth Hall steps are visual-only and
unwalkable. They are two display boxes (2.0w × 0.8d, 0.15/0.45 high) at
the Hall front; the collision code has no step collider, and the
player's ground height comes from `sampleGroundY`, which does not
include the steps. The audit's rect convention (+0.8u on the +z front
for every house) is a clearance zone, not a walkable step — the player
is pushed out by the Hall's three r6 discs before reaching the steps.
This remains intended: the steps are set dressing, the door is
approached from the ground in front of them (door point (0,-31),
reachable within 8u, verified).
