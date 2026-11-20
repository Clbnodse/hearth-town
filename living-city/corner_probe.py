#!/usr/bin/env python3
"""Corner probe for ChatGPT review item 3 (msg-c7f04c61).

Question: the movement code gives houses w<=12 ONE radius-6 circle at the
centre. A single r6 circle does not cover a rectangular footprint's corners
(e.g. 12x9 corner is 7.5u from the centre). Can the player walk into the
corner region? How deep? Is the house interior reachable?

Method: replicate the LIVE movement model exactly (final file, line ~1063):
  n = ceil((w-6)/6)+1 circles if w>12 else 1, offsets -(n-1)*3 + i*6, r=6.
  Player is a point; each frame it is pushed out to exactly 6u from any
  circle centre it is inside of. Walkable = distance >= 6 from every centre.
BFS on the audit's 0.5u grid from spawn (18,6) with the same blocked()
rule proves continuous walkability (BFS is MORE restrictive than the
continuous model: 4-connected 0.5u steps vs 0.18u/frame free movement, so a
BFS path guarantees a live walk exists).

For each house reports:
  - analytic corner distance from the nearest circle centre, clip = dist - 6
  - BFS: any reachable cell inside the BODY rect? inside the AUDIT rect
    (body + 0.8u front step zone)? deepest penetration (max over reachable
    interior points of distance to the nearest rect edge)
  - door approach (x, z+d/2+2) reachable within 8u (same check as the audit)
  - house CENTRE reachable? (the "walk-in" test: can the player stand where
    the house body is?)
Exit 0 always; prints a table + writes corner_probe_results.json.
"""
import json, math, re, sys
from collections import deque

HTML = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2s3s4.html"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/home/hatch/workspace/game-collab-api/city-proposal/stage234/corner_probe_results.json"

src = open(HTML, encoding="utf-8").read()
house_re = re.compile(r"\{x:(-?[\d.]+),z:(-?[\d.]+),label:(?:'([^']+)'|\"([^\"]+)\"),c:0x[0-9a-fA-F]+,roof:0x[0-9a-fA-F]+,roofType:'(\w+)',w:([\d.]+),h:([\d.]+),d:([\d.]+)\}")
HOUSES = []
for m in house_re.finditer(src):
    x, z = float(m.group(1)), float(m.group(2))
    name = m.group(3) if m.group(3) is not None else m.group(4)
    HOUSES.append((name, x, z, float(m.group(6)), float(m.group(8)),
                   float(m.group(7)), m.group(5)))
assert len(HOUSES) == 21, f"parsed {len(HOUSES)} houses, expected 21"

# LIVE movement model (verbatim from the file): w>12 -> ceil((w-6)/6)+1 circles
# Rule 'fix' (argv[3]): the proposed correction, w>=10 -> ceil((w-6)/6)+1.
RULE = sys.argv[3] if len(sys.argv) > 3 else 'live'
def live_circles(h):
    _, x, z, w, d = h[0], h[1], h[2], h[3], h[4]
    thresh = 10 if RULE == 'fix' else 12
    if w > thresh or (RULE == 'fix' and w >= thresh):
        n = math.ceil((w - 6) / 6) + 1
        o0 = -(n - 1) * 3
        return [(x + o0 + i * 6, z) for i in range(n)]
    return [(x, z)]

ALL_CIRCLES = []
for h in HOUSES:
    for cx, cz in live_circles(h):
        ALL_CIRCLES.append((h[0], cx, cz))
print(f"houses: {len(HOUSES)} -> {len(ALL_CIRCLES)} radius-6 discs")
assert len(ALL_CIRCLES) == (33 if RULE == 'fix' else 23), f"{len(ALL_CIRCLES)} discs, expected {33 if RULE == 'fix' else 23}"

# BFS (audit's grid + blocked rule)
STEP = 0.5
GX0, GX1, GZ0, GZ1 = -120, 120, -100, 100
NW, NZ = int((GX1 - GX0) / STEP) + 1, int((GZ1 - GZ0) / STEP) + 1
def blocked(ix, iz):
    x, z = GX0 + ix * STEP, GZ0 + iz * STEP
    for _, cx, cz in ALL_CIRCLES:
        if (x - cx) ** 2 + (z - cz) ** 2 < 36:
            return True
    return False
SPAWN = (18, 6)
si, sj = int((SPAWN[0] - GX0) / STEP), int((SPAWN[1] - GZ0) / STEP)
reach = [[False] * NZ for _ in range(NW)]
dq = deque([(si, sj)]); reach[si][sj] = True
while dq:
    i, j = dq.popleft()
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ni, nj = i + di, j + dj
        if 0 <= ni < NW and 0 <= nj < NZ and not reach[ni][nj] and not blocked(ni, nj):
            reach[ni][nj] = True; dq.append((ni, nj))

def rect_body(h):
    _, x, z, w, d = h[0], h[1], h[2], h[3], h[4]
    return (x - w / 2, x + w / 2, z - d / 2, z + d / 2)
def rect_audit(h):  # audit convention: +0.8u step zone on the +z front
    x0, x1, z0, z1 = rect_body(h)
    return (x0, x1, z0, z1 + 0.8)
def inside(px, pz, r):
    return r[0] <= px <= r[1] and r[2] <= pz <= r[3]
def edge_dist(px, pz, r):
    return min(px - r[0], r[1] - px, pz - r[2], r[3] - pz)
def min_dist_to_reachable(px, pz, radius):
    best = None
    rc = int(radius / STEP)
    ci, cj = int((px - GX0) / STEP), int((pz - GZ0) / STEP)
    for di in range(-rc, rc + 1):
        for dj in range(-rc, rc + 1):
            i, j = ci + di, cj + dj
            if 0 <= i < NW and 0 <= j < NZ and reach[i][j]:
                d = math.hypot(GX0 + i * STEP - px, GZ0 + j * STEP - pz)
                if d <= radius and (best is None or d < best):
                    best = d
    return best

print(f"\n{'house':<16} {'w×d':<7} {'discs':<5} {'corner':<7} {'clip':<6} {'BFS-in-body':<11} {'deepest':<8} {'BFS-in-audit':<12} {'deepest':<8} {'door≤8u':<8} {'centre?':<8}")
results = {}
for h in HOUSES:
    name, x, z, w, d = h[0], h[1], h[2], h[3], h[4]
    circles = live_circles(h)
    # analytic: farthest rect corner from its nearest circle centre
    corners = [(x - w / 2, z - d / 2), (x + w / 2, z - d / 2),
               (x - w / 2, z + d / 2), (x + w / 2, z + d / 2)]
    corner_dist = max(min(math.hypot(cx - ccx, cz - ccz) for ccx, ccz in circles)
                      for cx, cz in corners)
    clip = corner_dist - 6.0
    # BFS interior scan
    rb, ra = rect_body(h), rect_audit(h)
    best_body, best_audit = 0.0, 0.0
    in_body, in_audit = False, False
    for i in range(NW):
        px = GX0 + i * STEP
        if px < rb[0] - 1 or px > rb[1] + 1:
            continue
        for j in range(NZ):
            if not reach[i][j]:
                continue
            pz = GZ0 + j * STEP
            if inside(px, pz, rb):
                in_body = True
                best_body = max(best_body, edge_dist(px, pz, rb))
            if inside(px, pz, ra):
                in_audit = True
                best_audit = max(best_audit, edge_dist(px, pz, ra))
    door = (x, z + d / 2 + 2.0)
    door_d = min_dist_to_reachable(door[0], door[1], 8)
    centre_d = min_dist_to_reachable(x, z, 8)
    centre_reachable = blocked(int((x - GX0) / STEP), int((z - GZ0) / STEP)) is False and reach[int((x - GX0) / STEP)][int((z - GZ0) / STEP)]
    results[name] = {
        "x": x, "z": z, "w": w, "d": d, "h": h[5], "roof": h[6],
        "discs": [[round(cx, 1), round(cz, 1)] for cx, cz in circles],
        "corner_dist": round(corner_dist, 2), "corner_clip": round(clip, 2),
        "bfs_in_body_rect": in_body, "deepest_in_body": round(best_body, 2),
        "bfs_in_audit_rect": in_audit, "deepest_in_audit": round(best_audit, 2),
        "door_reachable_within_8u": None if door_d is None else round(door_d, 2),
        "centre_cell_walkable": bool(centre_reachable),
        "nearest_reachable_to_centre_within_8u": None if centre_d is None else round(centre_d, 2),
    }
    print(f"{name:<16} {f'{w:g}×{d:g}':<7} {len(circles):<5} {corner_dist:<7.2f} {clip:<6.2f} {str(in_body):<11} {best_body:<8.2f} {str(in_audit):<12} {best_audit:<8.2f} {str(door_d is not None):<8} {str(bool(centre_reachable)):<8}")

# summary lines for the answer
print("\n--- summary ---")
new_names = ["Bakery", "Café", "Workshop", "General Store", "Library", "Academy",
             "Maker Space", "Growth B", "Growth C"]
for n in new_names:
    r = results[n]
    print(f"{n}: corner {r['corner_dist']}u (clip {r['corner_clip']}u), "
          f"BFS deepest in body {r['deepest_in_body']}u, centre walkable: {r['centre_cell_walkable']}, "
          f"door within 8u: {r['door_reachable_within_8u'] is not None}")
old_clip = [(n, r["corner_clip"]) for n, r in results.items() if n not in new_names and n != "Hearth Hall"]
print("pre-existing v26 10x8 houses with clip>0:",
      [(n, c) for n, c in old_clip if c > 0])
print("any house centre walkable:", [n for n, r in results.items() if r["centre_cell_walkable"]])
print("any door unreachable:", [n for n, r in results.items() if r["door_reachable_within_8u"] is None])

json.dump({"file_sha": "cfc824dd478a1c08a15eaf5ecc275abb452e6c8dc92020be5fefa1ddb2af44b9",
           "discs_total": len(ALL_CIRCLES), "houses": results},
          open(OUT, "w"), indent=1)
print(f"\nresults -> {OUT}")
