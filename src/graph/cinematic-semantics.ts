import { flowIndex } from './flow';
import { dataEffect } from './semantics';
import type { AtlasGraph, GraphNode } from './types';
import type { CosmicGraph, Vec3 } from './cinematic';
import type { CosmicVisibility } from './cinematic-controls';

export type SemanticRole = 'entry' | 'core' | 'read' | 'write' | 'both' | 'external' | 'unresolved' | 'service';
export const roleStyles: Record<SemanticRole, { label: string; color: Vec3; css: string; description: string }> = {
  entry: { label: 'Endpoints', color: [.28, 1, .69], css: '#48ffb0', description: 'Recorded HTTP entry handlers' },
  core: { label: 'Core logic', color: [.26, .52, 1], css: '#4385ff', description: 'In-repository code and authentication context' },
  read: { label: 'Data reads', color: [.12, .91, .94], css: '#1fe8f0', description: 'Recorded read operations and persistence frontiers' },
  write: { label: 'Data writes', color: [1, .42, .23], css: '#ff6b3b', description: 'Recorded write operations and persistence frontiers' },
  both: { label: 'Read + write', color: [1, .76, .25], css: '#ffc240', description: 'Recorded combined persistence effect' },
  external: { label: 'External / libraries', color: [.70, .42, 1], css: '#b36bff', description: 'Targets outside the indexed repository; not necessarily network services' },
  unresolved: { label: 'Unresolved targets', color: [.42, .55, .65], css: '#6b8ca6', description: 'Ambiguous targets; their implementation is not established' },
  service: { label: 'Service / RPC', color: [1, .39, .70], css: '#ff64b3', description: 'Explicit RPC persistence evidence; read/write effect is shown in details' },
};
export const semanticRoles = Object.keys(roleStyles) as SemanticRole[];

export interface RecordedFocus {
  paths: Set<string>;
  definitions: Set<string>;
  edges: Set<string>;
  terminals: Set<string>;
  contexts: number;
  kind: 'data-path' | 'recorded-tree' | 'branch' | 'contexts' | 'untraced';
}
interface SemanticIndex {
  roles: Map<string, SemanticRole>;
  contexts: Map<string, string[]>;
  focuses: Map<string, RecordedFocus>;
}
const indexes = new WeakMap<AtlasGraph, SemanticIndex>();

export function semanticIndex(graph: AtlasGraph): SemanticIndex {
  const cached = indexes.get(graph);
  if (cached) return cached;
  const terminals = flowIndex(graph).terminals;
  const roles = new Map<string, SemanticRole>(), contexts = new Map<string, string[]>();
  for (const node of graph.nodes.values()) {
    if (node.kind === 'group') continue;
    let role: SemanticRole = 'core';
    if (node.groupedRoutes?.length) role = 'entry';
    else if (!node.canonical && node.accesses.some(({ access }) => access.persistenceApi === 'rpc')) role = 'service';
    else if (!node.canonical && terminals.has(node.id)) role = dataEffect(node) || 'unresolved';
    else if (node.call?.resolution === 'external') role = 'external';
    else if (node.call?.resolution === 'ambiguous') role = 'unresolved';
    roles.set(node.id, role);
    if (!node.canonical && node.symbol && (node.kind === 'auth' || node.call?.resolution === 'resolved')) {
      const list = contexts.get(node.symbol.id) || [];
      list.push(node.id);
      contexts.set(node.symbol.id, list);
    }
  }
  const result = { roles, contexts, focuses: new Map<string, RecordedFocus>() };
  indexes.set(graph, result);
  return result;
}

/** Execution evidence follows occurrence trees only; canonical links never form shortcuts. */
export function recordedFocus(graph: AtlasGraph, selected: string): RecordedFocus {
  const index = semanticIndex(graph);
  const cached = index.focuses.get(selected);
  if (cached) return cached;
  const node = graph.nodes.get(selected)!;
  const paths = new Set<string>(), definitions = new Set<string>();
  let kind: RecordedFocus['kind'] = 'branch', contexts = 1;
  const descended = new Set<string>();
  const descend = (id: string) => {
    if (descended.has(id)) return;
    descended.add(id);
    paths.add(id);
    graph.nodes.get(id)!.children.forEach(descend);
  };
  const branch = (id: string) => {
    descend(id);
    let parent = graph.nodes.get(id)!.parent;
    while (parent) {
      paths.add(parent);
      parent = graph.nodes.get(parent)!.parent;
    }
  };
  if (node.groupedRoutes?.length) {
    const flow = flowIndex(graph).entries.get(selected)!;
    if (flow.terminals.size) {
      kind = 'data-path';
      flow.paths.forEach(id => paths.add(id));
    } else {
      kind = 'recorded-tree';
      descend(selected);
    }
    contexts = node.groupedRoutes.length;
  } else if (node.canonical) {
    const occurrences = index.contexts.get(selected) || [];
    kind = occurrences.length ? 'contexts' : 'untraced';
    contexts = occurrences.length;
    occurrences.forEach(branch);
    paths.add(selected);
  } else branch(selected);
  for (const id of paths) {
    const item = graph.nodes.get(id)!;
    if (!item.canonical && item.symbol && !paths.has(item.symbol.id)) definitions.add(item.symbol.id);
  }
  const edges = new Set<string>();
  for (const edge of graph.edges) {
    if (edge.aggregated || !paths.has(edge.from)) continue;
    if (edge.kind === 'definition' ? definitions.has(edge.to) || paths.has(edge.to) : paths.has(edge.to)) edges.add(edge.id);
  }
  const terminals = new Set([...flowIndex(graph).terminals].filter(id => paths.has(id)));
  const result = { paths, definitions, edges, terminals, contexts, kind };
  index.focuses.set(selected, result);
  return result;
}

export function focusVisibility(cosmic: CosmicGraph, base: CosmicVisibility, focus: RecordedFocus | null): CosmicVisibility {
  if (!focus) return base;
  const nodes = new Set(base.nodes), edges = new Set(base.edges);
  for (const id of [...focus.paths, ...focus.definitions]) {
    const index = cosmic.index.get(id);
    if (index !== undefined) nodes.add(index);
  }
  cosmic.edges.forEach((edge, i) => {
    if (focus.edges.has(edge.id) && nodes.has(cosmic.index.get(edge.from)!) && nodes.has(cosmic.index.get(edge.to)!)) edges.add(i);
  });
  return { nodes, edges };
}

export function focusDescription(focus: RecordedFocus) {
  if (focus.kind === 'untraced') return 'No recorded trace';
  if (focus.kind === 'recorded-tree') return 'Recorded request tree · no data terminal recorded';
  if (focus.kind === 'contexts') return `${focus.contexts} recorded occurrence ${focus.contexts === 1 ? 'context' : 'contexts'}`;
  return focus.kind === 'data-path' ? 'Recorded entry → data paths' : 'Recorded ancestry + descendant branch';
}

export function serviceEvidence(node: GraphNode) {
  return node.accesses.some(({ access }) => access.persistenceApi === 'rpc');
}
