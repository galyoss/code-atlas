import { visualSeed, type CosmicGraph, type Vec3 } from './cinematic';
import type { RecordedFocus } from './cinematic-semantics';
import type { AtlasGraph } from './types';

export type CosmicLayout = 'files' | 'entries' | 'data';
export type CosmicResolution = 'all' | 'symbols';
export interface CosmicFilter {
  resolution: CosmicResolution;
  group: string;
  query: string;
}
export interface CosmicVisibility {
  nodes: Set<number>;
  edges: Set<number>;
}
export interface CosmicPresentation extends CosmicVisibility {
  layout: CosmicLayout;
  positions: Vec3[];
  focus?: RecordedFocus | null;
}

/** Layout depends on identity and recorded semantics, never the current filter. */
export function cosmicLayouts(_graph: AtlasGraph, cosmic: CosmicGraph): Record<CosmicLayout, Vec3[]> {
  function volume(id: string, center: number, width: number, height: number, depth: number): Vec3 {
    const theta = visualSeed(`angle:${id}`) * Math.PI * 2;
    const z = visualSeed(`latitude:${id}`) * 2 - 1;
    const radius = Math.cbrt(visualSeed(`radius:${id}`));
    const disk = Math.sqrt(1 - z * z);
    return [center + Math.cos(theta) * disk * radius * width, z * radius * height, Math.sin(theta) * disk * radius * depth];
  }
  return {
    files: cosmic.nodes.map(({ position }) => position),
    entries: cosmic.nodes.map(({ node }) => node.groupedRoutes?.length
      ? volume(node.id, -340, 105, 230, 160)
      : volume(node.id, 160, 275, 280, 245)),
    data: cosmic.nodes.map(({ node, role }) => {
      if (role === 'entry') return volume(node.id, -390, 90, 220, 150);
      if (role === 'read') {
        const p = volume(node.id, 390, 105, 115, 150);
        return [p[0], p[1] + 150, p[2] - 25];
      }
      if (role === 'write') {
        const p = volume(node.id, 390, 115, 115, 155);
        return [p[0], p[1] - 150, p[2] + 25];
      }
      if (role === 'both' || role === 'service') {
        const p = volume(node.id, 420, 105, 100, 100);
        return [p[0], p[1], p[2] + (role === 'service' ? 230 : -190)];
      }
      const p = volume(node.id, 0, 195, role === 'external' ? 155 : 175, 145);
      if (role === 'external') return [p[0], p[1] - 180, p[2] - 40];
      if (role === 'unresolved') return [p[0], p[1] + 65, p[2] - 230];
      return [p[0], p[1] + 125, p[2] + 75];
    }),
  };
}

/** Literal AND terms over recorded fields, matching the existing search convention. */
export function filterCosmic(graph: CosmicGraph, filter: CosmicFilter): CosmicVisibility {
  const terms = filter.query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const nodes = new Set<number>();
  graph.nodes.forEach(({ node }, i) => {
    if (filter.resolution === 'symbols' && !node.canonical) return;
    if (filter.group && node.groupId !== filter.group) return;
    if (terms.length) {
      const fields = [node.name, node.subtitle, node.range?.file, node.symbol?.qualifiedName,
        node.route?.httpMethod, node.route?.pathTemplate,
        ...(node.groupedRoutes || []).map(route => `${route.httpMethod} ${route.pathTemplate}`),
      ].join(' ').toLocaleLowerCase();
      if (!terms.every(term => fields.includes(term))) return;
    }
    nodes.add(i);
  });
  const edges = new Set<number>();
  graph.edges.forEach((edge, i) => {
    if (nodes.has(graph.index.get(edge.from)!) && nodes.has(graph.index.get(edge.to)!)) edges.add(i);
  });
  return { nodes, edges };
}

export function transitionProgress(elapsed: number, duration: number) {
  const t = Math.max(0, Math.min(1, elapsed / duration));
  return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/** Bake the currently displayed interpolation before a new target is assigned. */
export function retargetBuffer(source: { length: number; [index: number]: number }, target: ArrayLike<number>, progress: number) {
  for (let i = 0; i < source.length; i++) source[i] += (target[i] - source[i]) * progress;
}
