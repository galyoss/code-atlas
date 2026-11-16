import type { AtlasGraph, Call, GraphDocument, GraphEdge, GraphNode, Route } from './types';

// Call IDs are scoped by route even when a producer reuses a local call ID.
export const callNodeId = (routeId: string, callId: string) => `call:${routeId}:${callId}`;
export const routeNodeId = (routeId: string) => `route:${routeId}`;
const shortName = (name: string) => name.split('.').at(-1) || name;
const basename = (path: string) => path.split('/').at(-1) || path;

export function adaptGraph(document: GraphDocument): AtlasGraph {
  const nodes = new Map<string, GraphNode>();
  const baseIds: string[] = [];
  const edges: GraphEdge[] = [];
  const symbols = new Map(document.symbolIndex.map((symbol) => [symbol.id, symbol]));
  const addBase = (node: GraphNode) => {
    nodes.set(node.id, node);
    baseIds.push(node.id);
  };
  const edge = (from: string, to: string, kind: GraphEdge['kind']) => {
    const id = `${kind}:${from}:${to}`;
    if (!edges.some((item) => item.id === id)) edges.push({ id, from, to, kind });
  };
  function addCalls(calls: Call[], parent: GraphNode, route: Route) {
    for (const call of calls) {
      const accesses = route.dataAccesses
        .filter((access) => access.callId === call.id)
        .map((access) => ({ route, access }));
      const node: GraphNode = {
        id: callNodeId(route.id, call.id),
        name: call.calleeName,
        subtitle:
          call.resolution === 'ambiguous'
            ? 'unresolved target'
            : accesses.length
              ? accesses.map(({ access }) => `${access.operation} ${access.object.name}`).join(' · ')
              : call.expanded === 'partial'
                ? `partial · ${call.children.length} calls`
                : call.resolution === 'external'
                  ? 'external call'
                  : basename(call.callSite.file),
        kind: call.resolution === 'ambiguous' ? 'gap' : accesses.length ? 'data' : 'call',
        call,
        route,
        parent: parent.id,
        children: [],
        accesses,
        authSteps: [],
        range: call.callSite,
        symbol: call.symbolId ? symbols.get(call.symbolId) : undefined,
      };
      nodes.set(node.id, node);
      parent.children.push(node.id);
      edge(parent.id, node.id, node.kind === 'gap' ? 'unresolved' : 'call');
      addCalls(call.children, node, route);
    }
  }
  for (const route of document.routes) {
    const node: GraphNode = {
      id: routeNodeId(route.id),
      name: shortName(route.handler.qualifiedName),
      subtitle: `${route.httpMethod} ${route.pathTemplate}`,
      kind: 'route',
      children: [],
      route,
      symbol: symbols.get(route.handler.symbolId),
      range: route.handler.range,
      accesses: [],
      authSteps: [],
    };
    addBase(node);
    for (const step of route.authChain.filter((item) => item.mechanism !== 'inline')) {
      const id = `auth:${step.symbolId || `${route.id}:${step.id}`}`;
      if (!nodes.has(id))
        addBase({
          id,
          name: shortName(step.qualifiedName),
          subtitle: 'auth context · collapsed',
          kind: 'auth',
          children: [],
          range: step.range,
          symbol: step.symbolId ? symbols.get(step.symbolId) : undefined,
          accesses: [],
          authSteps: [],
        });
      nodes.get(id)!.authSteps.push({ route, step });
      edge(node.id, id, 'context');
    }
    for (const access of route.dataAccesses) {
      const id = `model:${access.object.symbolId || `${access.object.store}:${access.object.name}`}`;
      if (!nodes.has(id))
        addBase({
          id,
          name: access.object.name,
          subtitle: 'data summary',
          kind: 'model',
          children: [],
          accesses: [],
          authSteps: [],
          symbol: access.object.symbolId ? symbols.get(access.object.symbolId) : undefined,
        });
      nodes.get(id)!.accesses.push({ route, access });
      edge(node.id, id, 'summary');
    }
    addCalls(route.callGraph, node, route);
  }
  return { document, nodes, baseIds, edges, defaultId: routeNodeId(document.routes[0].id) };
}

export function ancestors(graph: AtlasGraph, id: string): string[] {
  const result: string[] = [];
  let node = graph.nodes.get(id);
  while (node) {
    result.unshift(node.id);
    node = node.parent ? graph.nodes.get(node.parent) : undefined;
  }
  return result;
}

export function visibleIds(graph: AtlasGraph, path: string[]): Set<string> {
  return new Set([...graph.baseIds, ...path.flatMap((id) => graph.nodes.get(id)?.children || [])]);
}
