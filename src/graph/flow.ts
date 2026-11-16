import type { AtlasGraph } from './types';
import { persistenceEffect } from './semantics';

export interface RecordedFlow {
  /** Occurrences and roots on recorded paths, without canonical shortcuts. */
  paths: Set<string>;
  terminals: Set<string>;
  definitions: Set<string>;
  edges: Set<string>;
}
export interface FlowIndex {
  entries: Map<string, RecordedFlow>;
  overview: RecordedFlow;
  terminals: Set<string>;
}
const indexes = new WeakMap<AtlasGraph, FlowIndex>();

/** Index producer trees once. An effect is a frontier only when no deeper terminal
 * is recorded; named access calls are terminals even when they have children. */
export function flowIndex(graph: AtlasGraph): FlowIndex {
  const cached = indexes.get(graph);
  if (cached) return cached;
  function project(terminals: Set<string>, roots: string[] = []): RecordedFlow {
    const paths = new Set(roots),
      definitions = new Set<string>();
    for (const id of terminals) {
      let node = graph.nodes.get(id)!;
      paths.add(node.id);
      while (node.parent) {
        node = graph.nodes.get(node.parent)!;
        paths.add(node.id);
      }
    }
    for (const id of paths) {
      const node = graph.nodes.get(id)!;
      if (!node.canonical && node.symbol) definitions.add(node.symbol.id);
    }
    const edges = new Set<string>();
    for (const edge of graph.edges) {
      // Canonical pairs can contain evidence from other routes. The occurrence
      // edges are the exact paths; definition edges provide separate context.
      if (edge.aggregated) continue;
      if (
        paths.has(edge.from) &&
        (paths.has(edge.to) ||
          (edge.kind === 'definition' && definitions.has(edge.to)))
      )
        edges.add(edge.id);
    }
    return { paths, terminals, definitions, edges };
  }
  const entries = new Map<string, RecordedFlow>(),
    terminals = new Set<string>();
  const named = new Set<string>();
  for (const id of graph.baseIds) {
    if (!graph.nodes.get(id)!.groupedRoutes?.length) continue;
    const entryTerminals = new Set<string>();
    function visit(id: string): boolean {
      const node = graph.nodes.get(id)!;
      const deeper = node.children.map(visit).some(Boolean);
      const access = !node.canonical && node.accesses.length > 0;
      if (access) named.add(id);
      const terminal =
        access ||
        (!deeper && !!persistenceEffect(node.call?.touchesPersistence));
      if (terminal) {
        entryTerminals.add(id);
        terminals.add(id);
      }
      return terminal || deeper;
    }
    graph.nodes.get(id)!.children.forEach(visit);
    entries.set(id, project(entryTerminals, [id]));
  }
  const result = { entries, overview: project(named), terminals };
  indexes.set(graph, result);
  return result;
}
