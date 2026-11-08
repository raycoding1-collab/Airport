// Qingyun Shanshui International Airport — interactive viewer (three.js r170)
// Geometry comes from the Blender model (assets/qingyun.glb). Materials are
// re-created here by name so the procedural looks (PV veins, mullions, flowing
// water) survive the trip to the browser.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { Sky } from 'three/addons/objects/Sky.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const D2R = Math.PI / 180;
const B = (x, y, z) => new THREE.Vector3(x, z, -y);          // Blender Z-up -> three Y-up

// ---------------------------------------------------------------------------
// renderer / scene
// ---------------------------------------------------------------------------
const Q = new URLSearchParams(location.search);
const LITE = Q.has('lite');                     // low-power mode (no shadows / bloom), also used for headless tests
const renderer = new THREE.WebGLRenderer({ antialias: !LITE, powerPreference: 'high-performance', logarithmicDepthBuffer: true });
renderer.setPixelRatio(LITE ? 1 : Math.min(window.devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.AgXToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = !LITE;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, 1, 90000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.maxPolarAngle = 89 * D2R;
controls.minDistance = 5;
controls.maxDistance = 16000;

const sky = new Sky();
sky.scale.setScalar(80000);
scene.add(sky);
const sun = new THREE.DirectionalLight(0xffffff, 3);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
Object.assign(sun.shadow.camera, { left: -1300, right: 1300, top: 1300, bottom: -1300, near: 10, far: 9000 });
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.6;
scene.add(sun, sun.target);
const hemi = new THREE.HemisphereLight(0xbfd4ff, 0x3a3020, 0.6);
scene.add(hemi);
scene.fog = new THREE.FogExp2(0xcfd6dc, 0.00009);

const pmrem = new THREE.PMREMGenerator(renderer);
const envScene = new THREE.Scene();
const envSky = new Sky();
envSky.scale.setScalar(1000);
envScene.add(envSky);
let envRT = null;

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.35, 0.6, 0.92);
composer.addPass(bloom);
composer.addPass(new OutputPass());

// ---------------------------------------------------------------------------
// procedural textures
// ---------------------------------------------------------------------------
function canvasTex(w, h, paint, repeat = true) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  paint(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 8;
  return t;
}
function rand(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

// flowing-water streaks (alpha), tiles vertically
const streakTex = canvasTex(128, 512, (g, w, h) => {
  const r = rand(7); g.fillStyle = '#000'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 260; i++) {
    const x = r() * w, len = 60 + r() * 380, y = r() * h, a = 0.25 + r() * 0.6, wd = 0.6 + r() * 2.6;
    const gr = g.createLinearGradient(0, y, 0, y + len);
    gr.addColorStop(0, `rgba(255,255,255,0)`); gr.addColorStop(0.3, `rgba(255,255,255,${a})`); gr.addColorStop(1, `rgba(255,255,255,0)`);
    g.fillStyle = gr; g.fillRect(x, y, wd, len); g.fillRect(x, y - h, wd, len);
  }
});
// tileable ripple normal map from integer-frequency waves
function rippleNormals(size = 256) {
  const data = new Uint8Array(size * size * 4), r = rand(11), waves = [];
  for (let i = 0; i < 14; i++) waves.push([Math.round((r() - 0.5) * 16), Math.round((r() - 0.5) * 16), r() * 6.28, 0.3 + r()]);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    let dx = 0, dy = 0;
    for (const [kx, ky, ph, a] of waves) {
      const t = 2 * Math.PI * (kx * x + ky * y) / size + ph, c = Math.cos(t) * a / (1 + Math.hypot(kx, ky) * 0.15);
      dx += c * kx; dy += c * ky;
    }
    const n = new THREE.Vector3(-dx * 0.04, -dy * 0.04, 1).normalize(), o = (y * size + x) * 4;
    data[o] = (n.x * 0.5 + 0.5) * 255; data[o + 1] = (n.y * 0.5 + 0.5) * 255; data[o + 2] = (n.z * 0.5 + 0.5) * 255; data[o + 3] = 255;
  }
  const t = new THREE.DataTexture(data, size, size); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.needsUpdate = true;
  return t;
}
const ripple = rippleNormals();
const noiseTex = canvasTex(256, 256, (g, w, h) => {
  const r = rand(3), img = g.createImageData(w, h);
  for (let i = 0; i < w * h; i++) { const v = 200 + r() * 55; img.data.set([v, v, v, 255], i * 4); }
  g.putImageData(img, 0, 0);
});
const loaderTex = new THREE.TextureLoader();
const atlas = n => { const t = loaderTex.load(`assets/leaf_${n}.png`); t.colorSpace = THREE.SRGBColorSpace; return t; };
const leafAtlas = { broad: atlas('broad'), fan: atlas('fan'), narrow: atlas('narrow'), needle: atlas('needle') };
const apronMask = loaderTex.load('assets/apron_mask.png');

// ---------------------------------------------------------------------------
// materials by name
// ---------------------------------------------------------------------------
const night = { u: { value: 0 } };            // shared uniform: 0 day .. 1 night
const animated = [];
const lin = (r, g, b) => new THREE.Color().setRGB(r, g, b, THREE.LinearSRGBColorSpace);

function pv(extra) {
  const m = new THREE.MeshPhysicalMaterial({ color: lin(0.012, 0.025, 0.06), metalness: 0.15, roughness: 0.2,
    clearcoat: 1, clearcoatRoughness: 0.04, iridescence: 0.55, iridescenceIOR: 1.7, envMapIntensity: 1.3, side: THREE.DoubleSide });
  if (extra) {
    m.defines = { USE_UV: '' };
    m.onBeforeCompile = s => {
      s.uniforms.uNight = night.u;
      s.fragmentShader = 'uniform float uNight;\n' + s.fragmentShader.replace('#include <emissivemap_fragment>',
        `#include <emissivemap_fragment>
         float av = abs(1.0 - vUv.y);            // glTF flips V; Blender UV v = metres across the pier
         float vein = max(step(av, 2.6), step(fract((vUv.x - av * 1.15) / 34.0), 0.055) * step(av, 23.0));
         diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.42, 0.58, 0.6), vein * 0.85);
         totalEmissiveRadiance += vec3(1.0, 0.72, 0.45) * vein * uNight * 2.2;`);
    };
  }
  return m;
}
function glass(opacity = 0.2, tint = [0.8, 0.9, 0.9]) {
  const m = new THREE.MeshPhysicalMaterial({ color: lin(...tint), metalness: 0, roughness: 0.04, transparent: true,
    opacity, envMapIntensity: 1.6, depthWrite: false, side: THREE.DoubleSide });
  m.onBeforeCompile = s => {
    s.uniforms.uNight = night.u;
    s.fragmentShader = 'uniform float uNight;\n' + s.fragmentShader.replace('#include <emissivemap_fragment>',
      `#include <emissivemap_fragment>
       totalEmissiveRadiance += vec3(1.0, 0.75, 0.5) * uNight * 0.9;
       diffuseColor.a = mix(diffuseColor.a, 0.75, uNight * 0.6);`);
  };
  return m;
}
function facade() {
  const m = glass(0.28, [0.55, 0.68, 0.7]);
  m.defines = { USE_UV: '' };
  m.onBeforeCompile = s => {
    s.uniforms.uNight = night.u;
    s.fragmentShader = 'uniform float uNight;\n' + s.fragmentShader.replace('#include <emissivemap_fragment>',
      `#include <emissivemap_fragment>
       float mull = max(step(fract(vUv.x / 3.0), 0.045), step(fract(vUv.y / 4.5), 0.035));
       diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.03), mull);
       diffuseColor.a = mix(mix(diffuseColor.a, 0.82, uNight), 1.0, mull);
       totalEmissiveRadiance += vec3(1.0, 0.74, 0.48) * (1.0 - mull) * uNight * 1.6;`);
  };
  return m;
}
function water(col, rough = 0.05, rep = 0.02) {
  const n = ripple.clone(); n.needsUpdate = true; n.repeat.set(rep, rep);
  const m = new THREE.MeshPhysicalMaterial({ color: lin(...col), roughness: rough, metalness: 0, normalMap: n,
    normalScale: new THREE.Vector2(0.25, 0.25), envMapIntensity: 1.4, clearcoat: 0.6, clearcoatRoughness: 0.02 });
  animated.push(dt => { n.offset.x += dt * 0.004; n.offset.y += dt * 0.0025; });
  return m;
}
function fall(op = 0.85, speed = 0.55) {
  const a = streakTex.clone(); a.needsUpdate = true; a.repeat.set(0.35, 0.03);
  const m = new THREE.MeshStandardMaterial({ color: 0xf2f8fa, roughness: 0.25, transparent: true, opacity: op,
    alphaMap: a, depthWrite: false, side: THREE.DoubleSide, emissive: new THREE.Color(0x9fd8ff), emissiveIntensity: 0 });
  animated.push(dt => { a.offset.y -= dt * speed; m.emissiveIntensity = night.u.value * 0.6; });
  return m;
}
function std(c, r = 0.8, mt = 0, extra = {}) {
  return new THREE.MeshStandardMaterial(Object.assign({ color: typeof c === 'number' ? c : lin(...c), roughness: r, metalness: mt }, extra));
}
function leaf(atlasName, tone, trans = 0.35) {
  const m = new THREE.MeshStandardMaterial({ map: leafAtlas[atlasName], alphaTest: 0.5, side: THREE.DoubleSide,
    color: lin(tone[0] * 3.4, tone[1] * 3.4, tone[2] * 3.4), roughness: 0.75 });
  return m;
}
function apron() {
  const m = std(0xffffff, 0.85);
  m.map = apronMask;
  m.onBeforeCompile = s => {
    s.fragmentShader = s.fragmentShader.replace('#include <map_fragment>',
      `float k = texture2D(map, vMapUv).r;
       vec3 conc = vec3(0.40, 0.395, 0.375), grass = vec3(0.07, 0.15, 0.04);
       diffuseColor.rgb = mix(grass, conc, smoothstep(0.35, 0.65, k));`);
  };
  return m;
}
function soffit() {
  const m = std([0.75, 0.68, 0.58], 0.6);
  m.onBeforeCompile = s => {
    s.uniforms.uNight = night.u;
    s.fragmentShader = 'uniform float uNight;\n' + s.fragmentShader.replace('#include <emissivemap_fragment>',
      `#include <emissivemap_fragment>
       totalEmissiveRadiance += vec3(1.0, 0.8, 0.58) * uNight * 1.4;`);
  };
  return m;
}

const MAT = {
  pv_bipv: () => pv(false), pv_pier: () => pv(true), pv_field: () => pv(false),
  glass_clear: () => glass(0.16), glass_lowiron: () => glass(0.14, [0.9, 0.96, 0.95]), glass_facade: facade,
  glass_dark: () => new THREE.MeshPhysicalMaterial({ color: 0x0b0f12, roughness: 0.06, clearcoat: 1, envMapIntensity: 1.3 }),
  steel_white: () => std([0.84, 0.84, 0.82], 0.32), bronze_caps: () => std([0.80, 0.73, 0.62], 0.26, 0.65),
  champagne: () => std([0.80, 0.66, 0.47], 0.24, 1), aluminium: () => std([0.78, 0.79, 0.80], 0.3, 1),
  metal_dark: () => std([0.07, 0.075, 0.08], 0.35, 1), engine_metal: () => std([0.6, 0.61, 0.63], 0.28, 1),
  rubber: () => std(0x080808, 0.7),
  concrete_apron: () => std([0.40, 0.395, 0.375], 0.85, 0, { map: noiseTex }), apron_mixed: apron,
  concrete_light: () => std([0.68, 0.67, 0.64], 0.7), asphalt: () => std([0.05, 0.05, 0.055], 0.9),
  rubber_deposit: () => std(0x050505, 0.6, 0, { transparent: true, opacity: 0.35, depthWrite: false }),
  paint_white: () => std([0.78, 0.78, 0.76], 0.6), paint_yellow: () => std([0.85, 0.55, 0.04], 0.6),
  paint_red: () => std([0.6, 0.05, 0.04], 0.6), paint_green: () => std([0.05, 0.35, 0.18], 0.6),
  grass_airside: () => std([0.08, 0.16, 0.04], 1, 0, { map: noiseTex }),
  planting_terrace: () => std([0.17, 0.25, 0.05], 0.85, 0, { map: noiseTex }),
  stone_wall: () => std([0.42, 0.39, 0.34], 0.85), stone_vines: () => std([0.14, 0.2, 0.08], 0.9),
  terrazzo: () => std([0.78, 0.76, 0.72], 0.32), timber: () => std([0.52, 0.34, 0.18], 0.5),
  soil: () => std([0.15, 0.11, 0.08], 0.95), gravel_path: () => std([0.6, 0.56, 0.48], 0.85),
  interior_soffit: soffit,
  water_lake: () => water([0.01, 0.03, 0.034], 0.04, 0.004), water_clear: () => water([0.04, 0.12, 0.12], 0.04, 0.03),
  waterfall: () => fall(0.9, 0.6), cascade_thin: () => fall(0.55, 0.45),
  foam: () => std(0xffffff, 0.6, 0, { transparent: true, opacity: 0.55, depthWrite: false }),
  aircraft_wide: () => new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.25, clearcoat: 0.6 }),
  aircraft_narrow: () => new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.25, clearcoat: 0.6, color: 0xffffff }),
  aircraft_wing: () => std([0.70, 0.72, 0.74], 0.3, 0.2),
  bark: () => std([0.12, 0.09, 0.07], 0.9), bamboo_cane: () => std([0.33, 0.42, 0.12], 0.4),
  leaf_camphor: () => leaf('broad', [0.18, 0.31, 0.085]), leaf_ginkgo: () => leaf('fan', [0.95, 0.62, 0.06]),
  leaf_maple: () => leaf('broad', [0.78, 0.2, 0.05]), leaf_blossom: () => leaf('broad', [0.92, 0.45, 0.56]),
  leaf_willow: () => leaf('narrow', [0.36, 0.47, 0.12]), leaf_pine: () => leaf('needle', [0.085, 0.2, 0.075]),
  leaf_bamboo: () => leaf('narrow', [0.22, 0.39, 0.08]), leaf_shrub: () => leaf('broad', [0.15, 0.27, 0.065]),
};
const matCache = {};
function materialFor(name) {
  if (!(name in matCache)) {
    matCache[name] = (MAT[name] || (() => std(0x888888, 0.7)))();
    matCache[name].side = THREE.DoubleSide;     // procedural meshes are not consistently wound
  }
  matCache[name].name = name;
  return matCache[name];
}

// ---------------------------------------------------------------------------
// ground, far landscape (procedural), mountains silhouettes
// ---------------------------------------------------------------------------
const farTex = canvasTex(1024, 1024, (g, w, h) => {
  const r = rand(5), pal = ['#1f3512', '#24391a', '#33391a', '#213714', '#2b3a18', '#1c3010', '#3a3c1e'];
  for (let y = 0; y < h; y += 16) for (let x = 0; x < w; x += 46) { g.fillStyle = pal[Math.floor(r() * pal.length)]; g.fillRect(x, y, 46, 16); }
  g.strokeStyle = 'rgba(10,20,6,.6)'; g.lineWidth = 1;
  for (let y = 0; y < h; y += 16) { g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
});
farTex.repeat.set(120, 120);
farTex.colorSpace = THREE.SRGBColorSpace;
const ground = new THREE.Mesh(new THREE.RingGeometry(60, 60000, 96, 8).rotateX(-Math.PI / 2),   // hole = Sky Well shaft
  new THREE.MeshStandardMaterial({ map: farTex, roughness: 1 }));
ground.position.y = -0.7;
ground.receiveShadow = true;
scene.add(ground);
{ // ink-wash ridges on the horizon
  const ridges = new THREE.Group();
  [[9000, 230, 0x1a2420], [12500, 420, 0x1e2a2c], [17000, 760, 0x24323a]].forEach(([R, H, c], k) => {
    const n = 360, pos = [], idx = [];
    for (let i = 0; i <= n; i++) {
      const a = i / n * Math.PI * 2;
      const h = H * (0.25 + 0.45 * Math.abs(Math.sin(a * (5 + k) + k)) + 0.3 * Math.abs(Math.sin(a * (17 + 3 * k) + 1.3 * k)) * Math.abs(Math.sin(a * 41 + k)));
      pos.push(Math.cos(a) * R, -1, Math.sin(a) * R, Math.cos(a) * R, h, Math.sin(a) * R);
      if (i < n) { const b = i * 2; idx.push(b, b + 1, b + 2, b + 1, b + 3, b + 2); }
    }
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); geo.setIndex(idx); geo.computeVertexNormals();
    ridges.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: c, roughness: 1, side: THREE.DoubleSide })));
  });
  scene.add(ridges);
}

// ---------------------------------------------------------------------------
// night lights (airfield)
// ---------------------------------------------------------------------------
const lightGroup = new THREE.Group();
lightGroup.visible = false;
scene.add(lightGroup);
const spriteTex = canvasTex(64, 64, (g, w, h) => {
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.25, 'rgba(255,255,255,.6)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
}, false);
const LIGHT_COL = { rwy_edge: 0xffe9c0, rwy_centre: 0xfff2d8, rwy_green: 0x33ff77, rwy_red: 0xff2a1a, approach: 0xffe2b0, taxi_blue: 0x2a5dff, taxi_green: 0x2aff66 };
fetch('assets/lights.json').then(r => r.json()).then(L => {
  for (const [k, pts] of Object.entries(L)) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts.flat(), 3));
    const m = new THREE.PointsMaterial({ color: LIGHT_COL[k] || 0xffffff, size: k.startsWith('taxi') ? 7 : 10, map: spriteTex,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true });
    m.color.multiplyScalar(4);
    lightGroup.add(new THREE.Points(g, m));
  }
});

// ---------------------------------------------------------------------------
// model
// ---------------------------------------------------------------------------
const bar = document.querySelector('#bar i'), lt = document.querySelector('#lt');
const gl = new GLTFLoader();
gl.setMeshoptDecoder(MeshoptDecoder);
gl.load('assets/qingyun.glb', async gltf => {
  const root = gltf.scene;
  const lib = {};
  root.traverse(o => {
    if (/^T\d\d_/.test(o.name) && !lib[o.name]) lib[o.name] = o;
    if (o.isMesh) {
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      const nm = mats.map(m => materialFor(m.name));
      o.material = Array.isArray(o.material) ? nm : nm[0];
      const n = (o.name + (o.parent ? o.parent.name : ''));
      const noShadow = /Water|Lake|Rills|Cascade|Curtain|Waterfall|Splash|Grass|Apron|Marking|Runway|Taxiway|Glass|Balustrade/.test(n);
      o.castShadow = !noShadow;
      o.receiveShadow = true;
      if (/Apron_Concrete/.test(n)) {      // planar UVs for the apron mask
        const p = o.geometry.attributes.position, uv = new Float32Array(p.count * 2), v = new THREE.Vector3();
        for (let i = 0; i < p.count; i++) {
          v.fromBufferAttribute(p, i).applyMatrix4(o.matrixWorld);
          uv[2 * i] = v.x / 2020 + 0.5; uv[2 * i + 1] = -v.z / 2020 + 0.5;
        }
        o.geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
      }
    }
  });
  scene.add(root);
  root.updateMatrixWorld(true);
  // instanced vegetation
  const trees = await (await fetch('assets/trees.json')).json();
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), col = new THREE.Color();
  for (const [name, list] of Object.entries(trees)) {
    const src = lib[name];
    if (!src || !list.length) continue;
    src.visible = false;
    src.traverse(o => {
      if (!o.isMesh) return;
      const im = new THREE.InstancedMesh(o.geometry, o.material, list.length);
      const r = rand(name.length * 97);
      list.forEach(([x, y, z, ry, s], i) => {
        q.setFromAxisAngle(up, ry);
        m4.compose(new THREE.Vector3(x, y, z), q, new THREE.Vector3(s, s, s));
        im.setMatrixAt(i, m4);
        const k = 0.8 + r() * 0.4;
        im.setColorAt(i, col.setRGB(k, k, k));
      });
      im.castShadow = true; im.receiveShadow = true;
      im.frustumCulled = false;
      scene.add(im);
    });
  }
  document.getElementById('load').style.opacity = 0;
  setTimeout(() => document.getElementById('load').remove(), 900);
  window.__ready = true;
}, e => { if (e.total) bar.style.width = (100 * e.loaded / e.total).toFixed(1) + '%'; lt.textContent = (e.loaded / 1e6).toFixed(1) + ' MB'; },
err => { lt.textContent = 'failed to load model: ' + err; });

// ---------------------------------------------------------------------------
// time of day
// ---------------------------------------------------------------------------
const TIMES = {
  golden: { az: 256, el: 7.5, sun: [1.0, 0.62, 0.36], si: 3.6, hemi: 0.55, tur: 6, ray: 2.2, mie: 0.006, exp: 0.9, fog: 0xc9c2bc, fd: 0.000075, night: 0 },
  day: { az: 215, el: 42, sun: [1.0, 0.95, 0.88], si: 3.2, hemi: 0.8, tur: 3, ray: 1.4, mie: 0.004, exp: 0.85, fog: 0xbfcfdc, fd: 0.00006, night: 0 },
  night: { az: 252, el: -4.0, sun: [0.6, 0.6, 0.9], si: 0.0, hemi: 0.12, tur: 4, ray: 3, mie: 0.005, exp: 1.6, fog: 0x1c2333, fd: 0.00012, night: 1 },
};
function setTime(key) {
  const t = TIMES[key];
  const az = t.az * D2R, el = t.el * D2R;
  const dir = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), -Math.cos(az) * Math.cos(el));
  for (const s of [sky, envSky]) {
    const u = s.material.uniforms;
    u.sunPosition.value.copy(dir);
    u.turbidity.value = t.tur; u.rayleigh.value = t.ray; u.mieCoefficient.value = t.mie; u.mieDirectionalG.value = 0.86;
  }
  sun.position.copy(dir).multiplyScalar(4000);
  sun.target.position.set(0, 0, 0);
  sun.color.setRGB(...t.sun);
  sun.intensity = t.si;
  sun.visible = t.si > 0;
  hemi.intensity = t.hemi;
  hemi.color.set(key === 'night' ? 0x4a5d9a : 0xbfd4ff);
  renderer.toneMappingExposure = t.exp;
  scene.fog.color.set(t.fog); scene.fog.density = t.fd;
  night.u.value = t.night;
  lightGroup.visible = t.night > 0;
  bloom.strength = t.night ? 0.9 : 0.25;
  bloom.threshold = t.night ? 0.6 : 0.95;
  if (envRT) envRT.dispose();
  envRT = pmrem.fromScene(envScene, 0.02);
  scene.environment = envRT.texture;
  document.querySelectorAll('#time button').forEach(b => b.classList.toggle('on', b.dataset.t === key));
}

// ---------------------------------------------------------------------------
// camera views (same shots as the 4K renders) + system notes
// ---------------------------------------------------------------------------
const VIEWS = [
  { n: 'Aerial', p: [-560, -1780, 400], t: [40, 260, 0], lens: 30, h: 'Shanshui masterplan',
    d: 'Lake → causeway → gorge → Lotus hub: one axis. The landside “mountains” are terraced wetland roofs over the car parks; five leaf-shaped piers carry 75 contact stands, the farthest ~700 m from central security.' },
  { n: 'Sky Well', p: [-15.75, -58.6, 13.7], t: [0, 0, 1.5], lens: 13, h: 'Chilled vortex · 58 m',
    d: 'All rain on the 200,000 m² inverted-lotus roof funnels to the 32 m oculus and falls 58 m to the maglev station. Fed with 13 °C water (below the hall’s dew point) the curtain works as a giant air-washer: it cools and dehumidifies instead of adding humidity.' },
  { n: 'Gorge', p: [0, -610, 6.5], t: [0, -282, 15], lens: 27, h: 'Water-curtain gateway',
    d: 'Roads arrive through a terraced gorge. A river runs down its centre from the hub to the lake (stormwater conveyance). The roof eave sheds a water curtain with openings at the doors.' },
  { n: 'Oculus', p: [-110, -165, 150], t: [0, 0, 12], lens: 27, h: 'Log-polar spiral gridshell',
    d: '19,296 nodes, two conformal spiral families (96 → 192): every panel is a near-square diamond that grows with radius. 74 % semi-transparent BIPV, 26 % clear “veins”.' },
  { n: 'Pier', p: [-128, 338, 17], t: [-30, 430, 8], lens: 26, h: 'Leaf piers',
    d: 'PV roofs with herring-bone skylight veins; pre-conditioned air and 400 Hz power at every stand so APUs stay off; electric taxi tugs to the runway.' },
  { n: 'Night', p: [1750, 1450, 640], t: [-40, -160, 0], lens: 30, h: 'Blue hour', time: 'night',
    d: 'Runway pairs 780 m apart (segregated parallel operations) and 3.1 km between pairs (independent).' },
  { n: 'Plan', p: [0, -281, 5600], t: [0, -280, 0], lens: 24, h: 'Master plan',
    d: 'Four 3,800 m runways, horseshoe taxiway, radial apron, 1.33 km² sponge lake with 85 floating-PV islands, 1.9 km² of solar fields outside the runway strips.' },
];
const info = document.getElementById('info');
let tween = null;
function goView(v) {
  const p = B(...v.p), t = B(...v.t);
  const fov = 2 * Math.atan(18 / v.lens * 9 / 16) / D2R;
  tween = { p0: camera.position.clone(), t0: controls.target.clone(), f0: camera.fov, p1: p, t1: t, f1: fov, k: 0 };
  info.style.display = 'block';
  info.querySelector('h3').textContent = v.h;
  info.querySelector('p').textContent = v.d;
  if (v.time) setTime(v.time);
}
const vb = document.getElementById('views');
VIEWS.forEach((v, i) => {
  const b = document.createElement('button'); b.textContent = v.n;
  b.onclick = () => { vb.querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on'); goView(v); };
  vb.appendChild(b);
  if (i === 0) b.classList.add('on');
});
document.querySelectorAll('#time button').forEach(b => b.onclick = () => setTime(b.dataset.t));

// initial
setTime('golden');
{ const v = VIEWS[0]; camera.position.copy(B(...v.p)); controls.target.copy(B(...v.t)); camera.fov = 2 * Math.atan(18 / v.lens * 9 / 16) / D2R; camera.updateProjectionMatrix(); }
const params = Q;
if (params.get('view')) { const v = VIEWS.find(x => x.n.toLowerCase() === params.get('view')); if (v) { goView(v); tween.k = 1; } }
if (params.get('time')) setTime(params.get('time'));

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight); composer.setSize(innerWidth, innerHeight);
});

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1);
  if (tween) {
    tween.k = Math.min(1, tween.k + dt / 2.2);
    const e = tween.k < 0.5 ? 4 * tween.k ** 3 : 1 - (-2 * tween.k + 2) ** 3 / 2;
    camera.position.lerpVectors(tween.p0, tween.p1, e);
    controls.target.lerpVectors(tween.t0, tween.t1, e);
    camera.fov = tween.f0 + (tween.f1 - tween.f0) * e; camera.updateProjectionMatrix();
    if (tween.k >= 1) tween = null;
  }
  for (const f of animated) f(dt);
  controls.update();
  // keep the shadow frustum around what the camera looks at
  sun.target.position.copy(controls.target);
  sun.position.copy(sky.material.uniforms.sunPosition.value).multiplyScalar(4000).add(controls.target);
  if (LITE) renderer.render(scene, camera); else composer.render();
  if (Q.has('still') && window.__ready && ++stillFrames > 3) { renderer.setAnimationLoop(null); window.__still = true; }
});
let stillFrames = 0;
