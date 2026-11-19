import type { AtlasGraph, GraphEdge, GraphNode } from './types';
import { dataEffect } from './semantics';
import { semanticIndex, roleStyles, type SemanticRole } from './cinematic-semantics';

export type Vec3 = [number, number, number];
export interface CosmicNode {
  node: GraphNode;
  position: Vec3;
  color: Vec3;
  size: number;
  role: SemanticRole;
}
export interface CosmicCluster {
  id: string;
  name: string;
  position: Vec3;
  radius: number;
  count: number;
}
export interface CosmicGraph {
  nodes: CosmicNode[];
  index: Map<string, number>;
  edges: GraphEdge[];
  clusters: CosmicCluster[];
  radius: number;
}

/** Stable visual entropy, never used to infer a code relationship. */
export function visualSeed(value: string) {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) h = Math.imul(h ^ value.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967296;
}
const TAU = Math.PI * 2;

/** A spatial presentation of the existing graph. No synthetic graph nodes/edges. */
export function cosmicGraph(graph: AtlasGraph): CosmicGraph {
  const roles = semanticIndex(graph).roles;
  const real = [...graph.nodes.values()].filter((node) => node.kind !== 'group');
  const counts = new Map<string, number>();
  for (const node of real) if (node.groupId) counts.set(node.groupId, (counts.get(node.groupId) || 0) + 1);
  const ordered = [...graph.groups].sort((a, b) => (counts.get(b.id) || 0) - (counts.get(a.id) || 0) || a.id.localeCompare(b.id));
  const clusters = ordered.map((group, i): CosmicCluster => {
    const count = counts.get(group.id) || 0;
    const angle = i * 2.399963229728653;
    const ring = 140 + Math.sqrt(i) * 42;
    return {
      id: group.id, name: group.name, count,
      position: [Math.cos(angle) * ring * 1.15, (visualSeed(group.id) - .5) * 250, Math.sin(angle) * ring * .8],
      radius: 15 + Math.cbrt(count) * 7.4,
    };
  });
  // Separate larger file volumes; deterministic and independent of render frames.
  for (let step = 0; step < 80; step++) {
    for (let i = 0; i < clusters.length; i++) for (let j = i + 1; j < clusters.length; j++) {
      const a = clusters[i], b = clusters[j];
      const d = a.position.map((v, axis) => v - b.position[axis]);
      const length = Math.hypot(...d) || 1;
      const gap = a.radius + b.radius + 22;
      if (length < gap) for (let axis = 0; axis < 3; axis++) {
        const shift = d[axis] / length * (gap - length) * .22;
        a.position[axis] += shift; b.position[axis] -= shift;
      }
    }
  }
  const byGroup = new Map(clusters.map((cluster) => [cluster.id, cluster]));
  const nodes = real.map((node): CosmicNode => {
    const cluster = byGroup.get(node.groupId || '');
    const seed = visualSeed(node.id), angle = seed * TAU;
    const z = visualSeed(node.id + ':z') * 2 - 1;
    const disk = Math.sqrt(1 - z * z);
    const radius = (cluster?.radius || 70) * Math.cbrt(visualSeed(node.id + ':r')) * (node.canonical ? .57 : 1);
    const center = cluster?.position || [0, 0, 0];
    const effect = dataEffect(node);
    const role = roles.get(node.id)!;
    const color = roleStyles[role].color;
    return {
      node,
      position: [center[0] + Math.cos(angle) * disk * radius, center[1] + z * radius, center[2] + Math.sin(angle) * disk * radius],
      color, role,
      size: node.groupedRoutes?.length ? 9 : node.canonical ? 5.3 : effect ? 4 : 1.9 + seed * 1.3,
    };
  });
  const index = new Map(nodes.map(({ node }, i) => [node.id, i]));
  const edges = graph.edges.filter((edge) => index.has(edge.from) && index.has(edge.to));
  const radius = Math.max(100, ...nodes.map(({ position }) => Math.hypot(...position)));
  return { nodes, index, edges, clusters, radius };
}

/** Smooth arc between the actual recorded endpoints, for geometry and energy alike. */
export function edgePoint(a: Vec3, b: Vec3, t: number, seed: number): Vec3 {
  const distance = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
  const lift = Math.sin(Math.PI * t) * Math.min(85, distance * .17);
  return [
    a[0] + (b[0] - a[0]) * t + Math.cos(seed * TAU) * lift * .35,
    a[1] + (b[1] - a[1]) * t + lift,
    a[2] + (b[2] - a[2]) * t + Math.sin(seed * TAU) * lift * .35,
  ];
}
