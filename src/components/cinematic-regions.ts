import * as THREE from 'three';
import type { CosmicGraph } from '../graph/cinematic';
import type { CosmicPresentation } from '../graph/cinematic-controls';
import { placeRegionLabel, type LabelRect } from '../graph/cinematic-labels';
import { roleStyles, semanticRoles } from '../graph/cinematic-semantics';

/** Subtle spatial envelopes. Labels are projected from the same world bounds on every camera frame. */
export function createSemanticRegions(host: HTMLElement, world: THREE.Group, graph: CosmicGraph) {
  const layer = document.createElement('div');
  layer.className = 'universe-regions';
  layer.setAttribute('aria-label', 'Spatial code regions');
  host.appendChild(layer);
  const svgNamespace = 'http://www.w3.org/2000/svg';
  const leaders = document.createElementNS(svgNamespace, 'svg'); leaders.setAttribute('class', 'universe-region-leaders');
  leaders.setAttribute('aria-hidden', 'true'); layer.appendChild(leaders);
  const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 128;
  const context = canvas.getContext('2d')!;
  const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, '#ffffff38'); gradient.addColorStop(.45, '#ffffff18'); gradient.addColorStop(1, '#ffffff00');
  context.fillStyle = gradient; context.fillRect(0, 0, 128, 128);
  const texture = new THREE.CanvasTexture(canvas);
  const regions = semanticRoles.map(role => {
    const style = roleStyles[role];
    const color = new THREE.Color(...style.color);
    const group = new THREE.Group(); world.add(group);
    const haze = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, color, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0 }));
    group.add(haze);
    const boundary = new THREE.Group(); group.add(boundary);
    const material = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0, depthWrite: false });
    for (const plane of ['xy', 'xz', 'yz']) {
      const points = Array.from({ length: 129 }, (_, i) => {
        const angle = i / 128 * Math.PI * 2, a = Math.cos(angle), b = Math.sin(angle);
        return plane === 'xy' ? new THREE.Vector3(a, b, 0) : plane === 'xz' ? new THREE.Vector3(a, 0, b) : new THREE.Vector3(0, a, b);
      });
      boundary.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material));
    }
    const label = document.createElement('div'); label.className = 'universe-region'; label.dataset.role = role;
    label.style.setProperty('--role-color', style.css); label.title = style.description;
    const title = document.createElement('strong'), count = document.createElement('span');
    title.textContent = style.label; label.append(title, count); layer.appendChild(label);
    const leader = document.createElementNS(svgNamespace, 'line'); leader.setAttribute('stroke', style.css);
    leaders.appendChild(leader);
    return { role, group, haze, boundary, material, label, count, leader, size: { width: 0, height: 0 }, anchor: new THREE.Vector3(), active: false, strength: 1 };
  });
  const projected = new THREE.Vector3();
  let measureLabels = true, measuredWidth = 0, measuredHeight = 0;
  return {
    setPresentation(presentation: CosmicPresentation) {
      measureLabels = true;
      for (const region of regions) {
        const members = [...presentation.nodes].filter(i => graph.nodes[i].role === region.role);
        region.active = presentation.layout === 'data' && members.length > 0;
        region.count.textContent = `${members.length.toLocaleString()} recorded nodes`;
        region.label.dataset.count = String(members.length);
        region.strength = presentation.focus ? members.some(i => presentation.focus!.paths.has(graph.nodes[i].node.id)) ? .75 : .2 : 1;
        if (!region.active) continue;
        const bounds = new THREE.Box3();
        members.forEach(i => bounds.expandByPoint(new THREE.Vector3(...presentation.positions[i])));
        const center = bounds.getCenter(new THREE.Vector3());
        const radius = bounds.getSize(new THREE.Vector3()).multiplyScalar(.53).addScalar(22);
        region.group.position.copy(center);
        region.boundary.scale.copy(radius);
        region.haze.scale.set(radius.x * 2.8, radius.y * 2.8, 1);
        region.anchor.copy(center).add(new THREE.Vector3(0, radius.y + 20, 0));
      }
    },
    update(camera: THREE.Camera, width: number, height: number, progress: number) {
      if (!regions.some(region => region.active)) {
        regions.forEach(region => {
          region.haze.material.opacity = 0; region.material.opacity = 0;
          region.label.hidden = true; region.leader.style.display = 'none';
        });
        return;
      }
      // Project first, then avoid the actual UI rectangles without moving the region itself.
      const hostBounds = host.getBoundingClientRect();
      const obstacles: LabelRect[] = [];
      host.parentElement?.querySelectorAll<HTMLElement>('.universe-header, .universe-semantic-key, .universe-rail, .universe-detail, .universe-dock, .universe-title, .universe-index, .universe-rail-toggle').forEach(element => {
        const style = getComputedStyle(element);
        if (style.visibility === 'hidden' || style.display === 'none') return;
        const rect = element.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        obstacles.push({ x: rect.left - hostBounds.left, y: rect.top - hostBounds.top, width: rect.width, height: rect.height });
      });
      const arrival = Math.max(0, (progress - .65) / .35);
      if (measureLabels || measuredWidth !== width || measuredHeight !== height) {
        regions.forEach(region => { region.label.hidden = false; });
        regions.forEach(region => { region.size = { width: region.label.offsetWidth, height: region.label.offsetHeight }; });
        measureLabels = false; measuredWidth = width; measuredHeight = height;
      }
      regions.forEach(region => {
        const opacity = region.active ? arrival * region.strength : 0;
        region.haze.material.opacity = opacity * .28;
        region.material.opacity = opacity * .11;
        projected.copy(region.anchor).project(camera);
        const x = (projected.x + 1) * width / 2, y = (1 - projected.y) * height / 2;
        const inView = opacity > .01 && projected.z > -1 && projected.z < 1 && x > 0 && x < width && y > 0 && y < height;
        const placement = inView ? placeRegionLabel({ x, y }, region.size, { width, height }, obstacles) : null;
        region.label.hidden = !placement;
        region.leader.style.display = placement ? '' : 'none';
        if (!placement) return;
        obstacles.push(placement);
        region.label.style.opacity = String(Math.max(.6, opacity));
        region.label.style.transform = `translate(${placement.x}px, ${placement.y}px)`;
        region.label.dataset.projected = `${x.toFixed(1)},${y.toFixed(1)}`;
        const endX = Math.max(placement.x, Math.min(placement.x + placement.width, x));
        const endY = Math.max(placement.y, Math.min(placement.y + placement.height, y));
        region.leader.setAttribute('x1', String(x)); region.leader.setAttribute('y1', String(y));
        region.leader.setAttribute('x2', String(endX)); region.leader.setAttribute('y2', String(endY));
        region.leader.style.opacity = String(Math.max(.2, opacity * .45));
      });
    },
    dispose() { layer.remove(); texture.dispose(); },
  };
}
