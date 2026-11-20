// Stage 2-4 mesh/draw-call counter: run a game HTML file in the node stub
// (real three-r128.min.js) and count meshes / sprites / materials / lights /
// occluders, per-house mesh counts, rect-based counts for the stage's new
// buildings, and near-counts for the stage's new kit items.
// Usage: node mesh_count_234.js <game-html-path> <stage-spec-json> <out-json-path>
// Adapted from stage1/stage1_mesh_count.js — same stub prelude and scene walk.
// The stage spec is {"rects": [[label, x, z, w, d], ...],
//                     "points": [[label, x, z, radius], ...]}.
const fs = require('fs');
const htmlPath = process.argv[2], specPath = process.argv[3], outPath = process.argv[4];
const html = fs.readFileSync(htmlPath, 'utf8');
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const parts = html.split('<script>');
if (parts.length < 2) { console.error('FATAL: could not find game script block'); process.exit(1); }
const gameJS = parts[1].split('</script>')[0];
const prelude = `
global.window=global;
global.innerWidth=1280; global.innerHeight=800;
global.navigator={maxTouchPoints:0}; global.devicePixelRatio=1;
const els={};
function mkEl(id){const e={id,style:{display:''},textContent:'',innerHTML:'',addEventListener(){},getContext:()=>({clearRect(){},fillRect(){},beginPath(){},arc(){},fill(){},stroke(){},moveTo(){},lineTo(){},fillText(){}}),getBoundingClientRect:()=>({left:0,top:0}),querySelectorAll:()=>[],appendChild(){}};els[id]=e;return e;}
['game','hud','pos','quest-name','quest-progress','quest-list','toast','minimap','mmap','talk','help','joy','stick','look','btn-cam','btn-interact','btn-restart','finale','btn-again','warn'].forEach(mkEl);
global.document={getElementById:id=>els[id]||mkEl(id),createElement:()=>({width:0,height:0,getContext:()=>({fillStyle:'',fillRect(){},font:'',textAlign:'',textBaseline:'',fillText(){}}),style:{}}),addEventListener(){},body:{appendChild(){},classList:{_s:new Set(),toggle(c,v){if(v)this._s.add(c);else this._s.delete(c);},contains(c){return this._s.has(c);}}},head:{appendChild(){}}};
global.localStorage={_d:{},getItem(k){return this._d[k]||null},setItem(k,v){this._d[k]=v},removeItem(k){delete this._d[k]}};
global.requestAnimationFrame=()=>{}; global.addEventListener=()=>{};
global.THREE=require('/home/hatch/workspace/muse-hub/three-r128.min.js');
THREE.WebGLRenderer=function(){return{setSize(){},setPixelRatio(){},render(){},domElement:{},shadowMap:{}};};
`;
const countCode = `

// ---- STAGE 234 COUNTS (appended before the final closing brace) ----
const __out = { houses: {}, newBuildingsRect: {}, kitPoints: {}, totalMeshes: 0, totalSprites: 0,
  totalObjects: 0, distinctMaterials: 0, lights: 0, cameraOccluders: cameraOccluders.length,
  trees: [], bushes: [], boulders: [], hallMaxTopY: null };
const __mats = new Set();
function __walk(o) {
  __out.totalObjects++;
  if (o.isMesh) { __out.totalMeshes++; if (o.material) __mats.add(o.material.uuid); }
  if (o.isSprite) { __out.totalSprites++; if (o.material) __mats.add(o.material.uuid); }
  if (o.isLight) __out.lights++;
  (o.children || []).forEach(__walk);
}
__walk(scene);
__out.distinctMaterials = __mats.size;
// Per-house mesh counts: direct scene children within 7u (xz) of the house centre (audit method).
houses.forEach(h => {
  let n = 0; const kinds = {};
  scene.children.forEach(m => {
    if (!m.isMesh) return;
    const dx = m.position.x - h.x, dz = m.position.z - h.z;
    if (Math.hypot(dx, dz) <= 7.0) { n++; const g = m.geometry ? m.geometry.type : '?'; kinds[g] = (kinds[g] || 0) + 1; }
  });
  __out.houses[h.label] = { centre: [h.x, h.z], w: h.w, h: h.h, d: h.d, roofType: h.roofType, meshes: n, kinds };
});
// Rect-based counts for the stage's new buildings (footprint + 0.5u margin).
const __rects = ${JSON.stringify(spec.rects || [])};
__rects.forEach(([label, hx, hz, w, d]) => {
  let n = 0, nSprites = 0;
  scene.children.forEach(m => {
    const inside = m.position.x >= hx - w / 2 - 0.5 && m.position.x <= hx + w / 2 + 0.5 &&
                   m.position.z >= hz - d / 2 - 0.5 && m.position.z <= hz + d / 2 + 0.5;
    if (!inside) return;
    if (m.isMesh) n++;
    if (m.isSprite) nSprites++;
  });
  __out.newBuildingsRect[label] = { meshes: n, sprites: nSprites };
});
// Near-counts for the stage's new kit items.
function __near(x, z, r) {
  let meshes = 0, sprites = 0;
  scene.children.forEach(m => {
    if (Math.hypot(m.position.x - x, m.position.z - z) <= r) {
      if (m.isMesh) meshes++;
      if (m.isSprite) sprites++;
    }
  });
  return { meshes, sprites };
}
const __points = ${JSON.stringify(spec.points || [])};
__points.forEach(([label, x, z, r]) => { __out.kitPoints[label] = { at: [x, z], ...__near(x, z, r) }; });
// Hall tower height: max top-y of any mesh inside the hall rect.
let __maxTop = -Infinity;
scene.children.forEach(m => {
  if (!m.isMesh || !m.geometry || !m.geometry.parameters) return;
  const inside = m.position.x >= -9.5 && m.position.x <= 9.5 && m.position.z >= -43.5 && m.position.z <= -31.7;
  if (!inside) return;
  const p = m.geometry.parameters;
  let half = 0;
  if (p.height !== undefined) half = p.height / 2;
  else if (p.radius !== undefined) half = p.radius;
  const top = m.position.y + half;
  if (top > __maxTop) __maxTop = top;
});
__out.hallMaxTopY = __maxTop === -Infinity ? null : +__maxTop.toFixed(2);
// Exact scatter positions (real engine values, not re-derived).
scene.children.forEach(m => {
  if (!m.isMesh || !m.geometry) return;
  const g = m.geometry.type, p = m.geometry.parameters || {};
  const col = m.material && m.material.color ? m.material.color.getHex() : null;
  if (g === 'CylinderGeometry' && col === 0x5a3a1e && p.radiusTop >= 0.4 && p.radiusTop <= 0.8)
    __out.trees.push([+m.position.x.toFixed(4), +m.position.z.toFixed(4), +(p.radiusTop || 0).toFixed(3)]);
  if (g === 'SphereGeometry' && [0x3a7a3a, 0x2f6a32, 0x4a8a42].includes(col) && m.position.y === 0.5)
    __out.bushes.push([+m.position.x.toFixed(4), +m.position.z.toFixed(4), +(p.radius || 0).toFixed(3)]);
  if (g === 'SphereGeometry' && col === 0x78716c && m.scale.x === 1.5)
    __out.boulders.push([+m.position.x.toFixed(4), +m.position.z.toFixed(4), +(p.radius || 0).toFixed(3)]);
});
console.log('COUNTS_JSON_BEGIN');
console.log(JSON.stringify(__out));
console.log('COUNTS_JSON_END');
fs.writeFileSync(outPath, JSON.stringify(__out, null, 1));
`;
const gameWithCounts = gameJS.replace(/\n\}\s*$/, '\n' + countCode + '\n}');
eval(prelude + gameWithCounts);
