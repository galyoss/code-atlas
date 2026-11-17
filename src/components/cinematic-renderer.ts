import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { edgePoint, visualSeed, type CosmicGraph, type Vec3 } from '../graph/cinematic';
import { createSemanticRegions } from './cinematic-regions';
import { retargetBuffer, transitionProgress, type CosmicPresentation } from '../graph/cinematic-controls';

export interface UniverseRenderer {
  dispose: () => void;
  setMotion: (enabled: boolean) => void;
  setPresentation: (presentation: CosmicPresentation, animate: boolean) => void;
  reset: () => void;
  zoom: (factor: number) => void;
  select: (index: number | null) => void;
}

const pointVertex = `
  attribute vec3 tint;
  attribute vec3 targetPosition;
  attribute float visible;
  attribute float emphasis;
  varying float strength;
  uniform float morph;
  varying float visibility;
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
    visibility = visible;
    strength = emphasis;
    vec4 mv = modelViewMatrix * vec4(mix(position,targetPosition,morph) * reveal, 1.);
    gl_Position = projectionMatrix * mv;
    float breath = 1. + .10 * sin(time*1.3 + index*1.7);
    gl_PointSize = clamp(size * scale / -mv.z * breath * (1.+focus*.75), 1., 72.);
  }
`;
const pointFragment = `
  varying float visibility;
  varying float strength;
  varying vec3 color;
  varying float focus;
  void main() {
    float d = length(gl_PointCoord-.5)*2.;
    if (d>1. || visibility < .5) discard;
    float core = exp(-d*d*24.);
    float halo = pow(1.-d,2.)*.38;
    gl_FragColor = vec4(mix(color, vec3(1.), core*.06 + focus*.12) * (.85 + core*.55), (core+halo)*strength);
  }
`;
const lineVertex = `
  attribute vec3 targetPosition;
  attribute float visible;
  attribute float emphasis;
  varying float strength;
  uniform float morph;
  varying float visibility;
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
    visibility=visible; strength=emphasis;
    gl_Position=projectionMatrix*modelViewMatrix*vec4(mix(position,targetPosition,morph)*reveal,1.);
  }
`;
const lineFragment = `
  varying float visibility;
  uniform float time;
  uniform float energy;
  varying float strength;
  varying vec3 color;
  varying float vTravel;
  varying float vSeed;
  varying float vPower;
  void main() {
    if(visibility < .5) discard;
    float phase=fract(vTravel-time*(.13+vSeed*.1)+vSeed);
    float pulse=exp(-phase*phase*1800.)+exp(-(phase-1.)*(phase-1.)*1800.);
    float trail=pow(max(0.,1.-phase*9.),3.)*.3;
    float alpha=(abs(vPower)*.043 + (pulse+trail)*max(vPower,0.)*.25*energy)*strength;
    if (strength>1.) alpha += .34*step(0.,vPower);
    gl_FragColor=vec4(color*(.65+(pulse+trail)*.7*energy*step(0.,vPower)),alpha);
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
  const morph = { value: 1 };
  let transitionStart = 0, transitioning = false;
  let targetPositions: CosmicPresentation['positions'] | null = null;
  let visibleNodes = new Set(graph.nodes.map((_, i) => i));
  const uniforms = { morph, time: { value: 0 }, reveal: { value: motion ? .55 : 1 }, scale: { value: 1 }, selected: { value: -1 } };
  const positions: number[] = [], colors: number[] = [], sizes: number[] = [];
  graph.nodes.forEach((node) => { positions.push(...node.position); colors.push(...node.color); sizes.push(node.size); });
  const pointsGeometry = new THREE.BufferGeometry();
  const pointSource = new THREE.Float32BufferAttribute(positions, 3);
  const pointTarget = new THREE.Float32BufferAttribute(positions, 3);
  const pointVisible = new THREE.Float32BufferAttribute(graph.nodes.map(() => 1), 1);
  pointsGeometry.setAttribute('position', pointSource);
  pointsGeometry.setAttribute('targetPosition', pointTarget);
  const pointEmphasis = new THREE.Float32BufferAttribute(graph.nodes.map(() => 1), 1);
  pointsGeometry.setAttribute('emphasis', pointEmphasis);
  pointsGeometry.setAttribute('visible', pointVisible);
  pointsGeometry.setAttribute('tint', new THREE.Float32BufferAttribute(colors, 3));
  pointsGeometry.setAttribute('size', new THREE.Float32BufferAttribute(sizes, 1));
  pointsGeometry.setAttribute('index', new THREE.Float32BufferAttribute(graph.nodes.map((_, i) => i), 1));
  const pointsMaterial = new THREE.ShaderMaterial({ uniforms, vertexShader: pointVertex, fragmentShader: pointFragment, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const points = new THREE.Points(pointsGeometry, pointsMaterial);
  points.frustumCulled = false;
  world.add(points);

  const linePositions: number[] = [], lineColors: number[] = [], travels: number[] = [], seeds: number[] = [], powers: number[] = [];
  const edgeRanges: { start: number; steps: number }[] = [];
  for (const edge of graph.edges) {
    const a = graph.nodes[graph.index.get(edge.from)!], b = graph.nodes[graph.index.get(edge.to)!];
    const seed = visualSeed(edge.id);
    const structural = edge.kind === 'definition' || edge.kind === 'context';
    const color = structural ? [.24, .36, .54] : b.color;
    const power = structural ? -.12 : edge.aggregated ? 1.5 : edge.kind === 'unresolved' ? .27 : .72;
    const distance = Math.hypot(...a.position.map((v, i) => v - b.position[i]));
    const steps = distance > 180 ? 18 : 8;
    edgeRanges.push({ start: travels.length, steps });
    for (let i = 0; i < steps; i++) for (const t of [i / steps, (i + 1) / steps]) {
      linePositions.push(...edgePoint(a.position, b.position, t, seed));
      lineColors.push(...color); travels.push(t); seeds.push(seed); powers.push(power);
    }
  }
  const lineGeometry = new THREE.BufferGeometry();
  const lineSource = new THREE.Float32BufferAttribute(linePositions, 3);
  const lineTarget = new THREE.Float32BufferAttribute(linePositions, 3);
  const lineVisible = new THREE.Float32BufferAttribute(travels.map(() => 1), 1);
  lineGeometry.setAttribute('position', lineSource);
  lineGeometry.setAttribute('targetPosition', lineTarget);
  const lineEmphasis = new THREE.Float32BufferAttribute(travels.map(() => 1), 1);
  lineGeometry.setAttribute('emphasis', lineEmphasis);
  lineGeometry.setAttribute('visible', lineVisible);
  lineGeometry.setAttribute('tint', new THREE.Float32BufferAttribute(lineColors, 3));
  lineGeometry.setAttribute('travel', new THREE.Float32BufferAttribute(travels, 1));
  lineGeometry.setAttribute('seed', new THREE.Float32BufferAttribute(seeds, 1));
  lineGeometry.setAttribute('power', new THREE.Float32BufferAttribute(powers, 1));
  const lineMaterial = new THREE.ShaderMaterial({ uniforms: { morph, time: uniforms.time, reveal: uniforms.reveal, energy: { value: 1 } }, vertexShader: lineVertex, fragmentShader: lineFragment, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const lines = new THREE.LineSegments(lineGeometry, lineMaterial);
  lines.frustumCulled = false;
  world.add(lines);
  const regions = createSemanticRegions(host, world, graph);
  // Directed chevrons remain visible when ambient energy is paused.
  const arrowGeometry = new THREE.BufferGeometry();
  const arrowPositions = new THREE.Float32BufferAttribute(new Float32Array(graph.edges.length * 12), 3);
  const arrowColors = new THREE.Float32BufferAttribute(new Float32Array(graph.edges.length * 12), 3);
  arrowGeometry.setAttribute('position', arrowPositions); arrowGeometry.setAttribute('color', arrowColors);
  arrowGeometry.setDrawRange(0, 0);
  const arrows = new THREE.LineSegments(arrowGeometry, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: .95, depthTest: false, depthWrite: false, blending: THREE.AdditiveBlending }));
  arrows.frustumCulled = false; world.add(arrows);
  let directedEdges: number[] = [];
  const tangent = new THREE.Vector3(), side = new THREE.Vector3(), eye = new THREE.Vector3();
  const arrowTip = new THREE.Vector3(), arrowStart = new THREE.Vector3(), wing = new THREE.Vector3();
  function linePoint(vertex: number, target: THREE.Vector3) {
    const offset = vertex * 3;
    target.set(lineSource.array[offset], lineSource.array[offset + 1], lineSource.array[offset + 2]);
    for (let axis = 0; axis < 3; axis++) target.setComponent(axis,
      target.getComponent(axis) + (lineTarget.array[offset + axis] - target.getComponent(axis)) * morph.value);
    return target;
  }
  function updateArrows() {
    let vertex = 0;
    for (const index of directedEdges) {
      const edge = graph.edges[index], range = edgeRanges[index];
      const segment = range.start + Math.floor(range.steps * .68) * 2;
      // Use the drawn edge buffers, including an interrupted morph, not a re-created curve.
      linePoint(segment, arrowStart); linePoint(segment + 1, arrowTip);
      tangent.copy(arrowTip).sub(arrowStart).normalize();
      eye.copy(camera.position).sub(arrowTip).normalize(); side.crossVectors(tangent, eye).normalize();
      const size = Math.min(9, Math.max(3, camera.position.distanceTo(arrowTip) * .006));
      const color = graph.nodes[graph.index.get(edge.to)!].color;
      for (const direction of [-1, 1]) {
        wing.copy(arrowTip).addScaledVector(tangent, -size).addScaledVector(side, direction * size * .45);
        for (const point of [wing, arrowTip]) {
          arrowPositions.setXYZ(vertex, point.x * uniforms.reveal.value, point.y * uniforms.reveal.value, point.z * uniforms.reveal.value);
          arrowColors.array.set(color, vertex * 3); vertex++;
        }
      }
    }
    arrowGeometry.setDrawRange(0, vertex);
    if (vertex) { arrowPositions.needsUpdate = true; arrowColors.needsUpdate = true; }
  }

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
  const hazes: { sprite: THREE.Sprite; group: string; from: number; to: number }[] = [];
  for (const cluster of graph.clusters.slice(0, 9)) {
    const haze = new THREE.Sprite(hazeMaterial.clone()); haze.position.set(...cluster.position);
    haze.scale.setScalar(cluster.radius * 5); world.add(haze);
    hazes.push({ sprite: haze, group: cluster.id, from: .45, to: .45 });
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
  function currentPoint(index: number): Vec3 {
    const offset = index * 3;
    return [0, 1, 2].map(axis => pointSource.array[offset + axis] +
      (pointTarget.array[offset + axis] - pointSource.array[offset + axis]) * morph.value) as Vec3;
  }
  function presentationProgress(now: number) {
    return transitioning ? transitionProgress(now - transitionStart, 900) : 1;
  }
  function setPresentation(presentation: CosmicPresentation, animate: boolean) {
    // Focus and visibility changes do not restart a settled layout.
    animate = animate && (transitioning || targetPositions !== presentation.positions);
    targetPositions = presentation.positions;
    // Read the currently drawn pose, including an interrupted transition.
    const progress = morph.value;
    retargetBuffer(pointSource.array, pointTarget.array, progress);
    retargetBuffer(lineSource.array, lineTarget.array, progress);
    presentation.positions.forEach((position, i) => pointTarget.array.set(position, i * 3));
    visibleNodes = presentation.nodes;
    if (selected !== null && !visibleNodes.has(selected)) {
      selected = null;
      uniforms.selected.value = -1;
      reticle.visible = false;
      callbacks.select(null);
    }
    graph.nodes.forEach(({ node }, i) => {
      pointVisible.array[i] = visibleNodes.has(i) ? 1 : 0;
      pointEmphasis.array[i] = !presentation.focus ? 1 : presentation.focus.paths.has(node.id) ? 1.5 : presentation.focus.definitions.has(node.id) ? .28 : .055;
    });
    directedEdges = [];
    regions.setPresentation(presentation);
    starMaterial.opacity = presentation.focus ? .18 : .65;
    graph.edges.forEach((edge, index) => {
      const focused = presentation.focus?.edges.has(edge.id);
      const structural = edge.kind === 'definition' || edge.kind === 'context';
      if (focused && !structural && !edge.aggregated) directedEdges.push(index);
      const strength = !presentation.focus ? 1 : focused ? structural ? 3 : 2 : .018;
      const a = presentation.positions[graph.index.get(edge.from)!];
      const b = presentation.positions[graph.index.get(edge.to)!];
      const range = edgeRanges[index], seed = visualSeed(edge.id);
      for (let offset = 0; offset < range.steps * 2; offset++) {
        const vertex = range.start + offset;
        lineTarget.array.set(edgePoint(a, b, travels[vertex], seed), vertex * 3);
        lineVisible.array[vertex] = presentation.edges.has(index) ? 1 : 0;
        lineEmphasis.array[vertex] = strength;
      }
    });
    const groups = new Set([...visibleNodes].map(i => graph.nodes[i].node.groupId));
    for (const haze of hazes) {
      haze.from = haze.sprite.material.opacity;
      haze.to = presentation.layout === 'files' && groups.has(haze.group) ? presentation.focus ? .025 : .45 : 0;
    }
    if (!animate) {
      pointSource.array.set(pointTarget.array);
      lineSource.array.set(lineTarget.array);
      uniforms.reveal.value = 1;
    }
    [pointSource, pointTarget, lineSource, lineTarget, pointVisible, lineVisible, pointEmphasis, lineEmphasis].forEach(attribute => {
      attribute.needsUpdate = true;
    });
    transitioning = animate;
    transitionStart = performance.now();
    morph.value = animate ? 0 : 1;
    host.dataset.layout = presentation.layout;
    host.dataset.visibleNodes = String(presentation.nodes.size);
    host.dataset.visibleEdges = String(presentation.edges.size);
    host.dataset.focusPaths = JSON.stringify([...(presentation.focus?.paths || [])]);
    host.dataset.focusEdges = JSON.stringify([...(presentation.focus?.edges || [])]);
    host.dataset.focusTerminals = JSON.stringify([...(presentation.focus?.terminals || [])]);
    host.dataset.focusDefinitions = JSON.stringify([...(presentation.focus?.definitions || [])]);
    host.dataset.directionCues = String(directedEdges.length);
    callbacks.hover(null, 0, 0);
    dirty = true;
  }
  const projected = new THREE.Vector3();
  function hit(event: PointerEvent) {
    const bounds = renderer.domElement.getBoundingClientRect();
    const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
    let best = 12 * 12, winner: number | null = null;
    graph.nodes.forEach((node, i) => {
      if (!visibleNodes.has(i)) return;
      projected.set(...currentPoint(i)).multiplyScalar(uniforms.reveal.value).project(camera);
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
    if (transitioning) {
      morph.value = presentationProgress(now);
      dirty = true;
      if (morph.value === 1) transitioning = false;
    }
    if (!dirty) return;
    uniforms.time.value = clock;
    if (enabled) uniforms.reveal.value = Math.max(uniforms.reveal.value, .55 + .45 * (1 - Math.pow(1 - Math.min(1, clock / 2.3), 3)));
    for (const haze of hazes) haze.sprite.material.opacity = haze.from + (haze.to - haze.from) * morph.value;
    if (selected !== null) { reticle.position.set(...currentPoint(selected)).multiplyScalar(uniforms.reveal.value); reticle.quaternion.copy(camera.quaternion); }
    updateArrows();
    regions.update(camera, width, height, morph.value);
    try { composer.render(); } catch {
      failed = true; callbacks.error('The 3D renderer was interrupted. Return to the graph and reopen the universe.');
    }
    dirty = false;
    host.dataset.transition = morph.value.toFixed(4);
    host.dataset.pose = [0, Math.min(59, graph.nodes.length - 1), graph.nodes.length - 1].map(index => currentPoint(index).map(value => value.toFixed(3)).join(',')).join(';');
    if (now - diagnosticAt > 250) {
      host.dataset.sceneTime = clock.toFixed(4);
      host.dataset.camera = camera.position.toArray().map((v) => v.toFixed(3)).join(',');
      host.dataset.ready = 'true'; diagnosticAt = now;
    }
  }
  frame = requestAnimationFrame(animate);
  return {
    setPresentation,
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
      geometries.forEach((geometry) => geometry.dispose()); materials.forEach((material) => material.dispose()); hazeTexture.dispose(); hazeMaterial.dispose();
      regions.dispose();
      bloom.dispose(); output.dispose(); composer.dispose(); renderer.dispose(); renderer.forceContextLoss(); canvas.remove();
    },
  };
}
