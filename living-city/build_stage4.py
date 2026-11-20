#!/usr/bin/env python3
"""Build the Stage 4 Living City patch (Park) as EXECUTABLE CODE against
game v26+Stage2+Stage3.

Input : ~/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2s3.html
        (83,519 B, sha 7a312ae234cc3cdb4595f732da6325c8679b122e1ed654b94f589a2f6364b79d)
Output: ~/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2s3s4.html
Rules : new file only; v26s2s3 untouched. Every replacement is an exact string
        asserted to occur exactly once. Houses[] kit entries for the two
        homes; the park is display-only kit (pond, benches, lamps, paths,
        fixed trees). No new lights, no quest/save/NPC/API changes, no CDN
        or external assets, no trading.

Stage 4 (prop-36ee3e9f §1.3 / §3): Growth B (-38,38) 8x8 h5 gable;
Growth C (52,-28) 8x8 h5 porch; City Park (70,32) 40x25 with a pond disc
r5, 4 benches, 3 plazaLanterns, a ring path + a strip to the east path,
and 6 park trees at (55,28),(59,44),(75,20),(77,44),(91,28),(95,44).

Design notes (build-time decisions, recorded for the audit):
- The 6 park trees use FIXED values — they must NOT consume the global
  rnd() sequence, or the scatter positions shift (same rule as the
  fixed trees in v24).
- The ring path is 4 walkPlane segments forming a rectangle around the
  pond (N/S at z 26/38, W/E at x 64/76) — NOT one plane across the pond,
  which would lay cobble over the water (the path plane sits at y 0.06,
  above the pond disc at y 0.04).
- The strip walkPlane(1,20,70,10) runs z 0..20 and meets the park's north
  edge (z 19.5), joining the east path — a T-junction, flat plane, no
  collision (same as the Stage 1 strips).
- Park benches face the pond: the north pair (z 26) has its backrest on
  the north side, the south pair (z 38) on the south side.
- The pond centre stone is NOT an occluder (small rock inside a
  no-collision pond); only the fountain basin (Stage 2) joins
  cameraOccluders, per the CITY_AUDIT.md recommendation.
- Colours are build-time choices: Growth B warm 0x8a7a5a/0x4a3a20,
  Growth C green 0x7a8a6a/0x334155; pond canvas blue 0x3b82f6/0x60a5fa.
"""
import hashlib

V26S2S3 = "/home/hatch/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2s3.html"
OUT = "/home/hatch/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2s3s4.html"
V26S2S3_SHA = "36941466d2c5092107dd0e4c352bc6e1945a9ffc219ab0b07bd4141342b53c61"

src = open(V26S2S3, encoding="utf-8").read()
h = hashlib.sha256(src.encode()).hexdigest()
assert h == V26S2S3_SHA, f"v26s2s3 sha mismatch: {h}"
print(f"v26s2s3 verified: sha {h[:12]}..., {len(src.encode())} bytes")

def rep(old, new, tag):
    global src
    n = src.count(old)
    assert n == 1, f"{tag}: anchor occurs {n}x (want 1): {old[:70]!r}"
    src = src.replace(old, new)
    print(f"  applied {tag}")

# --- R1: houses[] — Growth B + Growth C --------------------------------------
old = """ {x:-88,z:32,label:'Maker Space',c:0x7a5a3a,roof:0x5b2d16,roofType:'dome',w:10,h:7,d:8},
];"""
new = """ {x:-88,z:32,label:'Maker Space',c:0x7a5a3a,roof:0x5b2d16,roofType:'dome',w:10,h:7,d:8},
 // STAGE 4 — Living City Park (prop-36ee3e9f): Growth B (gable), Growth C (porch)
 {x:-38,z:38,label:'Growth B',c:0x8a7a5a,roof:0x4a3a20,roofType:'gable',w:8,h:5,d:8},
 {x:52,z:-28,label:'Growth C',c:0x7a8a6a,roof:0x334155,roofType:'porch',w:8,h:5,d:8},
];"""
rep(old, new, "R1 houses[] growth homes")

# --- R2: City Park block, before Market props ---------------------------------
# (anchor: the Stage 2 plaza IIFE close + the Market props comment — the
#  plain `});` anchor Stage 2 used was consumed by Stage 2's own replacement)
old = """})();
// Market props — display only (v20, from the owner's screenshots)"""
new = """})();
// ================= STAGE 4 — City Park (prop-36ee3e9f) =================
// Display-only park: pond disc r5 (no collision, no water sim) + centre
// stone + glow sprite; 4 benches facing the pond; 3 plazaLanterns; ring
// path (4 segments around the pond) + strip to the east path; 6 FIXED park
// trees (fixed values — they must NOT consume the global rnd() sequence).
// No new lights, no quest/save/NPC/API changes, no trading.
(function(){
  // Pond — same canvas pattern as walkPlane, on a disc.
  const c=document.createElement('canvas'); c.width=64; c.height=64; const g=c.getContext('2d');
  g.fillStyle='#3b82f6'; g.fillRect(0,0,64,64); g.fillStyle='#60a5fa';
  for(let i=0;i<8;i++){ g.fillRect(8+i*6,10+i*5,14,2); }
  const tex=new THREE.CanvasTexture(c); tex.wrapS=tex.wrapT=THREE.RepeatWrapping;
  const pond=new THREE.Mesh(new THREE.CircleGeometry(5,28),new THREE.MeshStandardMaterial({map:tex}));
  pond.rotation.x=-Math.PI/2; pond.position.set(70,0.04,32); pond.receiveShadow=true; scene.add(pond);
  cyl(0.5,0.65,1.4,0x78716c,70,0.7,32);
  const pglow=glowSprite(0x60a5fa,2.0); pglow.position.set(70,1.6,32); scene.add(pglow);
  // Benches facing the pond — dir -1 = north pair (backrest north), +1 = south pair (backrest south).
  [[62,26,-1],[78,26,-1],[62,38,1],[78,38,1]].forEach(([x,z,dir])=>{
    box(2.4,0.45,0.9,0x5a3a1e,x,0.55,z);
    box(0.35,0.55,0.9,0x5a3a1e,x-0.95,0.28,z); box(0.35,0.55,0.9,0x5a3a1e,x+0.95,0.28,z);
    const back=box(2.4,0.9,0.22,0x5a3a1e,x,1.15,z+dir*0.45); back.rotation.x=-dir*0.15;
  });
  // Lamps (plazaLantern kit, same as Stage 1 square lamps).
  plazaLantern(58,22); plazaLantern(82,22); plazaLantern(70,44);
  // Ring path (4 segments around the pond) + strip to the east path.
  walkPlane(12,1,70,26); walkPlane(12,1,70,38); walkPlane(1,11,64,32); walkPlane(1,11,76,32);
  walkPlane(1,20,70,10);
  // 6 park trees — FIXED values, no rnd() calls.
  [[55,28],[59,44],[75,20],[77,44],[91,28],[95,44]].forEach(([x,z])=>{
    cyl(0.6,0.8,3.0,0x5a3a1e,x,1.5,z);
    const can=new THREE.Mesh(new THREE.SphereGeometry(2.8,10,8),mat(0x3a7a3a));
    can.position.set(x,4.5,z); can.castShadow=true; scene.add(can);
  });
})();
// Market props — display only (v20, from the owner's screenshots)"""
rep(old, new, "R2 city park")

open(OUT, "w", encoding="utf-8").write(src)
h2 = hashlib.sha256(src.encode()).hexdigest()
print(f"wrote {OUT}")
print(f"v26s2s3s4: sha {h2}, {len(src.encode())} bytes (+{len(src.encode())-83519} vs v26s2s3)")
print("replacements applied: R1 houses[] growth homes, R2 city park")
