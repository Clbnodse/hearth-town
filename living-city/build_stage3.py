#!/usr/bin/env python3
"""Build the Stage 3 Living City patch (Civic / learning west) as EXECUTABLE
CODE against game v26+Stage2.

Input : ~/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2.html
        (83,139 B, sha 24337e7805fff347c1ca30f246cf6ae3492f92ef58d55d1721c163b58c196129)
Output: ~/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2s3.html
Rules : new file only; v26s2 untouched. Every replacement is an exact string
        asserted to occur exactly once. Houses[] kit entries only — collision
        + minimap automatic. No new lights, no quest/save/NPC/API changes,
        no CDN or external assets, no trading.

Stage 3 (prop-36ee3e9f §1.3 / §3): Library (-70,-28) 12x9 h9 gable;
Academy (-70,28) 12x9 h9 flat; Maker Space (-88,32) 10x8 h7 dome.
All three are plain houses[] entries — the kit handles their heights
generically. Note: the kit gives every house ONE window row (winRow(2.5));
the second row is flat/hall/shop only, so the Library (gable) has the
standard single row despite its 12u width — verified by the mesh counter
(Library 18 = the standard gable count).

NOT built: the west-street lamps/planters (§3) — no coordinates are pinned
in the proposal, so there is nothing executable to build; flagged as an
open/unpinned item in SUMMARY.md.

Colours are build-time choices (the proposal pins footprints, heights and
roof types, not colours): Library warm stone 0x8a6a4a/0x4a3a20, Academy
slate 0x6a7a8a/0x334155, Maker Space workshop brown 0x7a5a3a/0x5b2d16.
"""
import hashlib

V26S2 = "/home/hatch/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2.html"
OUT = "/home/hatch/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2s3.html"
V26S2_SHA = "24337e7805fff347c1ca30f246cf6ae3492f92ef58d55d1721c163b58c196129"

src = open(V26S2, encoding="utf-8").read()
h = hashlib.sha256(src.encode()).hexdigest()
assert h == V26S2_SHA, f"v26s2 sha mismatch: {h}"
print(f"v26s2 verified: sha {h[:12]}..., {len(src.encode())} bytes")

def rep(old, new, tag):
    global src
    n = src.count(old)
    assert n == 1, f"{tag}: anchor occurs {n}x (want 1): {old[:70]!r}"
    src = src.replace(old, new)
    print(f"  applied {tag}")

# --- R1: houses[] — 3 civic buildings ----------------------------------------
old = """ {x:32,z:86,label:'General Store',c:0x9a6a2a,roof:0x5b2d16,roofType:'shop',w:10,h:8,d:8},
];"""
new = """ {x:32,z:86,label:'General Store',c:0x9a6a2a,roof:0x5b2d16,roofType:'shop',w:10,h:8,d:8},
 // STAGE 3 — Living City Civic / learning west (prop-36ee3e9f): Library (gable), Academy (flat), Maker Space (dome)
 {x:-70,z:-28,label:'Library',c:0x8a6a4a,roof:0x4a3a20,roofType:'gable',w:12,h:9,d:9},
 {x:-70,z:28,label:'Academy',c:0x6a7a8a,roof:0x334155,roofType:'flat',w:12,h:9,d:9},
 {x:-88,z:32,label:'Maker Space',c:0x7a5a3a,roof:0x5b2d16,roofType:'dome',w:10,h:7,d:8},
];"""
rep(old, new, "R1 houses[] civic")

# --- R2: sign fix (2026-11-17 teleport verification) -------------------------
# The kit placed every sign at the FIXED offset h.z+4.15, but the front face
# sits at h.z + h.d/2. For d=8 that is 0.15u proud of the wall (fine); for
# the new d=9 Library/Academy the sign landed 0.35u INSIDE the body and was
# invisible in-game (Maker Space d=8 and all v26 houses were unaffected).
# Fix: put the sign on the front face for every depth. For d=8 and the Hall
# this is byte-identical placement (front+0.15 == z+4.15 / the old hall case).
old = "  houseSign(h.label,h.x,5.2,h.roofType==='hall'?front+0.15:h.z+4.15); // STAGE 1: hall sign on its front face (d=10)"
new = "  houseSign(h.label,h.x,5.2,front+0.15); // STAGE 3 FIX: sign on the front face for every depth (d=9 Library/Academy were buried at fixed z+4.15)"
rep(old, new, "R2 sign on front face")

open(OUT, "w", encoding="utf-8").write(src)
h2 = hashlib.sha256(src.encode()).hexdigest()
print(f"wrote {OUT}")
print(f"v26s2s3: sha {h2}, {len(src.encode())} bytes (+{len(src.encode())-83139} vs v26s2)")
print("replacements applied: R1 houses[] civic, R2 sign on front face")
