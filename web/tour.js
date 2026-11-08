// Qingyun — 360° path-traced tour.
// Each scene is an equirectangular panorama rendered in Blender Cycles from the
// same model and lighting as the 4K stills (image centre = north, 6144 x 3072).
import * as THREE from 'three';

const D2R = Math.PI / 180;
const B = (x, y, z) => new THREE.Vector3(x, z, -y);   // Blender Z-up -> three Y-up

const SCENES = [
  { id: 'P1_aerial_golden', name: 'Aerial', pos: [-300, -1000, 230], yaw: 17, pitch: -12,
    h: 'Shanshui master plan',
    d: 'Lake → causeway → gorge → Lotus hub, one axis facing south. The terraced “mountains” are wetland green roofs over the car parks; the lake stores ~2 million m³ of stormwater under 85 floating-PV islands; lily-pad vertiports line the shore.' },
  { id: 'P2_sky_well', name: 'Sky Well', pos: [-15.75, -58.6, 13.7], yaw: 15, pitch: -14,
    h: 'Chilled vortex · 58 m',
    d: 'All rain on the 200,000 m² inverted-lotus roof funnels to the 32 m oculus and falls 58 m past nine garden terraces to the maglev station. Fed with 13 °C water — below the hall’s dew point — the curtain is a giant air-washer: it cools and dehumidifies instead of adding humidity.' },
  { id: 'P3_gorge', name: 'Gorge', pos: [0, -420, 9], yaw: 0, pitch: 3,
    h: 'Water-curtain gateway',
    d: 'Roads arrive through a gorge cut between terraced hills; its river carries stormwater from the hub to the lake. The roof eave sheds a water curtain with openings at the doors. Ginkgo and maple ribbons mark every terrace lip.' },
  { id: 'P4_above_oculus', name: 'Oculus', pos: [-55, -80, 85], yaw: 34, pitch: -27,
    h: 'Log-polar spiral gridshell',
    d: '19,296 nodes in two conformal spiral families (96 → 192): every panel is a near-square diamond that grows with radius, from 1 m at the oculus to 9 m at the eaves. 74 % semi-transparent BIPV, 26 % clear “veins” that daylight the hall.' },
  { id: 'P5_apron', name: 'Apron', pos: [-110, 330, 12], yaw: 38, pitch: -3,
    h: 'Leaf piers',
    d: 'Five leaf-shaped piers, 75 contact stands, farthest gate ≈ 700 m from central security. PV roofs with herring-bone skylight veins; pre-conditioned air and 400 Hz power at every stand so APUs stay off.' },
  { id: 'P6_blue_hour', name: 'Blue hour', pos: [700, 500, 300], yaw: 234, pitch: -19,
    h: 'Blue hour',
    d: 'Runway pairs 780 m apart allow segregated operations (≥ 760 m, ICAO); the two pairs are 3.1 km apart and fully independent. Horseshoe taxiways keep every road off the airfield.' },
];

const RENDERS = [
  ['01_aerial_golden_hour', 'Aerial at golden hour'],
  ['04_sky_well_interior', 'Sky Well — the 58 m chilled vortex'],
  ['03_gorge_gateway', 'Gorge gateway and water curtain'],
  ['02_blue_hour', 'Blue hour'],
  ['07_oculus_vortex', 'The oculus and spiral gridshell'],
  ['05_pier_apron', 'Leaf pier and apron'],
  ['06_masterplan', 'Master plan'],
];

// ---------------------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ antialias: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.NoToneMapping;          // panoramas are already graded (AgX)
document.body.prepend(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(innerWidth < innerHeight ? 85 : 70, innerWidth / innerHeight, 0.1, 2000);

const maxTex = renderer.capabilities.maxTextureSize;
const small = Math.min(screen.width, screen.height) * devicePixelRatio < 900;
const FULL = maxTex >= 6144 && !small ? '6k' : '4k';

const vert = `varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const frag = `
  uniform sampler2D map; uniform float opacity; varying vec3 vDir;
  #define PI 3.141592653589793
  void main(){
    vec3 d = normalize(vDir);
    vec2 uv = vec2(0.5 + atan(d.x, -d.z) / (2.0 * PI), 0.5 + asin(clamp(d.y, -1.0, 1.0)) / PI);
    vec2 dx = dFdx(uv), dy = dFdy(uv);
    float u2 = fract(uv.x + 0.5);                 // seam-free derivatives across u = 0/1
    float dx2 = dFdx(u2), dy2 = dFdy(u2);
    if (abs(dx2) < abs(dx.x)) dx.x = dx2;
    if (abs(dy2) < abs(dy.x)) dy.x = dy2;
    gl_FragColor = vec4(textureGrad(map, uv, dx, dy).rgb, opacity);
    #include <colorspace_fragment>
  }`;
const geo = new THREE.SphereGeometry(500, 96, 48);

function makeSphere(tex) {
  const m = new THREE.ShaderMaterial({ uniforms: { map: { value: tex }, opacity: { value: 0 } },
    vertexShader: vert, fragmentShader: frag, side: THREE.BackSide, transparent: true, depthTest: false, depthWrite: false });
  const s = new THREE.Mesh(geo, m);
  scene.add(s);
  return s;
}

const loader = new THREE.TextureLoader();
function loadTex(url) {
  return new Promise((res, rej) => loader.load(url, t => {
    t.colorSpace = THREE.SRGBColorSpace;
    t.minFilter = THREE.LinearMipmapLinearFilter;
    t.anisotropy = renderer.capabilities.getMaxAnisotropy();
    t.generateMipmaps = true;
    res(t);
  }, undefined, rej));
}

// ---------------------------------------------------------------------------
// view control (yaw / pitch with inertia, fov zoom)
let yaw = 0, pitch = 0, vYaw = 0, vPitch = 0, idle = 0, dragging = false, lx = 0, ly = 0;
const el = renderer.domElement;
const pointers = new Map();
let pinch0 = 0, fov0 = camera.fov;
el.addEventListener('pointerdown', e => {
  el.setPointerCapture(e.pointerId); pointers.set(e.pointerId, [e.clientX, e.clientY]);
  dragging = true; lx = e.clientX; ly = e.clientY; vYaw = vPitch = 0; idle = 0;
  if (pointers.size === 2) { const [a, b] = [...pointers.values()]; pinch0 = Math.hypot(a[0] - b[0], a[1] - b[1]); fov0 = camera.fov; }
});
el.addEventListener('pointermove', e => {
  if (!pointers.has(e.pointerId)) return;
  pointers.set(e.pointerId, [e.clientX, e.clientY]);
  if (pointers.size === 2) {
    const [a, b] = [...pointers.values()]; const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
    camera.fov = THREE.MathUtils.clamp(fov0 * pinch0 / d, 25, 95); camera.updateProjectionMatrix(); return;
  }
  const k = camera.fov / innerHeight;
  const dx = (e.clientX - lx) * k, dy = (e.clientY - ly) * k;
  lx = e.clientX; ly = e.clientY;
  yaw -= dx; pitch += dy; vYaw = -dx * 30; vPitch = dy * 30; idle = 0;
});
const up = e => { pointers.delete(e.pointerId); if (!pointers.size) dragging = false; };
el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
el.addEventListener('wheel', e => {
  e.preventDefault(); idle = 0;
  camera.fov = THREE.MathUtils.clamp(camera.fov * Math.exp(e.deltaY * 0.0012), 25, 95); camera.updateProjectionMatrix();
}, { passive: false });

// ---------------------------------------------------------------------------
// scenes, hotspots, info
const sceneBar = document.getElementById('scenes');
const info = document.getElementById('info');
const hots = document.getElementById('hots');
const load = document.getElementById('load');
info.querySelector('.close').onclick = () => (info.style.display = 'none');
let cur = null, sphere = null, token = 0;

SCENES.forEach((s, i) => {
  const b = document.createElement('button'); b.textContent = s.name; b.onclick = () => go(i); s.btn = b; sceneBar.appendChild(b);
});

function dirTo(from, to) { return B(...to).sub(B(...from)).normalize(); }

async function go(i, instant = false) {
  const s = SCENES[i];
  const my = ++token;
  SCENES.forEach(x => x.btn.classList.toggle('on', x === s));
  info.style.display = 'block';
  info.querySelector('h3').textContent = s.h;
  info.querySelector('p').textContent = s.d;
  history.replaceState(null, '', '?scene=' + s.id.slice(0, 2).toLowerCase());
  load.style.opacity = 1;
  const prev = sphere;
  const pre = await loadTex(`panos/${s.id}_2k.jpg`);
  if (my !== token) return;
  const sp = makeSphere(pre);
  sp.renderOrder = 2;
  sphere = sp;
  cur = s;
  yaw = s.yaw * D2R; pitch = s.pitch * D2R; vYaw = vPitch = 0;
  buildHots(i);
  fade(sp, prev, instant ? 0.01 : 0.9);
  loadTex(`panos/${s.id}_${FULL}.jpg`).then(t => {
    if (my !== token) { t.dispose(); return; }
    sp.material.uniforms.map.value.dispose();
    sp.material.uniforms.map.value = t;
    load.style.opacity = 0;
  });
}
function fade(sp, prev, dur) {
  const t0 = performance.now();
  const step = () => {
    const k = Math.min(1, (performance.now() - t0) / (dur * 1000));
    sp.material.uniforms.opacity.value = k * k * (3 - 2 * k);
    if (k < 1) requestAnimationFrame(step);
    else if (prev) { scene.remove(prev); prev.material.uniforms.map.value.dispose(); prev.material.dispose(); }
  };
  step();
  if (prev) prev.renderOrder = 1;
}
function buildHots(i) {
  hots.innerHTML = '';
  SCENES.forEach((t, j) => {
    if (j === i || t.available === false) return;
    const h = document.createElement('div'); h.className = 'hot';
    h.innerHTML = `<i></i><span>${t.name}</span>`;
    h.onclick = () => go(j);
    h._vec = dirTo(SCENES[i].pos, t.pos);
    hots.appendChild(h);
  });
}
const tmp = new THREE.Vector3();
function placeHots() {
  for (const h of hots.children) {
    tmp.copy(h._vec).multiplyScalar(100).applyMatrix4(camera.matrixWorldInverse);
    if (tmp.z > -1) { h.style.display = 'none'; continue; }
    tmp.applyMatrix4(camera.projectionMatrix);
    h.style.display = 'flex';
    h.style.left = ((tmp.x * 0.5 + 0.5) * innerWidth) + 'px';
    h.style.top = ((-tmp.y * 0.5 + 0.5) * innerHeight) + 'px';
  }
}

// ---------------------------------------------------------------------------
// gallery + lightbox
const gal = document.getElementById('gallery'), grid = document.getElementById('grid');
const lb = document.getElementById('lb'), lbbar = document.getElementById('lbbar'), lbimg = lb.querySelector('img');
RENDERS.forEach(([f, cap]) => {
  const fig = document.createElement('figure');
  fig.innerHTML = `<img loading="lazy" src="thumbs/${f}.jpg" alt="${cap}"><figcaption>${cap}</figcaption>`;
  fig.onclick = () => { lbimg.src = `../renders/${f}.jpg`; document.getElementById('lbfull').href = `../renders/${f}.jpg`;
    lb.classList.remove('zoom'); lb.style.display = 'block'; lbbar.style.display = 'flex'; };
  grid.appendChild(fig);
});
document.getElementById('gbtn').onclick = () => (gal.style.display = 'block');
document.getElementById('gclose').onclick = () => (gal.style.display = 'none');
lb.onclick = () => lb.classList.toggle('zoom');
document.getElementById('lbclose').onclick = () => { lb.style.display = 'none'; lbbar.style.display = 'none'; };
addEventListener('keydown', e => {
  if (e.key === 'Escape') { if (lb.style.display === 'block') document.getElementById('lbclose').click(); else gal.style.display = 'none'; }
  const i = SCENES.indexOf(cur);
  const av = SCENES.map((s, k) => k).filter(k => SCENES[k].available);
  const p = av.indexOf(i);
  if (e.key === 'ArrowRight' && gal.style.display !== 'block') go(av[(p + 1) % av.length]);
  if (e.key === 'ArrowLeft' && gal.style.display !== 'block') go(av[(p + av.length - 1) % av.length]);
});

// ---------------------------------------------------------------------------
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight);
});
const q = new URLSearchParams(location.search);
// only offer scenes whose panorama has been published (they are rendered progressively)
Promise.all(SCENES.map(s => fetch(`panos/${s.id}_2k.jpg`, { method: 'HEAD' }).then(r => r.ok).catch(() => false)))
  .then(ok => {
    SCENES.forEach((s, i) => { s.available = ok[i]; s.btn.style.display = ok[i] ? '' : 'none'; });
    let start = SCENES.findIndex(s => s.available && s.id.slice(0, 2).toLowerCase() === (q.get('scene') || 'p1'));
    if (start < 0) start = SCENES.findIndex(s => s.available);
    if (start >= 0) go(start, true).then(() => (window.__ready = true));
  });
if (q.has('gallery')) gal.style.display = 'block';

const clock = new THREE.Clock();
const look = new THREE.Vector3();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1);
  idle += dt;
  if (!dragging) {
    yaw += vYaw * dt; pitch += vPitch * dt;
    vYaw *= Math.pow(0.04, dt); vPitch *= Math.pow(0.04, dt);
    if (idle > 6 && !q.has('still')) yaw += 0.025 * dt * Math.min(1, (idle - 6) / 3);   // gentle auto-pan
  }
  pitch = THREE.MathUtils.clamp(pitch, -88 * D2R, 88 * D2R);
  look.set(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), -Math.cos(yaw) * Math.cos(pitch));
  camera.lookAt(look);
  camera.updateMatrixWorld();
  placeHots();
  renderer.render(scene, camera);
});
