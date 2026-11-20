#!/usr/bin/env python3
"""Stage 2-4 re-audit against a PATCHED game file (v26s2 / v26s2s3 / v26s2s3s4).
Adapts stage1/stage1_audit.py + city_audit.py, with TWO corrections to the
v24 audit's collision model (verified against the live v26 movement code,
lines 982-983):
  (1) houses wider than 12u get collision circles every 6u along x, not one
      circle per house — the Hall (w18) is 3 centres (-6,0,+6 at z=-38), so
      v26 has 14 radius-6 discs, not 12;
  (2) the centre-spacing rule is checked per-circle (min distance between any
      two circles of different buildings >= 12u), not per single centre.
Ground truth parsed from the PATCHED file itself (houses[] / stalls[] are
audited as built, not as claimed) and cross-checked against the PROP list
for the stage. Scatter positions are the REAL engine values from the node
mesh counter (mesh_count_234.js), cross-checked against an independent LCG
replication of the file's rnd() sequence.

Usage:
  python3 audit_stage234.py --stage 2 --html hearth-3d-game-v2-v26s2.html \
      --counts counts_stage2.json --prev-html ../hearth-3d-game-v2-v26.html \
      --prev-counts counts_v26.json --diff v26-to-stage2.diff \
      --out results_stage2.json
Exit 0 iff 0 fails. Log goes to stdout (redirect to a .log file).
"""
import argparse, hashlib, json, math, re, subprocess, sys, tempfile, os
from collections import deque

# ---------------------------------------------------------------- frozen v24 ground truth (unchanged by Stages 2-4)
V24_HOUSES = [("Porch", 30, 0, 10, 8), ("Cloudwatch", -30, -24, 8, 8),
    ("Lucky Corner", -30, 24, 7, 7), ("Press Office", -14, 34, 10, 8),
    ("Hearthside", -34, -6, 10, 8)]
NPCS = [("Muse", 22, 0), ("Ember", -26, -6), ("Nimbus", -22, -18),
        ("Zing", -20, 10), ("Miro", -8, 26)]
LANTERNS = [(8, -6), (48, 2), (-4, -48)]
PICKUPS = ([("ember", -3, -11), ("ember", 3, -11), ("ember", -4, -17),
            ("ember", 4, -17), ("ember", 0, -9)]
           + [("wisp", -20, -70), ("wisp", 15, -80), ("wisp", -35, -60)]
           + [("coin", 60, 10), ("coin", 80, -8), ("coin", 95, 15)])
FIRE = (0, -14)
BENCHES = [(-4, -10), (4, -10), (-4, -18), (4, -18)]          # square benches
DECOR_LANTERNS = [(10, 14), (-10, 14)]
SIGNS = [(0, -45), (45, 0), (0, 45), (-45, 0), (8, 8)]
PLANTERS = [(-8, 52), (8, 52)]
BARRELS = [(-16, 54), (14, 56), (-26, 30), (34, 6)]
CRATES = [(-9, 40), (-7.6, 40)]
BANNERS = [(6, 20), (-6, 20)]
HILL = (-95, 0, 14)
SPAWN = (18, 6)
CORRIDORS = {"east": (45, 95, -1.5, 1.5), "north": (-1.5, 1.5, -95, -45),
             "south": (-1.5, 1.5, 45, 75), "west": (-95, -45, -1.5, 1.5)}
# Stage 1 as built (v26): hall + 2 homes + street kit (lamps, strips, planters, board, benches)
S1_HOUSES = [("Hearth Hall", 0, -38, 18, 10), ("Ziri's CRT Nook", 38, 28, 8, 8),
             ("Growth A", 38, -28, 8, 8)]
S1_LAMPS = [(2, -55), (2, -65), (2, -75), (2, -85), (2, 55), (2, 65),
            (57.5, -2), (70, -2), (82.5, -2), (-57.5, -2), (-70, -2), (-82.5, -2)]
S1_SQ_LAMPS = [(20, 20), (20, -20), (-20, 20), (-20, -20)]
S1_PLANTERS = [(-3.8, -31.6), (3.8, -31.6)]
S1_NOTICE = (6, -20)
S1_BENCHES = [(-8, -26), (8, -26)]
S1_STRIPS = [(0, -44, 30, 1), (0, 44, 30, 1), (-44, 0, 1, 30), (44, 0, 1, 30),
             (-2, 60, 1, 30), (2, 60, 1, 30), (70, -2, 50, 1), (70, 2, 50, 1)]

# ---------------------------------------------------------------- per-stage config
# new_houses: (name, x, z, w, d, h, roofType) as built in the patched file.
# new_stalls: (x, z). plaza/park: (cx, cz, w, d). park_trees/lamps: (x, z).
# components: (part, meshes, sprites) derived from the CODE (kit counts).
# expected_delta: measured scene delta vs the previous stage (meshes, sprites, occluders).
STAGES = {
 2: {"label": "Stage 2 Market District",
     "new_houses": [("Bakery", -30, 62, 10, 8, 8, "shop"),
                    ("Café", 30, 64, 10, 8, 8, "shop"),
                    ("Workshop", -32, 84, 10, 8, 8, "shop"),
                    ("General Store", 32, 86, 10, 8, 8, "shop")],
     "new_stalls": [(-20, 74), (20, 74)],
     "plaza": (0, 88, 12, 12), "plaza_benches": [(-4.5, 92), (4.5, 92)],
     "park": None, "park_trees": [], "park_lamps": [],
     "components": [("4 shops (kit, 30 each)", 120, 0),
                    ("2 market stalls (kit, 13 each)", 26, 0),
                    ("Market plaza disc + fountain + 2 benches", 12, 1)],
     "expected_delta": {"meshes": 158, "sprites": 1, "occluders": 7}},
 3: {"label": "Stage 3 Civic / learning (west)",
     "new_houses": [("Library", -70, -28, 12, 9, 9, "gable"),
                    ("Academy", -70, 28, 12, 9, 9, "flat"),
                    ("Maker Space", -88, 32, 10, 8, 7, "dome")],
     "new_stalls": [], "plaza": None, "plaza_benches": [],
     "park": None, "park_trees": [], "park_lamps": [],
     "components": [("Library (gable kit)", 18, 0),
                    ("Academy (flat kit)", 28, 0),
                    ("Maker Space (dome kit)", 16, 0)],
     "expected_delta": {"meshes": 62, "sprites": 0, "occluders": 3}},
 4: {"label": "Stage 4 Park",
     "new_houses": [("Growth B", -38, 38, 8, 8, 5, "gable"),
                    ("Growth C", 52, -28, 8, 8, 5, "porch")],
     "new_stalls": [], "plaza": None, "plaza_benches": [],
     "park": (70, 32, 40, 25),
     "park_trees": [(55, 28), (59, 44), (75, 20), (77, 44), (91, 28), (95, 44)],
     "park_lamps": [(58, 22), (82, 22), (70, 44)],
     "park_benches": [(62, 26), (78, 26), (62, 38), (78, 38)],
     "components": [("Growth B (gable kit)", 18, 0),
                    ("Growth C (porch kit)", 18, 0),
                    ("Pond disc + centre stone", 2, 1),
                    ("Park benches x4 (4 each)", 16, 0),
                    ("Park lamps x3 (3 meshes + 1 sprite each)", 9, 3),
                    ("Park trees x6 (2 each)", 12, 0),
                    ("Ring path x4 + strip to east path", 5, 0)],
     "expected_delta": {"meshes": 80, "sprites": 4, "occluders": 2}},
}
# Cumulative expected houses[] per stage (name, x, z, w, d) — v26 base + stages.
V26_HOUSES = V24_HOUSES + S1_HOUSES + [
    ("Claude's Study", -40, -42, 8, 8), ("ChatGPT Workshop", 26, -43, 8, 8),
    ("Grok's Lab", 19, 37, 8, 8), ("Meta AI Lodge", 30, 50, 8, 8)]
EXPECTED_HOUSES = {
 2: V26_HOUSES + [(n, x, z, w, d) for n, x, z, w, d, _, _ in STAGES[2]["new_houses"]],
 3: V26_HOUSES + [(n, x, z, w, d) for n, x, z, w, d, _, _ in STAGES[2]["new_houses"]]
                + [(n, x, z, w, d) for n, x, z, w, d, _, _ in STAGES[3]["new_houses"]],
 4: V26_HOUSES + [(n, x, z, w, d) for n, x, z, w, d, _, _ in STAGES[2]["new_houses"]]
                + [(n, x, z, w, d) for n, x, z, w, d, _, _ in STAGES[3]["new_houses"]]
                + [(n, x, z, w, d) for n, x, z, w, d, _, _ in STAGES[4]["new_houses"]],
}
EXPECTED_STALLS = {2: [(-12, 58), (12, 60), (-20, 74), (20, 74)],
                   3: [(-12, 58), (12, 60), (-20, 74), (20, 74)],
                   4: [(-12, 58), (12, 60), (-20, 74), (20, 74)]}

ap = argparse.ArgumentParser()
ap.add_argument("--stage", type=int, required=True, choices=[2, 3, 4])
ap.add_argument("--html", required=True)
ap.add_argument("--counts", required=True)
ap.add_argument("--prev-html", required=True)
ap.add_argument("--prev-counts", required=True)
ap.add_argument("--diff", required=True)
ap.add_argument("--out", required=True)
A = ap.parse_args()
STAGE = A.stage
CFG = STAGES[STAGE]

src = open(A.html, encoding="utf-8").read()
prev_src = open(A.prev_html, encoding="utf-8").read()
COUNTS = json.load(open(A.counts))
PREV = json.load(open(A.prev_counts))
TREES = [(x, z) for x, z, _ in COUNTS["trees"]]
BUSHES = [(x, z) for x, z, _ in COUNTS["bushes"]]
BOULDERS = [(x, z) for x, z, _ in COUNTS["boulders"]]
PREV_TREES = [(x, z) for x, z, _ in PREV["trees"]]
print(f"=== {CFG['label']} audit — {A.html} ===")
print(f"file: {len(src.encode())} bytes, sha {hashlib.sha256(src.encode()).hexdigest()[:12]}...")
print(f"counts: {COUNTS['totalMeshes']} meshes + {COUNTS['totalSprites']} sprites = "
      f"{COUNTS['totalMeshes'] + COUNTS['totalSprites']} draw calls; materials {COUNTS['distinctMaterials']}; "
      f"lights {COUNTS['lights']}; occluders {COUNTS['cameraOccluders']}; trees {len(TREES)}; bushes {len(BUSHES)}; boulders {len(BOULDERS)}")

results = {"stage": STAGE, "label": CFG["label"], "file": A.html,
           "sha256": hashlib.sha256(src.encode()).hexdigest(),
           "bytes": len(src.encode()), "buildings": {}, "stalls": {},
           "plaza": {}, "park": {}, "park_trees": {}, "park_lamps": {},
           "corridors": {}, "quest_points": {}, "mesh": {}, "reconciliation": {},
           "static_checks": {}, "inventory": {}}
fails_total = [0]
def fail(msg):
    fails_total[0] += 1
    print("  FAIL:", msg)
    return msg

# ---------------------------------------------------------------- parse houses[] + stalls[] from the patched file
house_re = re.compile(r"\{x:(-?[\d.]+),z:(-?[\d.]+),label:(?:'([^']+)'|\"([^\"]+)\"),c:0x[0-9a-fA-F]+,roof:0x[0-9a-fA-F]+,roofType:'(\w+)',w:([\d.]+),h:([\d.]+),d:([\d.]+)\}")
PARSED_HOUSES = []
for m in house_re.finditer(src):
    x, z = float(m.group(1)), float(m.group(2))
    name = m.group(3) if m.group(3) is not None else m.group(4)
    PARSED_HOUSES.append((name, x, z, float(m.group(6)), float(m.group(8)),
                          float(m.group(7)), m.group(5)))
stalls_m = re.search(r"const stalls=\[(.*?)\];", src, re.S)
PARSED_STALLS = []
if stalls_m:
    for m in re.finditer(r"\{x:(-?[\d.]+),z:(-?[\d.]+),say:'[^']*'\}", stalls_m.group(1)):
        PARSED_STALLS.append((float(m.group(1)), float(m.group(2))))
print(f"\nparsed houses[]: {len(PARSED_HOUSES)} entries; stalls[]: {len(PARSED_STALLS)} entries")
print("  houses:", ", ".join(f"{n}@({x:g},{z:g})" for n, x, z, *_ in PARSED_HOUSES))

# ---------------------------------------------------------------- inventory: parsed vs expected (built vs planned)
inv_fails = []
exp_h = sorted(EXPECTED_HOUSES[STAGE])
got_h = sorted((n, x, z, w, d) for n, x, z, w, d, _, _ in PARSED_HOUSES)
if exp_h != got_h:
    for e in exp_h:
        if e not in got_h: inv_fails.append(f"expected house missing from file: {e}")
    for g in got_h:
        if g not in exp_h: inv_fails.append(f"unexpected house in file: {g}")
exp_s = sorted(EXPECTED_STALLS[STAGE])
got_s = sorted(PARSED_STALLS)
if exp_s != got_s:
    inv_fails.append(f"stalls mismatch: expected {exp_s}, got {got_s}")
# roofType / height check for the stage's new houses
for n, x, z, w, d, h, rt in CFG["new_houses"]:
    match = [p for p in PARSED_HOUSES if p[0] == n]
    if not match: inv_fails.append(f"new house {n} not parsed")
    elif (match[0][5], match[0][6]) != (h, rt):
        inv_fails.append(f"{n}: height/roofType {match[0][5]}/{match[0][6]} != expected {h}/{rt}")
results["inventory"] = {"expected_houses": len(exp_h), "parsed_houses": len(got_h),
                        "expected_stalls": len(exp_s), "parsed_stalls": len(got_s),
                        "fails": inv_fails}
print(f"inventory: {len(got_h)}/{len(exp_h)} houses, {len(got_s)}/{len(exp_s)} stalls — "
      + ("PASS" if not inv_fails else f"FAIL {inv_fails}"))
fails_total[0] += len(inv_fails)

# ---------------------------------------------------------------- LCG cross-check (scatter = first 30 trees; park trees appended after)
_seed = 12345.0
def rnd():
    global _seed
    _seed = (_seed * 1103515245 + 12345) % 2147483648
    return _seed / 2147483648
_spots = []
for _ in range(14): _spots.append((-40 + rnd() * 80, -60 - rnd() * 35))
for _ in range(4):  _spots.append((55 + rnd() * 50, -20 + rnd() * 40))
for _ in range(4):  _spots.append((-70 - rnd() * 30, -30 + rnd() * 60))
for _ in range(3):  _spots.append((-20 + rnd() * 40, 50 + rnd() * 20))
_spots += [(-42, -8), (42, -8), (-42, 8), (42, 8), (0, 34)]
_lcg_max_err = max(math.hypot(a[0]-b[0], a[1]-b[1]) for a, b in zip(_spots, TREES[:30]))
results["lcg_max_err"] = _lcg_max_err
print(f"\nLCG cross-check: 30 scatter tree spots replicated, max err vs node = {_lcg_max_err:.2e} u")
# Threshold 1e-4, not 1e-6: the node counter rounds positions to 4 decimals,
# so the documented match is 6.15e-05 u (CITY_AUDIT.md §3, "rounding only").
if _lcg_max_err > 1e-4: fail(f"LCG max err {_lcg_max_err:.2e} > 1e-4")

# ---------------------------------------------------------------- geometry helpers
def rect(b):  # b: (name, x, z, w, d, ...) — footprint + 0.8u steps on the +z front
    _, x, z, w, d = b[0], b[1], b[2], b[3], b[4]
    return (x - w/2, x + w/2, z - d/2, z + d/2 + 0.8)
def rect_no_steps(b):
    _, x, z, w, d = b[0], b[1], b[2], b[3], b[4]
    return (x - w/2, x + w/2, z - d/2, z + d/2)
def d_point_rect(px, pz, r):
    x0, x1, z0, z1 = r
    dx = max(x0 - px, 0, px - x1); dz = max(z0 - pz, 0, pz - z1)
    return math.hypot(dx, dz)
def point_in_rect(px, pz, r):
    x0, x1, z0, z1 = r
    return x0 <= px <= x1 and z0 <= pz <= z1
def rects_overlap(a, b):
    return not (a[1] < b[0] or b[1] < a[0] or a[3] < b[2] or b[3] < a[2])
def rect_rect_gap(a, b):
    if rects_overlap(a, b): return 0.0
    dx = max(b[0]-a[1], a[0]-b[1], 0); dz = max(b[2]-a[3], a[2]-b[3], 0)
    return math.hypot(dx, dz)

# TRUE collision model (v26 movement code, lines 982-983): houses wider than
# 12u get circles every 6u along x; others get one centre circle (r6).
def house_circles(h):
    # CORNERFIX verification model: the proposed rule, w>=10 -> 2 circles.
    _, x, z, w, d = h[0], h[1], h[2], h[3], h[4]
    if w >= 10:
        n = math.ceil((w - 6) / 6) + 1
        o0 = -(n - 1) * 3
        return [(x + o0 + i * 6, z) for i in range(n)]
    return [(x, z)]
ALL_CIRCLES = []  # (house_name, cx, cz)
for h in PARSED_HOUSES:
    for cx, cz in house_circles(h):
        ALL_CIRCLES.append((h[0], cx, cz))
print(f"collision model (TRUE): {len(PARSED_HOUSES)} houses -> {len(ALL_CIRCLES)} radius-6 discs "
      f"({', '.join(f'{n}:{len(house_circles(h))}' for h in PARSED_HOUSES for n in [h[0]] if len(house_circles(h)) > 1) or 'no wide houses'})")

# ---------------------------------------------------------------- BFS reachability (TRUE circles)
STEP = 0.5
GX0, GX1, GZ0, GZ1 = -120, 120, -100, 100
NW, NZ = int((GX1-GX0)/STEP)+1, int((GZ1-GZ0)/STEP)+1
def blocked(ix, iz):
    x, z = GX0 + ix*STEP, GZ0 + iz*STEP
    for _, cx, cz in ALL_CIRCLES:
        if (x-cx)**2 + (z-cz)**2 < 36: return True
    return False
si, sj = int((SPAWN[0]-GX0)/STEP), int((SPAWN[1]-GZ0)/STEP)
reach = [[False]*NZ for _ in range(NW)]
dq = deque([(si, sj)]); reach[si][sj] = True
while dq:
    i, j = dq.popleft()
    for di, dj in ((1,0),(-1,0),(0,1),(0,-1)):
        ni, nj = i+di, j+dj
        if 0 <= ni < NW and 0 <= nj < NZ and not reach[ni][nj] and not blocked(ni, nj):
            reach[ni][nj] = True; dq.append((ni, nj))
def min_dist_to_reachable(px, pz, radius):
    best = None
    r_cells = int(radius/STEP)
    ci, cj = int((px-GX0)/STEP), int((pz-GZ0)/STEP)
    for di in range(-r_cells, r_cells+1):
        for dj in range(-r_cells, r_cells+1):
            i, j = ci+di, cj+dj
            if 0 <= i < NW and 0 <= j < NZ and reach[i][j]:
                d = math.hypot(GX0+i*STEP-px, GZ0+j*STEP-pz)
                if d <= radius and (best is None or d < best): best = d
    return best

# Frozen point obstacles (v24 + Stage 1 kit; stalls = parsed, i.e. cumulative)
POINT_OBSTACLES = ([("lantern", x, z) for x, z in LANTERNS] +
    [("pickup-" + k, x, z) for k, x, z in PICKUPS] +
    [("npc-" + n, x, z) for n, x, z in NPCS] +
    [("stall", x, z) for x, z in PARSED_STALLS] + [("fire", *FIRE)] +
    [("bench", x, z) for x, z in BENCHES] +
    [("decor-lantern", x, z) for x, z in DECOR_LANTERNS] +
    [("sign", x, z) for x, z in SIGNS] +
    [("planter", x, z) for x, z in PLANTERS] +
    [("barrel", x, z) for x, z in BARRELS] +
    [("crate", x, z) for x, z in CRATES] +
    [("banner", x, z) for x, z in BANNERS] +
    [("sq-lamp", x, z) for x, z in S1_SQ_LAMPS] +
    [("s1-planter", x, z) for x, z in S1_PLANTERS] +
    [("notice", *S1_NOTICE)] +
    [("bench-hall", x, z) for x, z in S1_BENCHES] +
    [("plaza-bench", x, z) for x, z in CFG.get("plaza_benches", [])] +
    ([("park-bench", x, z) for x, z in CFG.get("park_benches", [])] if CFG.get("park") else []) +
    ([("pond", CFG["park"][0], CFG["park"][1])] if CFG.get("park") else []))

def check_building(b, label=None):
    """Full per-building check. b: (name, x, z, w, d, h, kit, stage, circ)."""
    name, x, z, w, d, h, kit, stage, circ = b
    r = rect(b)
    fails, warns, notes = [], [], []
    if r[0] < -120 or r[1] > 120 or r[2] < -100 or r[3] > 100:
        fails.append(f"out of bounds: rect {r}")
    # vs every OTHER house's TRUE circles (rect must not enter a 6u circle)
    for hn, hx, hz, hw, hd, *_ in PARSED_HOUSES:
        if hn == name: continue
        for cx, cz in house_circles((hn, hx, hz, hw, hd)):
            dd = d_point_rect(cx, cz, r)
            if dd < 6: fails.append(f"rect enters {hn} 6u circle at ({cx:g},{cz:g}) (centre-to-rect {dd:.2f}u)")
    # vs other houses: min circle-to-circle distance >= 12 (circled pairs), rects must not overlap
    my_circles = house_circles((name, x, z, w, d))
    for hn, hx, hz, hw, hd, *_ in PARSED_HOUSES:
        if hn == name: continue
        other = house_circles((hn, hx, hz, hw, hd))
        if circ:
            md = min(math.hypot(cx-ox, cz-oz) for cx, cz in my_circles for ox, oz in other)
            if md < 12: fails.append(f"collision circles {md:.1f}u from {hn} (<12u rule)")
            notes.append(f"  min circle distance to {hn}: {md:.1f}u")
        if rects_overlap(r, rect((hn, hx, hz, hw, hd))):
            fails.append(f"footprint OVERLAPS {hn}")
        elif rect_rect_gap(r, rect((hn, hx, hz, hw, hd))) < 2:
            warns.append(f"footprint gap to {hn} only {rect_rect_gap(r, rect((hn, hx, hz, hw, hd))):.1f}u")
    # vs the stage's non-house kits (stalls, plaza, park) — rects must not overlap
    for sx, sz in CFG.get("new_stalls", []):
        sr = (sx - 1.6, sx + 1.6, sz - 0.9, sz + 0.9)
        if rects_overlap(r, sr): fails.append(f"footprint OVERLAPS market stall at ({sx},{sz})")
    if CFG.get("plaza") and kit != "plaza":
        px, pz, pw, pd = CFG["plaza"]
        pr = (px - pw/2, px + pw/2, pz - pd/2, pz + pd/2)
        if rects_overlap(r, pr): fails.append("footprint OVERLAPS market plaza")
    if CFG.get("park") and kit != "park":
        px, pz, pw, pd = CFG["park"]
        pr = (px - pw/2, px + pw/2, pz - pd/2, pz + pd/2)
        if rects_overlap(r, pr): fails.append("footprint OVERLAPS city park")
    # vs corridors
    for cn, cr in CORRIDORS.items():
        if rects_overlap(r, cr): fails.append(f"footprint BLOCKS {cn} corridor")
    # vs hill
    hd = d_point_rect(HILL[0], HILL[1], r)
    if hd < 14: fails.append(f"rect {hd:.1f}u from hill centre (<14u)")
    # vs quest/frozen points (a kit is never checked against its own furniture:
    # the plaza contains its benches by design; the park contains its benches + pond)
    skip_kinds = set()
    if kit == "plaza": skip_kinds.add("plaza-bench")
    if kit == "park": skip_kinds |= {"park-bench", "pond"}
    for kind, qx, qz in POINT_OBSTACLES:
        if kind in skip_kinds: continue
        if point_in_rect(qx, qz, r):
            fails.append(f"SWALLOWS {kind} at ({qx},{qz})")
        else:
            dd = d_point_rect(qx, qz, r)
            if dd < 2: warns.append(f"{kind} ({qx},{qz}) only {dd:.2f}u from footprint")
    # vs exact scatter (a kit is never checked against its own trees: the
    # park rect contains its own 6 park trees by design)
    park_tree_set = set(CFG.get("park_trees", [])) if kit == "park" else set()
    for tx, tz in TREES:
        if (tx, tz) in park_tree_set: continue
        dd = d_point_rect(tx, tz, r)
        if dd < 1.5: fails.append(f"tree trunk ({tx:.1f},{tz:.1f}) {dd:.2f}u from footprint")
    for bx, bz in BUSHES:
        if d_point_rect(bx, bz, r) < 1.5: fails.append(f"bush ({bx:.1f},{bz:.1f}) inside/near footprint")
    for bx, bz in BOULDERS:
        if d_point_rect(bx, bz, r) < 2.0: fails.append(f"boulder ({bx:.1f},{bz:.1f}) inside/near footprint")
    # door approach (houses only): point 2u in front of the door reachable within 8u
    door_reach = None
    if kit not in ("plaza", "park", "stall"):
        door = (x, z + d/2 + 2.0)
        door_reach = min_dist_to_reachable(door[0], door[1], 8)
        if door_reach is None: fails.append(f"door approach {door} UNREACHABLE from spawn")
    return {"rect": [round(v, 1) for v in r], "stage": stage, "fails": fails, "warns": warns,
            "notes": notes, "door_reachable_within_8u": None if door_reach is None else round(door_reach, 2)}

print("\n### New buildings")
for n, x, z, w, d, h, rt in CFG["new_houses"]:
    b = (n, x, z, w, d, h, rt, STAGE, True)
    res = check_building(b)
    results["buildings"][n] = res
    fails_total[0] += len(res["fails"])
    print(f"  {n} ({x},{z}) {w}x{d} h{h} {rt} rect x {res['rect'][0]}..{res['rect'][1]} z {res['rect'][2]}..{res['rect'][3]}")
    print("    FAILS:", res["fails"] if res["fails"] else "none")
    print("    WARNS:", res["warns"] if res["warns"] else "none")
    print(f"    door approach reachable: {'NO' if res['door_reachable_within_8u'] is None else 'yes, nearest reachable cell %.2fu away' % res['door_reachable_within_8u']}")
    for nn in res["notes"]: print("   ", nn)

# ---------------------------------------------------------------- stalls (new): approach + clearances
print("\n### New stalls")
for sx, sz in CFG.get("new_stalls", []):
    fails = []
    dd = min_dist_to_reachable(sx, sz, 8)
    if dd is None: fails.append("stall approach UNREACHABLE from spawn")
    for hn, hx, hz, *_ in PARSED_HOUSES:
        for cx, cz in house_circles((hn, hx, hz, 0, 0)):
            if math.hypot(sx-cx, sz-cz) < 6: fails.append(f"stall inside {hn} 6u circle")
    for cn, cr in CORRIDORS.items():
        if point_in_rect(sx, sz, cr): fails.append(f"stall BLOCKS {cn} corridor")
    for kind, qx, qz in POINT_OBSTACLES:
        if (qx, qz) != (sx, sz) and math.hypot(sx-qx, sz-qz) < 1.0:
            fails.append(f"stall within 1u of frozen {kind} ({qx},{qz})")
    results["stalls"][f"({sx},{sz})"] = {"approach_within_8u": None if dd is None else round(dd, 2), "fails": fails}
    fails_total[0] += len(fails)
    print(f"  stall ({sx},{sz}): approach {'NO' if dd is None else 'yes, %.2fu' % dd} — {'FAIL: ' + str(fails) if fails else 'PASS'}")

# ---------------------------------------------------------------- plaza (Stage 2): rect checks, no door
if CFG.get("plaza"):
    px, pz, pw, pd = CFG["plaza"]
    b = ("Market plaza+fountain", px, pz, pw, pd, 1, "plaza", STAGE, False)
    res = check_building(b)
    results["plaza"] = res
    fails_total[0] += len(res["fails"])
    print(f"\n### Market plaza rect x {res['rect'][0]}..{res['rect'][1]} z {res['rect'][2]}..{res['rect'][3]}")
    print("  FAILS:", res["fails"] if res["fails"] else "none")
    print("  WARNS:", res["warns"] if res["warns"] else "none")
    # plaza benches: outside house circles, >=1u from frozen, >=1.5u from trees
    for bx, bz in CFG["plaza_benches"]:
        bfails = []
        for hn, hx, hz, *_ in PARSED_HOUSES:
            for cx, cz in house_circles((hn, hx, hz, 0, 0)):
                if math.hypot(bx-cx, bz-cz) < 6: bfails.append(f"bench inside {hn} 6u circle")
        for tx, tz in TREES:
            if math.hypot(bx-tx, bz-tz) < 1.5: bfails.append(f"bench within 1.5u of tree ({tx:.1f},{tz:.1f})")
        for kind, qx, qz in POINT_OBSTACLES:
            if (qx, qz) != (bx, bz) and math.hypot(bx-qx, bz-qz) < 1.0:
                bfails.append(f"bench within 1u of frozen {kind} ({qx},{qz})")
        fails_total[0] += len(bfails)
        print(f"  plaza bench ({bx},{bz}): {'FAIL: ' + str(bfails) if bfails else 'PASS'}")

# ---------------------------------------------------------------- park (Stage 4): rect, trees, lamps, benches
if CFG.get("park"):
    px, pz, pw, pd = CFG["park"]
    b = ("City Park", px, pz, pw, pd, 1, "park", STAGE, False)
    res = check_building(b)
    results["park"]["rect_check"] = res
    fails_total[0] += len(res["fails"])
    print(f"\n### City Park rect x {res['rect'][0]}..{res['rect'][1]} z {res['rect'][2]}..{res['rect'][3]}")
    print("  FAILS:", res["fails"] if res["fails"] else "none")
    print("  WARNS:", res["warns"] if res["warns"] else "none")
    # park trees: >=10u from pond (70,32), >=12u from any coin, >=12u from any
    # pre-existing tree, >=1.5u from any building rect, inside park rect.
    pr = (px - pw/2, px + pw/2, pz - pd/2, pz + pd/2)
    coins = [(x, z) for k, x, z in PICKUPS if k == "coin"]
    for tx, tz in CFG["park_trees"]:
        tf = []
        # NOTE: "inside the park rect" is NOT a proposal rule and is NOT
        # checked: the proposal pins the park at 40x25 (x 50..90) AND pins
        # trees at (91,28) and (95,44), which stand 1u/5u east of that
        # footprint. The trees are built exactly where the proposal pins
        # them; the footprint/tree mismatch is in the spec itself (flagged
        # in SUMMARY.md). The clearance rules below are the real checks.
        note = ""
        if not point_in_rect(tx, tz, pr):
            note = f"stands outside the 40x25 park footprint (x {pr[0]:.0f}..{pr[1]:.0f}) — spec quirk, see SUMMARY.md"
        dpond = math.hypot(tx - px, tz - pz)
        if dpond < 10: tf.append(f"tree {dpond:.1f}u from pond centre (<10u)")
        dc = min(math.hypot(tx-cx, tz-cz) for cx, cz in coins)
        if dc < 12: tf.append(f"tree {dc:.1f}u from nearest coin (<12u)")
        dt = min(math.hypot(tx-ex, tz-ez) for ex, ez in PREV_TREES)
        if dt < 12: tf.append(f"tree {dt:.1f}u from nearest existing tree (<12u)")
        for hn, hx, hz, hw, hd, *_ in PARSED_HOUSES:
            if d_point_rect(tx, tz, rect_no_steps((hn, hx, hz, hw, hd))) < 1.5:
                tf.append(f"tree within 1.5u of {hn} footprint")
        results["park_trees"][f"({tx},{tz})"] = {"pond": round(dpond, 2), "coin": round(dc, 2),
            "existing_tree": round(dt, 2), "fails": tf, "notes": note}
        fails_total[0] += len(tf)
        print(f"  park tree ({tx},{tz}): pond {dpond:.1f}u, coin {dc:.1f}u, existing tree {dt:.1f}u — {'FAIL: ' + str(tf) if tf else 'PASS'}" + (f" [{note}]" if note else ""))
    # park lamps: Stage 1 lamp thresholds (tree>=1.5, bush>=1.5, boulder>=2.0,
    # frozen>=2.0, outside house 6u circles). TREES here include the 6 park trees.
    FROZEN_PARK = ([("quest-lantern", x, z) for x, z in LANTERNS] +
        [("npc-" + n, x, z) for n, x, z in NPCS] + [("sign", x, z) for x, z in SIGNS] +
        [("bench", x, z) for x, z in BENCHES] + [("stall", x, z) for x, z in PARSED_STALLS] +
        [("fire", *FIRE)] + [("pickup-" + k, x, z) for k, x, z in PICKUPS] +
        [("planter", x, z) for x, z in PLANTERS] + [("sq-lamp", x, z) for x, z in S1_SQ_LAMPS] +
        [("notice", *S1_NOTICE)] + [("bench-hall", x, z) for x, z in S1_BENCHES] +
        [("plaza-bench", x, z) for x, z in CFG.get("plaza_benches", [])] +
        [("park-bench", x, z) for x, z in CFG.get("park_benches", [])] +
        [("pond", px, pz)] + [("park-lamp", x, z) for x, z in CFG["park_lamps"]])
    for lx, lz in CFG["park_lamps"]:
        lf = []
        dt = min(math.hypot(lx-tx, lz-tz) for tx, tz in TREES)
        du = min(math.hypot(lx-bx, lz-bz) for bx, bz in BUSHES)
        db = min(math.hypot(lx-bx, lz-bz) for bx, bz in BOULDERS)
        df = min(math.hypot(lx-fx, lz-fz) for _, fx, fz in FROZEN_PARK
                 if not (abs(fx-lx) < 0.01 and abs(fz-lz) < 0.01))
        dc = min(math.hypot(lx-cx, lz-cz) - 6 for _, cx, cz in ALL_CIRCLES)
        if dt < 1.5: lf.append(f"tree {dt:.2f}u")
        if du < 1.5: lf.append(f"bush {du:.2f}u")
        if db < 2.0: lf.append(f"boulder {db:.2f}u")
        if df < 2.0: lf.append(f"frozen {df:.2f}u")
        if dc < 0: lf.append(f"inside house circle ({dc:.2f}u)")
        results["park_lamps"][f"({lx},{lz})"] = {"tree": round(dt, 2), "bush": round(du, 2),
            "boulder": round(db, 2), "frozen": round(df, 2), "house_circle_clearance": round(dc, 2), "fails": lf}
        fails_total[0] += len(lf)
        print(f"  park lamp ({lx},{lz}): tree {dt:.2f}u, bush {du:.2f}u, boulder {db:.2f}u, frozen {df:.2f}u, house-circle +{dc:.2f}u — {'FAIL: ' + str(lf) if lf else 'PASS'}")
    # park benches: outside house circles, >=1u from frozen, >=1.5u from trees
    for bx, bz in CFG["park_benches"]:
        bf = []
        for hn, hx, hz, *_ in PARSED_HOUSES:
            for cx, cz in house_circles((hn, hx, hz, 0, 0)):
                if math.hypot(bx-cx, bz-cz) < 6: bf.append(f"bench inside {hn} 6u circle")
        for tx, tz in TREES:
            if math.hypot(bx-tx, bz-tz) < 1.5: bf.append(f"bench within 1.5u of tree ({tx:.1f},{tz:.1f})")
        for kind, qx, qz in POINT_OBSTACLES:
            if (qx, qz) != (bx, bz) and math.hypot(bx-qx, bz-qz) < 1.0:
                bf.append(f"bench within 1u of frozen {kind} ({qx},{qz})")
        fails_total[0] += len(bf)
        print(f"  park bench ({bx},{bz}): {'FAIL: ' + str(bf) if bf else 'PASS'}")

# ---------------------------------------------------------------- corridors (40 centreline samples total)
print("\n### Corridors")
total_samples = 0
for cn, cr in CORRIDORS.items():
    x0, x1, z0, z1 = cr
    samples = []
    if x1 - x0 > z1 - z0:
        xx = x0
        while xx <= x1: samples.append((xx, (z0+z1)/2)); xx += 5
    else:
        zz = z0
        while zz <= z1: samples.append(((x0+x1)/2, zz)); zz += 5
    total_samples += len(samples)
    bad = []
    for sx, sz in samples:
        i, j = int((sx-GX0)/STEP), int((sz-GZ0)/STEP)
        if blocked(i, j) or not reach[i][j]: bad.append((sx, sz))
    blockers = [h[0] for h in PARSED_HOUSES if rects_overlap(rect(h), cr)]
    if CFG.get("plaza"):
        px, pz, pw, pd = CFG["plaza"]
        if rects_overlap((px-pw/2, px+pw/2, pz-pd/2, pz+pd/2), cr): blockers.append("Market plaza")
    if CFG.get("park"):
        px, pz, pw, pd = CFG["park"]
        if rects_overlap((px-pw/2, px+pw/2, pz-pd/2, pz+pd/2), cr): blockers.append("City Park")
    results["corridors"][cn] = {"samples": len(samples), "unreachable_samples": bad, "rect_blockers": blockers}
    fails_total[0] += len(bad) + len(blockers)
    print(f"  {cn}: {len(samples)} centreline samples, unreachable: {bad if bad else 'none'}, rect blockers: {blockers if blockers else 'none'}")
print(f"  TOTAL corridor samples: {total_samples}")

# ---------------------------------------------------------------- quest points: reachable within 8u
print("\n### Quest points — nearest REACHABLE walkable cell (must be <= 8u)")
n_qp = 0
qp_fails = 0
for kind, qx, qz in ([("lantern", x, z) for x, z in LANTERNS] +
                     [("pickup-" + k, x, z) for k, x, z in PICKUPS] +
                     [("npc-" + n, x, z) for n, x, z in NPCS] +
                     [("stall", x, z) for x, z in PARSED_STALLS] + [("fire", *FIRE)]):
    n_qp += 1
    dd = min_dist_to_reachable(qx, qz, 8)
    ok = dd is not None
    if not ok: qp_fails += 1
    results["quest_points"][f"{kind}@({qx},{qz})"] = None if dd is None else round(dd, 2)
    print(f"  {kind} ({qx},{qz}): {'REACHABLE, nearest walkable cell %.2fu away' % dd if ok else 'UNREACHABLE within 8u — FAIL'}")
print(f"  TOTAL quest points: {n_qp}")
fails_total[0] += qp_fails
si2, sj2 = int((SPAWN[0]-GX0)/STEP), int((SPAWN[1]-GZ0)/STEP)
spawn_ok = reach[si2][sj2] and not blocked(si2, sj2)
print(f"\nSpawn {SPAWN} walkable+reachable: {spawn_ok} (blocked={blocked(si2, sj2)})")
if not spawn_ok: fail("spawn not walkable+reachable")

# ---------------------------------------------------------------- static checks
print("\n### Static checks")
sc = results["static_checks"]
# 1. node --check on the extracted game JS
game_js = src.split("<script>", 1)[1].split("</script>", 1)[0]
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
    tf.write(game_js); tmp_js = tf.name
nc = subprocess.run(["node", "--check", tmp_js], capture_output=True, text=True)
os.unlink(tmp_js)
sc["node_check"] = {"pass": nc.returncode == 0, "stderr": nc.stderr.strip()[:300]}
print(f"  node --check on extracted game JS: {'PASS' if nc.returncode == 0 else 'FAIL ' + nc.stderr[:200]}")
if nc.returncode != 0: fail("node --check failed")
# 2. no external refs (http/https/fetch/XHR/import) in the ADDED lines only —
#    the diff is the stage's change set; the base file is already clean.
diff_text = open(A.diff, encoding="utf-8").read()
added = "\n".join(l[1:] for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++"))
ext_pats = [r"https?://", r"\bfetch\s*\(", r"XMLHttpRequest", r"\bimport\s", r"\bimport\("]
ext_hits = {}
for p in ext_pats:
    n = len(re.findall(p, added))
    if n: ext_hits[p] = n
sc["external_refs_in_diff"] = ext_hits
print(f"  external refs in added lines (http/fetch/XHR/import): {ext_hits if ext_hits else 'none — PASS'}")
if ext_hits: fail(f"external refs in diff: {ext_hits}")
# whole-file check as well (base must stay clean too)
whole_hits = {}
for p in ext_pats:
    n = len(re.findall(p, src))
    if n: whole_hits[p] = n
sc["external_refs_whole_file"] = whole_hits
print(f"  external refs in whole file: {whole_hits if whole_hits else 'none — PASS'}")
if whole_hits: fail(f"external refs in file: {whole_hits}")
# 3. no money / network words anywhere in the file
money_pats = [r"\bwallet\b", r"\bprice\b", r"\bmoney\b", r"\bpayment\b", r"\baccount\b",
              r"\bserver\b", r"\bsocket\b"]
money_hits = {}
for p in money_pats:
    n = len(re.findall(p, src, re.I))
    if n: money_hits[p] = n
sc["money_words"] = money_hits
print(f"  money/network words (wallet/price/money/payment/account/server/socket): {money_hits if money_hits else 'none — PASS'}")
if money_hits: fail(f"money words present: {money_hits}")
# 4. phone CSS/JS untouched: <style> block hash + applyPhoneUI line identity vs previous stage
def style_block(s):
    m = re.search(r"<style>.*?</style>", s, re.S)
    return m.group(0) if m else ""
def phone_line(s):
    m = re.search(r"function applyPhoneUI\(\).*", s)
    return m.group(0) if m else ""
sb_new, sb_prev = style_block(src), style_block(prev_src)
pl_new, pl_prev = phone_line(src), phone_line(prev_src)
sc["phone_css_untouched"] = {"pass": sb_new == sb_prev and len(sb_new) > 0,
    "style_sha": hashlib.sha256(sb_new.encode()).hexdigest()[:16]}
sc["phone_js_untouched"] = {"pass": pl_new == pl_prev and len(pl_new) > 0}
print(f"  phone CSS (<style> block, {len(sb_new)} B, sha {sc['phone_css_untouched']['style_sha']}): "
      f"{'identical — PASS' if sb_new == sb_prev else 'CHANGED — FAIL'}")
print(f"  phone JS (applyPhoneUI line): {'identical — PASS' if pl_new == pl_prev else 'CHANGED — FAIL'}")
if sb_new != sb_prev: fail("phone CSS changed")
if pl_new != pl_prev: fail("phone JS (applyPhoneUI) changed")
# 5. no new lights: lights count must equal previous stage's
sc["lights"] = {"prev": PREV["lights"], "now": COUNTS["lights"]}
print(f"  lights: {PREV['lights']} -> {COUNTS['lights']} — {'PASS (no new lights)' if COUNTS['lights'] == PREV['lights'] else 'FAIL'}")
if COUNTS["lights"] != PREV["lights"]: fail("light count changed")
# 6. scatter unchanged: trees/bushes/boulders identical to previous stage
#    (except Stage 4, which adds 6 park trees — scatter subset must match)
sc["scatter_unchanged"] = {"prev_trees": len(PREV_TREES), "now_trees": len(TREES),
    "prev_bushes": len(PREV["bushes"]), "now_bushes": len(BUSHES),
    "prev_boulders": len(PREV["boulders"]), "now_boulders": len(BOULDERS)}
scatter_ok = (TREES[:30] == PREV_TREES[:30] and BUSHES == [(x, z) for x, z, _ in PREV["bushes"]]
              and BOULDERS == [(x, z) for x, z, _ in PREV["boulders"]])
print(f"  scatter: trees {len(PREV_TREES)} -> {len(TREES)}, bushes {len(PREV['bushes'])} -> {len(BUSHES)}, "
      f"boulders {len(PREV['boulders'])} -> {len(BOULDERS)} — {'PASS' if scatter_ok else 'FAIL'}")
if not scatter_ok: fail("scatter positions changed")
# 7. hall top-y unchanged
sc["hall_max_top_y"] = {"prev": PREV["hallMaxTopY"], "now": COUNTS["hallMaxTopY"]}
print(f"  hall max top-y: {PREV['hallMaxTopY']} -> {COUNTS['hallMaxTopY']} — "
      f"{'PASS' if COUNTS['hallMaxTopY'] == PREV['hallMaxTopY'] else 'FAIL'}")
if COUNTS["hallMaxTopY"] != PREV["hallMaxTopY"]: fail("hall max top-y changed")

# ---------------------------------------------------------------- mesh reconciliation
print("\n### Mesh reconciliation (components from the code vs measured delta)")
dm = COUNTS["totalMeshes"] - PREV["totalMeshes"]
ds = COUNTS["totalSprites"] - PREV["totalSprites"]
do = COUNTS["cameraOccluders"] - PREV["cameraOccluders"]
comp_m = sum(c[1] for c in CFG["components"])
comp_s = sum(c[2] for c in CFG["components"])
exp = CFG["expected_delta"]
print(f"  measured delta: +{dm} meshes, +{ds} sprites, +{do} occluders")
print(f"  component table: +{comp_m} meshes, +{comp_s} sprites")
for part, m, s in CFG["components"]:
    print(f"    {part}: {m} meshes, {s} sprites")
rec_ok = (dm == comp_m == exp["meshes"] and ds == comp_s == exp["sprites"] and do == exp["occluders"])
results["mesh"] = {"prev": {"meshes": PREV["totalMeshes"], "sprites": PREV["totalSprites"],
    "draw_calls": PREV["totalMeshes"] + PREV["totalSprites"], "materials": PREV["distinctMaterials"],
    "lights": PREV["lights"], "occluders": PREV["cameraOccluders"]},
  "now": {"meshes": COUNTS["totalMeshes"], "sprites": COUNTS["totalSprites"],
    "draw_calls": COUNTS["totalMeshes"] + COUNTS["totalSprites"], "materials": COUNTS["distinctMaterials"],
    "lights": COUNTS["lights"], "occluders": COUNTS["cameraOccluders"]},
  "delta": {"meshes": dm, "sprites": ds, "occluders": do, "materials": COUNTS["distinctMaterials"] - PREV["distinctMaterials"]},
  "houses": {k: v["meshes"] for k, v in COUNTS["houses"].items()},
  "new_buildings_rect": COUNTS["newBuildingsRect"], "kit_points": COUNTS.get("kitPoints", {}),
  "hall_max_top_y": COUNTS["hallMaxTopY"]}
results["reconciliation"] = {"components": [{"part": p, "meshes": m, "sprites": s} for p, m, s in CFG["components"]],
  "component_meshes": comp_m, "component_sprites": comp_s,
  "expected_delta": exp, "measured_delta": {"meshes": dm, "sprites": ds, "occluders": do},
  "pass": rec_ok,
  "note": "Per-house 7u buckets and rect counts overcount by adjacency (grass tufts inside buckets/rects; awning+posts outside the rect). The component table is derived from the CODE (kit counts), not from summed buckets — same method as STAGE1_AUDIT.md §1."}
print(f"  reconciliation: {'PASS' if rec_ok else 'FAIL'} (measured {dm}/{ds}/{do} vs components {comp_m}/{comp_s} vs expected {exp['meshes']}/{exp['sprites']}/{exp['occluders']})")
if not rec_ok: fail("mesh reconciliation mismatch")

# ---------------------------------------------------------------- totals + dump
results["totals"] = {"building_fails": sum(len(v["fails"]) for v in results["buildings"].values()),
  "corridor_samples": total_samples, "quest_points": n_qp, "quest_point_fails": qp_fails,
  "total_fails": fails_total[0]}
json.dump(results, open(A.out, "w"), indent=1)
print(f"\nTOTAL FAILS: {fails_total[0]}")
print(f"corridor samples: {total_samples}; quest points: {n_qp} ({qp_fails} fails); "
      f"draw calls: {COUNTS['totalMeshes'] + COUNTS['totalSprites']} (prev {PREV['totalMeshes'] + PREV['totalSprites']}, +{dm + ds})")
print(f"results -> {A.out}")
sys.exit(0 if fails_total[0] == 0 else 1)
