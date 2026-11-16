import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationNodeDatum,
} from 'd3-force';
import type { AtlasGraph, Camera, Point } from './types';

export const GLYPH_RADIUS = 8;
const PITCH = 34;
export interface GroupRegion extends Point {
  radius: number;
}
export interface NetworkLayout {
  positions: Map<string, Point>;
  regions: Map<string, GroupRegion>;
}
interface LayoutGroup extends SimulationNodeDatum {
  id: string;
  radius: number;
}

function hexSlots(count: number): Point[] {
  const radius = Math.ceil(Math.sqrt(count));
  const points: Point[] = [];
  for (let q = -radius; q <= radius; q++)
    for (let r = -radius; r <= radius; r++)
      points.push({
        x: PITCH * (q + r / 2),
        y: ((PITCH * Math.sqrt(3)) / 2) * r,
      });
  return points
    .sort(
      (a, b) =>
        Math.hypot(a.x, a.y) - Math.hypot(b.x, b.y) ||
        Math.atan2(a.y, a.x) - Math.atan2(b.y, b.x),
    )
    .slice(0, count);
}

/** D3 is stopped before its first frame. Only fixed, deterministic output enters React. */
export function layoutGraph(graph: AtlasGraph): NetworkLayout {
  const slots = new Map(
    graph.groups.map((group) => [group.id, hexSlots(group.members.length)]),
  );
  const groups: LayoutGroup[] = graph.groups.map((group) => ({
    id: group.id,
    radius:
      Math.max(
        ...slots.get(group.id)!.map((point) => Math.hypot(point.x, point.y)),
      ) + 28,
  }));
  const groupBySymbol = new Map(
    graph.baseIds.map((id) => [id, graph.nodes.get(id)!.groupId!]),
  );
  const uniqueLinks = new Map<string, { source: string; target: string }>();
  for (const edge of graph.edges.filter((edge) => edge.aggregated)) {
    const source = groupBySymbol.get(edge.from)!,
      target = groupBySymbol.get(edge.to)!;
    if (source !== target)
      uniqueLinks.set([source, target].sort().join('|'), { source, target });
  }
  const byId = new Map(groups.map((group) => [group.id, group]));
  forceSimulation(groups)
    .stop()
    .force(
      'links',
      forceLink<LayoutGroup, { source: string; target: string }>([
        ...uniqueLinks.values(),
      ])
        .id((group) => group.id)
        .distance(
          (link) =>
            byId.get(
              typeof link.source === 'string'
                ? link.source
                : (link.source as LayoutGroup).id,
            )!.radius +
            byId.get(
              typeof link.target === 'string'
                ? link.target
                : (link.target as LayoutGroup).id,
            )!.radius +
            42,
        )
        .strength(0.09),
    )
    .force('charge', forceManyBody().strength(-160))
    .force('x', forceX(0).strength(0.012))
    .force('y', forceY(0).strength(0.055))
    .force(
      'collision',
      forceCollide<LayoutGroup>((group) => group.radius + 13).iterations(5),
    )
    .tick(450);
  const positions = new Map<string, Point>(),
    regions = new Map<string, GroupRegion>();
  const degree = new Map<string, number>();
  for (const edge of graph.edges.filter((edge) => edge.aggregated))
    for (const id of [edge.from, edge.to])
      degree.set(id, (degree.get(id) || 0) + 1);
  for (const group of graph.groups) {
    const center = byId.get(group.id)!;
    const region = { x: center.x!, y: center.y!, radius: center.radius };
    regions.set(group.id, region);
    positions.set(group.id, { x: region.x, y: region.y - region.radius - 7 });
    [...group.members]
      .sort(
        (a, b) =>
          (degree.get(b) || 0) - (degree.get(a) || 0) || a.localeCompare(b),
      )
      .forEach((id, index) => {
        const point = slots.get(group.id)![index];
        positions.set(id, { x: region.x + point.x, y: region.y + point.y });
      });
  }
  return { positions, regions };
}

/** Append-only detail anchors: reveal order never relocates an existing glyph. A spatial
 * grid finds the nearest free slot around its recorded parent, including hidden anchors. */
export class DetailAnchors {
  readonly positions: Map<string, Point>;
  private occupied = new Map<string, Point[]>();
  constructor(layout: NetworkLayout) {
    this.positions = new Map(layout.positions);
    for (const point of this.positions.values()) this.reserve(point);
    // File labels have their own reserved breathing room.
    for (const region of layout.regions.values())
      for (let x = -66; x <= 66; x += 22)
        this.reserve({ x: region.x + x, y: region.y - region.radius - 7 });
  }
  private key(point: Point) {
    return `${Math.floor(point.x / PITCH)},${Math.floor(point.y / PITCH)}`;
  }
  private reserve(point: Point) {
    const key = this.key(point),
      cell = this.occupied.get(key) || [];
    cell.push(point);
    this.occupied.set(key, cell);
  }
  private free(point: Point) {
    const x = Math.floor(point.x / PITCH),
      y = Math.floor(point.y / PITCH);
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++)
        for (const other of this.occupied.get(`${x + dx},${y + dy}`) || [])
          if (Math.hypot(point.x - other.x, point.y - other.y) < PITCH - 0.1)
            return false;
    return true;
  }
  ensure(graph: AtlasGraph, ids: ReadonlySet<string>) {
    const place = (id: string): Point => {
      if (this.positions.has(id)) return this.positions.get(id)!;
      const node = graph.nodes.get(id)!;
      const parent = place(node.parent!);
      // Rotate the search deterministically so branches grow in distinct directions.
      const phase =
        ([...id].reduce((hash, c) => (hash * 31 + c.charCodeAt(0)) >>> 0, 0) /
          4294967296) *
        Math.PI *
        2;
      for (let ring = 1; ; ring++) {
        const radius = ring * PITCH,
          steps = ring * 8;
        for (let step = 0; step < steps; step++) {
          const angle = phase + (step / steps) * Math.PI * 2;
          const point = {
            x: parent.x + Math.cos(angle) * radius,
            y: parent.y + Math.sin(angle) * radius,
          };
          if (!this.free(point)) continue;
          this.positions.set(id, point);
          this.reserve(point);
          return point;
        }
      }
    };
    for (const id of ids) place(id);
    return this.positions;
  }
}

export function fitCamera(
  positions: Map<string, Point>,
  ids: ReadonlySet<string>,
  width: number,
  height: number,
): Camera {
  const points = [...ids].map((id) => positions.get(id)!).filter(Boolean);
  const minX = Math.min(...points.map((p) => p.x)) - 80,
    maxX = Math.max(...points.map((p) => p.x)) + 80;
  const minY = Math.min(...points.map((p) => p.y)) - 55,
    maxY = Math.max(...points.map((p) => p.y)) + 55;
  const scale = Math.min(
    1.2,
    (width - 40) / (maxX - minX),
    (height - 70) / (maxY - minY),
  );
  return {
    scale: Math.max(0.12, scale),
    x: (width - (minX + maxX) * scale) / 2,
    y: (height - (minY + maxY) * scale) / 2,
  };
}
/** A phone opens at a usable glyph size around the first recorded handler. The
 * entire canonical network still exists, and explicit Fit can show its full extent. */
export function initialCamera(
  layout: NetworkLayout,
  graph: AtlasGraph,
  width: number,
  height: number,
): Camera {
  if (width >= 600)
    return fitCamera(
      layout.positions,
      new Set(layout.positions.keys()),
      width,
      height,
    );
  const point = layout.positions.get(graph.defaultId)!;
  const scale = 1;
  return {
    scale,
    x: width / 2 - point.x * scale,
    y: height / 2 - point.y * scale,
  };
}

export function zoomCamera(
  camera: Camera,
  factor: number,
  center: Point,
): Camera {
  const scale = Math.max(0.12, Math.min(3, camera.scale * factor));
  return {
    scale,
    x: center.x - ((center.x - camera.x) * scale) / camera.scale,
    y: center.y - ((center.y - camera.y) * scale) / camera.scale,
  };
}
