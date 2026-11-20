#!/usr/bin/env python3
"""Build the Stage 2 Living City patch (Market District) as EXECUTABLE CODE
against game v26.

Input : ~/workspace/game-collab-api/city-proposal/hearth-3d-game-v2-v26.html
        (79,828 B, sha f27d758d054f84d76447a0be993f0605117643db35f7af97d94e753327a37f5b)
Output: ~/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2.html
Rules : new file only; v26 untouched. Every replacement is an exact string
        asserted to occur exactly once. Geometry/content only — no quest,
        save, NPC, API, or network changes. No new lights. No money.

Stage 2 (prop-36ee3e9f §1.3 / §3): Bakery (-30,62), Cafe (30,64),
Workshop (-32,84), General Store (32,86) — 10x8, 2 storeys (h8), new
'shop' roofType (flat parapet roof kit + striped awning + second winRow);
two new stalls (-20,74), (20,74) in the existing stalls[] kit (display-only,
flavour lines only); market plaza cobble disc r6 + fountain (basin +
centre stone + glow sprite) at (0,88) + two benches facing it at
(-4.5,92),(4.5,92) (bench positions pinned at build time — the proposal
pins the plaza and the benches but not their coordinates; rule: flanking
the plaza's south edge, facing the fountain).

Stalls and shops are display-only — interact shows a flavour line, same as
the existing stalls. Market path (x 0, z 45..75) stays clear.
"""
import hashlib

V26 = "/home/hatch/workspace/game-collab-api/city-proposal/hearth-3d-game-v2-v26.html"
OUT = "/home/hatch/workspace/game-collab-api/city-proposal/stage234/hearth-3d-game-v2-v26s2.html"
V26_SHA = "f27d758d054f84d76447a0be993f0605117643db35f7af97d94e753327a37f5b"

src = open(V26, encoding="utf-8").read()
h = hashlib.sha256(src.encode()).hexdigest()
assert h == V26_SHA, f"v26 sha mismatch: {h}"
print(f"v26 verified: sha {h[:12]}..., {len(src)} bytes")

def rep(old, new, tag):
    global src
    n = src.count(old)
    assert n == 1, f"{tag}: anchor occurs {n}x (want 1): {old[:70]!r}"
    src = src.replace(old, new)
    print(f"  applied {tag}")

# --- R1: houses[] — 4 shops ---------------------------------------------------
old = """ {x:30,z:50,label:"Meta AI Lodge",c:0x7a6a4a,roof:0x4a3a20,roofType:'gable',w:8,h:5,d:8},
];"""
new = """ {x:30,z:50,label:"Meta AI Lodge",c:0x7a6a4a,roof:0x4a3a20,roofType:'gable',w:8,h:5,d:8},
 // STAGE 2 — Living City Market District (prop-36ee3e9f): 4 shops, 2 storeys (collision + minimap automatic via houses[])
 {x:-30,z:62,label:'Bakery',c:0xc2703d,roof:0x7c2d12,roofType:'shop',w:10,h:8,d:8},
 {x:30,z:64,label:'Café',c:0x7a8a4a,roof:0x4a3a20,roofType:'shop',w:10,h:8,d:8},
 {x:-32,z:84,label:'Workshop',c:0x5a7a9a,roof:0x334155,roofType:'shop',w:10,h:8,d:8},
 {x:32,z:86,label:'General Store',c:0x9a6a2a,roof:0x5b2d16,roofType:'shop',w:10,h:8,d:8},
];"""
rep(old, new, "R1 houses[] shops")

# --- R2: shops get the second window row (2 storeys) ---------------------------
old = " if(h.roofType==='flat'||h.roofType==='hall') winRow(6); // STAGE 1: hall gets the second window row too"
new = " if(h.roofType==='flat'||h.roofType==='hall'||h.roofType==='shop') winRow(6); // STAGE 2: shops get the second window row too (2 storeys)"
rep(old, new, "R2 winRow")

# --- R3: 'shop' roof branch — flat parapet roof (kit) + striped awning --------
old = """  } else {
    const dome=new THREE.Mesh(new THREE.SphereGeometry(5.5,20,12,0,Math.PI*2,0,Math.PI/2),mat(h.roof));"""
new = """  } else if(h.roofType==='shop'){ // STAGE 2: 2-storey shop — flat parapet roof (kit) + striped awning
    const slab=box(h.w+0.6,0.4,h.d+0.6,0x44403c,h.x,top+0.2,h.z);
    box(h.w+0.6,0.5,0.3,0x44403c,h.x,top+0.6,front+0.15); box(h.w+0.6,0.5,0.3,0x44403c,h.x,top+0.6,h.z-h.d/2-0.15);
    box(0.3,0.5,h.d+0.6,0x44403c,h.x-h.w/2-0.15,top+0.6,h.z); box(0.3,0.5,h.d+0.6,0x44403c,h.x+h.w/2+0.15,top+0.6,h.z);
    const awn=new THREE.Mesh(new THREE.BoxGeometry(4.6,0.25,2.0),stripeMat('#c96a3a','#f5f0e6')); awn.position.set(h.x,3.1,front+1.0); awn.castShadow=true; awn.receiveShadow=true; scene.add(awn);
    box(0.25,3.0,0.25,0x3a2c1e,h.x-2.0,1.5,front+1.8); box(0.25,3.0,0.25,0x3a2c1e,h.x+2.0,1.5,front+1.8);
    box(0.8,2.4,0.8,0x57534e,h.x+3.5,top+1.2,h.z+2);
  } else {
    const dome=new THREE.Mesh(new THREE.SphereGeometry(5.5,20,12,0,Math.PI*2,0,Math.PI/2),mat(h.roof));"""
rep(old, new, "R3 shop roof")

# --- R4: two new stalls in the existing stalls[] kit ---------------------------
old = "const stalls=[{x:-12,z:58,say:'Miro runs the Press Office. He edits the Chronicle.'},{x:12,z:60,say:'Zing runs the Lucky Corner. Good luck lives here.'}];"
new = """const stalls=[{x:-12,z:58,say:'Miro runs the Press Office. He edits the Chronicle.'},{x:12,z:60,say:'Zing runs the Lucky Corner. Good luck lives here.'},
 // STAGE 2 — second stall row (display-only, flavour lines only, no trading)
 {x:-20,z:74,say:'Fresh bread, still warm from the oven.'},{x:20,z:74,say:'Tools, trinkets, and things that hum.'}];"""
rep(old, new, "R4 stalls")

# --- R5: market plaza disc + fountain + two benches, before Market props -------
old = """});
// Market props — display only (v20, from the owner's screenshots)"""
new = """});
// ================= STAGE 2 — Market plaza + fountain (prop-36ee3e9f) =================
// Cobble disc r6 + display-only fountain (basin + centre stone + glow sprite,
// no water sim). The basin joins cameraOccluders like the fire base. Two
// benches flank the plaza's south edge, facing the fountain. No new lights,
// no quest/save/NPC/API changes, no trading.
(function(){
  // Cobble disc — same canvas pattern as walkPlane, on a circle.
  const c=document.createElement('canvas'); c.width=64; c.height=64; const g=c.getContext('2d');
  g.fillStyle='#8a7a63'; g.fillRect(0,0,64,64); g.fillStyle='#6b5d49';
  for(let i=0;i<=4;i++){ g.fillRect(i*16,0,2,64); g.fillRect(0,i*16,64,2); }
  const tex=new THREE.CanvasTexture(c); tex.wrapS=tex.wrapT=THREE.RepeatWrapping;
  const disc=new THREE.Mesh(new THREE.CircleGeometry(6,28),new THREE.MeshStandardMaterial({map:tex}));
  disc.rotation.x=-Math.PI/2; disc.position.set(0,0.04,88); disc.receiveShadow=true; scene.add(disc);
  // Fountain: basin (occluder, like the fire base) + water disc + centre stone + glow.
  const basin=cyl(1.8,2.0,0.8,0x78716c,0,0.4,88); cameraOccluders.push(basin);
  const water=new THREE.Mesh(new THREE.CircleGeometry(1.6,20),new THREE.MeshStandardMaterial({color:0x7dd3fc,emissive:0x38bdf8,emissiveIntensity:0.4}));
  water.rotation.x=-Math.PI/2; water.position.set(0,0.75,88); scene.add(water);
  cyl(0.5,0.65,1.4,0x78716c,0,0.7,88);
  const fglow=glowSprite(0x7dd3fc,2.0); fglow.position.set(0,1.6,88); scene.add(fglow);
  // Benches facing the fountain — backrest SOUTH so sitters face north to it.
  [[-4.5,92],[4.5,92]].forEach(([x,z])=>{
    box(2.4,0.45,0.9,0x5a3a1e,x,0.55,z);
    box(0.35,0.55,0.9,0x5a3a1e,x-0.95,0.28,z); box(0.35,0.55,0.9,0x5a3a1e,x+0.95,0.28,z);
    const back=box(2.4,0.9,0.22,0x5a3a1e,x,1.15,z+0.45); back.rotation.x=-0.15;
  });
})();
// Market props — display only (v20, from the owner's screenshots)"""
rep(old, new, "R5 plaza+fountain")

open(OUT, "w", encoding="utf-8").write(src)
h2 = hashlib.sha256(src.encode()).hexdigest()
print(f"wrote {OUT}")
print(f"v26s2: sha {h2}, {len(src.encode())} bytes (+{len(src.encode())-79828} vs v26)")
print("replacements applied: R1 houses[] shops, R2 winRow, R3 shop roof, R4 stalls, R5 plaza+fountain")
