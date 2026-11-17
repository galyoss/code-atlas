import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { edgePoint, visualSeed, type CosmicGraph } from '../graph/cinematic';

export interface UniverseRenderer {
  dispose: () => void;
  setMotion: (enabled: boolean) => void;
  reset: () => void;
  zoom: (factor: number) => void;
  select: (index: number | null) => void;
}

const pointVertex = `
  attribute vec3 tint;
  attribute float size;
  attribute float index;
  uniform float time;
  uniform float scale;
  uniform float reveal;
  uniform float selected;
  varying vec3 color;
  varying float focus;
  void main() {
    focus = abs(index-selected) < .1 ? 1. : 0.;
    color = tint;
    vec4 mv = modelViewMatrix * vec4(position * reveal, 1.);
    gl_Position = projectionMatrix * mv;
    float breath = 1. + .10 * sin(time*1.3 + index*1.7);
    gl_PointSize = clamp(size * scale / -mv.z * breath * (1.+focus*.75), 1., 72.);
  }
`;
const pointFragment = `
  varying vec3 color;
  varying float focus;
  void main() {
    float d = length(gl_PointCoord-.5)*2.;
    if (d>1.) discard;
    float core = exp(-d*d*24.);
    float halo = pow(1.-d,2.)*.38;
    gl_FragColor = vec4(mix(color, vec3(1.), core*.24 + focus*.2) * (.85 + core*.8), core+halo);
  }
`;
const lineVertex = `
  attribute vec3 tint;
  attribute float travel;
  attribute float seed;
  attribute float power;
  uniform float reveal;
  varying vec3 color;
  varying float vTravel;
  varying float vSeed;
  varying float vPower;
  void main() {
    color=tint; vTravel=travel; vSeed=seed; vPower=power;
    gl_Position=projectionMatrix*modelViewMatrix*vec4(position*reveal,1.);
  }
`;
const lineFragment = `
  uniform float time;
  uniform float energy;
  varying vec3 color;
  varying float vTravel;
  varying float vSeed;
  varying float vPower;
  void main() {
    float phase=fract(vTravel-time*(.13+vSeed*.1)+vSeed);
    float pulse=exp(-phase*phase*1800.)+exp(-(phase-1.)*(phase-1.)*1800.);
    float trail=pow(max(0.,1.-phase*9.),3.)*.3;
    float alpha=abs(vPower)*.055 + (pulse+trail)*max(vPower,0.)*.38*energy;
    gl_FragColor=vec4(color*(.55+(pulse+trail)*1.1*energy*step(0.,vPower)),alpha);
  }
`;

export function createUniverse(
  host: HTMLDivElement,
  graph: CosmicGraph,
  callbacks: { select: (index: number | null) => void; hover: (index: number | null, x: number, y: number) => void; error: (message: string) => void },
  motion: boolean,
): UniverseRenderer {
  const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setClearColor(0x03070e);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = .9;
  renderer.domElement.tabIndex = 0;
  renderer.domElement.setAttribute('aria-label', 'Interactive 3D code universe. Drag to orbit, scroll to zoom. Arrow keys orbit; plus and minus zoom.');
  host.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const world = new THREE.Group();
  scene.add(world);
  const camera = new THREE.PerspectiveCamera(48, 1, .5, 8000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = .075;
  controls.rotateSpeed = .55;
  controls.zoomSpeed = .7;
  controls.autoRotateSpeed = .24;
  controls.minDistance = 100;
  controls.maxDistance = 3600;
  controls.enablePan = true;
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), .45, .45, .65);
  composer.addPass(bloom);
  const output = new OutputPass();
  composer.addPass(output);
  let enabled = motion, destroyed = false, failed = false, frame = 0, clock = 0, last = performance.now(), dirty = true, userInteracted = false, selected: number | null = null;
  const uniforms = { time: { value: 0 }, reveal: { value: motion ? .55 : 1 }, scale: { value: 1 }, selected: { value: -1 } };
  const positions: number[] = [], colors: number[] = [], sizes: number[] = [];
  graph.nodes.forEach((node) => { positions.push(...node.position); colors.push(...node.color); sizes.push(node.size); });
  const pointsGeometry = new THREE.BufferGeometry();
  pointsGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  pointsGeometry.setAttribute('tint', new THREE.Float32BufferAttribute(colors, 3));
  pointsGeometry.setAttribute('size', new THREE.Float32BufferAttribute(sizes, 1));
  pointsGeometry.setAttribute('index', new THREE.Float32BufferAttribute(graph.nodes.map((_, i) => i), 1));
  const pointsMaterial = new THREE.ShaderMaterial({ uniforms, vertexShader: pointVertex, fragmentShader: pointFragment, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const points = new THREE.Points(pointsGeometry, pointsMaterial);
  world.add(points);

  const linePositions: number[] = [], lineColors: number[] = [], travels: number[] = [], seeds: number[] = [], powers: number[] = [];
  for (const edge of graph.edges) {
    const a = graph.nodes[graph.index.get(edge.from)!], b = graph.nodes[graph.index.get(edge.to)!];
    const seed = visualSeed(edge.id);
    const structural = edge.kind === 'definition' || edge.kind === 'context';
    const color = structural ? [.24, .36, .54] : b.color;
    const power = structural ? -.12 : edge.aggregated ? 1.5 : edge.kind === 'unresolved' ? .27 : .72;
    const distance = Math.hypot(...a.position.map((v, i) => v - b.position[i]));
    const steps = distance > 180 ? 18 : 8;
    for (let i = 0; i < steps; i++) for (const t of [i / steps, (i + 1) / steps]) {
      linePositions.push(...edgePoint(a.position, b.position, t, seed));
      lineColors.push(...color); travels.push(t); seeds.push(seed); powers.push(power);
    }
  }
  const lineGeometry = new THREE.BufferGeometry();
  lineGeometry.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
  lineGeometry.setAttribute('tint', new THREE.Float32BufferAttribute(lineColors, 3));
  lineGeometry.setAttribute('travel', new THREE.Float32BufferAttribute(travels, 1));
  lineGeometry.setAttribute('seed', new THREE.Float32BufferAttribute(seeds, 1));
  lineGeometry.setAttribute('power', new THREE.Float32BufferAttribute(powers, 1));
  const lineMaterial = new THREE.ShaderMaterial({ uniforms: { time: uniforms.time, reveal: uniforms.reveal, energy: { value: 1 } }, vertexShader: lineVertex, fragmentShader: lineFragment, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  world.add(new THREE.LineSegments(lineGeometry, lineMaterial));

  // Atmosphere: unconnected star dust and orbital guides, excluded from code counts.
  const starPositions: number[] = [], starColors: number[] = [];
  for (let i = 0; i < 1000; i++) {
    const angle = visualSeed(`star:${i}`) * Math.PI * 2;
    const z = visualSeed(`latitude:${i}`) * 2 - 1;
    const r = 700 + visualSeed(`radius:${i}`) * 1400;
    starPositions.push(Math.cos(angle) * Math.sqrt(1 - z * z) * r, z * r, Math.sin(angle) * Math.sqrt(1 - z * z) * r);
    starColors.push(.27, .4, .52);
  }
  const starsGeometry = new THREE.BufferGeometry();
  starsGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starPositions, 3));
  starsGeometry.setAttribute('color', new THREE.Float32BufferAttribute(starColors, 3));
  const starMaterial = new THREE.PointsMaterial({ size: 1.4, vertexColors: true, transparent: true, opacity: .65, depthWrite: false, sizeAttenuation: true });
  scene.add(new THREE.Points(starsGeometry, starMaterial));
  const rings = new THREE.Group();
  for (let i = 0; i < 3; i++) {
    const vertices = Array.from({ length: 257 }, (_, j) => {
      const angle = j / 256 * Math.PI * 2;
      const r = graph.radius * (.89 + i * .17);
      return new THREE.Vector3(Math.cos(angle) * r, -145 - i * 12, Math.sin(angle) * r * .76);
    });
    const geometry = new THREE.BufferGeometry().setFromPoints(vertices);
    const material = new THREE.LineBasicMaterial({ color: 0x235569, transparent: true, opacity: .2 - i * .045 });
    rings.add(new THREE.Line(geometry, material));
  }
  scene.add(rings);

  const haloCanvas = document.createElement('canvas'); haloCanvas.width = 128; haloCanvas.height = 128;
  const context = haloCanvas.getContext('2d')!;
  const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, 'rgba(90,190,255,.2)'); gradient.addColorStop(.25, 'rgba(45,110,220,.08)'); gradient.addColorStop(1, 'rgba(0,0,0,0)');
  context.fillStyle = gradient; context.fillRect(0, 0, 128, 128);
  const hazeTexture = new THREE.CanvasTexture(haloCanvas);
  const hazeMaterial = new THREE.SpriteMaterial({ map: hazeTexture, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: .45 });
  for (const cluster of graph.clusters.slice(0, 9)) {
    const haze = new THREE.Sprite(hazeMaterial); haze.position.set(...cluster.position);
    haze.scale.setScalar(cluster.radius * 5); world.add(haze);
  }
  const reticle = new THREE.Mesh(new THREE.RingGeometry(8, 8.3, 64), new THREE.MeshBasicMaterial({ color: 0xb7fff1, side: THREE.DoubleSide, transparent: true, opacity: .9, depthTest: false }));
  reticle.visible = false; world.add(reticle);

  let width = 1, height = 1;
  function frameCamera() {
    const portrait = width < height;
    const distance = graph.radius * (portrait ? 3.75 : 2.15);
    camera.position.set(distance * .15, distance * .48, distance * .86);
    controls.target.set(0, -12, 0); controls.update(); controls.saveState();
    dirty = true;
  }
  function resize() {
    width = Math.max(1, host.clientWidth); height = Math.max(1, host.clientHeight);
    camera.aspect = width / height; camera.updateProjectionMatrix();
    renderer.setSize(width, height); composer.setSize(width, height);
    uniforms.scale.value = height * renderer.getPixelRatio() * .85;
    if (!userInteracted) frameCamera();
    dirty = true;
  }
  const observer = new ResizeObserver(resize); observer.observe(host); resize();
  const markDirty = () => { dirty = true; };
  const onStart = () => { userInteracted = true; host.dataset.interacted = 'true'; };
  controls.addEventListener('change', markDirty); controls.addEventListener('start', onStart);
  const projected = new THREE.Vector3();
  function hit(event: PointerEvent) {
    const bounds = renderer.domElement.getBoundingClientRect();
    const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
    let best = 12 * 12, winner: number | null = null;
    graph.nodes.forEach((node, i) => {
      projected.set(...node.position).multiplyScalar(uniforms.reveal.value).project(camera);
      if (projected.z > 1 || projected.z < -1) return;
      const distance = ((projected.x + 1) * width / 2 - x) ** 2 + ((1 - projected.y) * height / 2 - y) ** 2;
      const bias = node.node.canonical ? .7 : 1;
      if (distance * bias < best) { best = distance * bias; winner = i; }
    });
    return { index: winner, x, y };
  }
  let startX = 0, startY = 0, hoverTime = 0, dragging = false;
  function pointerDown(event: PointerEvent) { startX = event.clientX; startY = event.clientY; dragging = true; callbacks.hover(null, 0, 0); }
  function pointerUp(event: PointerEvent) {
    dragging = false;
    if (Math.hypot(event.clientX - startX, event.clientY - startY) > 5) return;
    callbacks.select(hit(event).index);
  }
  function pointerMove(event: PointerEvent) {
    if (dragging || performance.now() - hoverTime < 90) return;
    hoverTime = performance.now(); const result = hit(event);
    callbacks.hover(result.index, result.x, result.y);
    renderer.domElement.style.cursor = result.index === null ? 'grab' : 'pointer';
  }
  function pointerLeave() { dragging = false; callbacks.hover(null, 0, 0); }
  function zoom(factor: number) { camera.position.sub(controls.target).multiplyScalar(factor).add(controls.target); controls.update(); dirty = true; userInteracted = true; }
  function keyDown(event: KeyboardEvent) {
    if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(.85); }
    else if (event.key === '-') { event.preventDefault(); zoom(1.15); }
    else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
      event.preventDefault(); userInteracted = true;
      const offset = camera.position.clone().sub(controls.target);
      const spherical = new THREE.Spherical().setFromVector3(offset);
      if (event.key === 'ArrowLeft') spherical.theta -= .1;
      if (event.key === 'ArrowRight') spherical.theta += .1;
      if (event.key === 'ArrowUp') spherical.phi -= .1;
      if (event.key === 'ArrowDown') spherical.phi += .1;
      spherical.makeSafe(); camera.position.setFromSpherical(spherical).add(controls.target); controls.update(); dirty = true;
    }
  }
  function contextLost(event: Event) { event.preventDefault(); failed = true; callbacks.error('The 3D connection was interrupted. Return to the graph, then reopen the universe.'); }
  const canvas = renderer.domElement;
  canvas.addEventListener('pointerdown', pointerDown);
  canvas.addEventListener('pointerup', pointerUp);
  canvas.addEventListener('pointermove', pointerMove);
  canvas.addEventListener('pointerleave', pointerLeave);
  canvas.addEventListener('pointercancel', pointerLeave);
  canvas.addEventListener('keydown', keyDown);
  canvas.addEventListener('webglcontextlost', contextLost);
  let diagnosticAt = 0;
  function animate(now: number) {
    if (destroyed) return;
    frame = requestAnimationFrame(animate);
    const delta = Math.min(.05, (now - last) / 1000); last = now;
    if (document.hidden || failed) return;
    controls.autoRotate = enabled;
    controls.update(delta);
    if (enabled) { clock += delta; dirty = true; }
    if (!dirty) return;
    uniforms.time.value = clock;
    if (enabled) uniforms.reveal.value = .55 + .45 * (1 - Math.pow(1 - Math.min(1, clock / 2.3), 3));
    if (selected !== null) { reticle.position.set(...graph.nodes[selected].position).multiplyScalar(uniforms.reveal.value); reticle.quaternion.copy(camera.quaternion); }
    try { composer.render(); } catch {
      failed = true; callbacks.error('The 3D renderer was interrupted. Return to the graph and reopen the universe.');
    }
    dirty = false;
    if (now - diagnosticAt > 250) {
      host.dataset.sceneTime = clock.toFixed(4);
      host.dataset.camera = camera.position.toArray().map((v) => v.toFixed(3)).join(',');
      host.dataset.ready = 'true'; diagnosticAt = now;
    }
  }
  frame = requestAnimationFrame(animate);
  return {
    setMotion(value) {
      enabled = value; controls.autoRotate = value;
      if (!value) {
        // Flush damping without moving the camera: Pause freezes its current pose.
        const position = camera.position.clone(), target = controls.target.clone();
        controls.enableDamping = false; controls.update();
        camera.position.copy(position); controls.target.copy(target); controls.update();
        controls.enableDamping = true;
      }
      dirty = true;
    },
    reset() { userInteracted = false; frameCamera(); },
    zoom,
    select(index) { selected = index; uniforms.selected.value = index ?? -1; reticle.visible = index !== null; dirty = true; },
    dispose() {
      destroyed = true; cancelAnimationFrame(frame); observer.disconnect();
      controls.removeEventListener('change', markDirty); controls.removeEventListener('start', onStart); controls.dispose();
      canvas.removeEventListener('pointerdown', pointerDown); canvas.removeEventListener('pointerup', pointerUp); canvas.removeEventListener('pointermove', pointerMove); canvas.removeEventListener('pointerleave', pointerLeave); canvas.removeEventListener('pointercancel', pointerLeave); canvas.removeEventListener('keydown', keyDown); canvas.removeEventListener('webglcontextlost', contextLost);
      const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>();
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) geometries.add(mesh.geometry);
        if (mesh.material) (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).forEach((material) => materials.add(material));
      });
      geometries.forEach((geometry) => geometry.dispose()); materials.forEach((material) => material.dispose()); hazeTexture.dispose();
      bloom.dispose(); output.dispose(); composer.dispose(); renderer.dispose(); renderer.forceContextLoss(); canvas.remove();
    },
  };
}
