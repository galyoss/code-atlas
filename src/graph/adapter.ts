import type {
  AtlasGraph,
  AuthStep,
  Call,
  EvidenceRef,
  GraphDocument,
  GraphEdge,
  GraphNode,
  Route,
  SourceGroup,
} from './types';

// Tuple serialization keeps producer IDs distinct even if they contain separators.
export const callNodeId = (
  routeId: string,
  callId: string,
  authStepId?: string,
) => `call:${JSON.stringify([routeId, authStepId ?? null, callId])}`;
export const authNodeId = (routeId: string, stepId: string) =>
  `auth:${JSON.stringify([routeId, stepId])}`;
export const groupNodeId = (file: string) => `file:${file}`;

export function adaptGraph(document: GraphDocument): AtlasGraph {
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];
  const pairs = new Map<string, GraphEdge>();
  const groups = new Map<string, SourceGroup>();
  const symbols = new Map(
    document.symbolIndex.map((symbol) => [symbol.id, symbol]),
  );
  for (const symbol of document.symbolIndex) {
    const file = symbol.range.file,
      groupId = groupNodeId(file);
    if (!groups.has(groupId))
      groups.set(groupId, {
        id: groupId,
        file,
        name: file.split('/').at(-1)!,
        members: [],
      });
    groups.get(groupId)!.members.push(symbol.id);
    nodes.set(symbol.id, {
      id: symbol.id,
      name: symbol.name,
      subtitle: symbol.qualifiedName,
      kind: 'symbol',
      children: [],
      groupId,
      symbol,
      range: symbol.range,
      accesses: [],
      authSteps: [],
      canonical: true,
    });
  }
  // Only the immediate resolved parent can establish a symbol-to-symbol call.
  function aggregate(
    parentSymbol: string | undefined,
    call: Call,
    ref: EvidenceRef,
  ) {
    if (
      !parentSymbol ||
      !symbols.has(parentSymbol) ||
      call.resolution !== 'resolved' ||
      !call.symbolId ||
      !symbols.has(call.symbolId)
    )
      return;
    const id = `pair:${JSON.stringify([parentSymbol, call.symbolId])}`;
    if (!pairs.has(id))
      pairs.set(id, {
        id,
        from: parentSymbol,
        to: call.symbolId,
        kind: 'call',
        evidence: [],
        aggregated: true,
      });
    pairs.get(id)!.evidence.push(ref);
  }
  function addCalls(
    calls: Call[],
    parent: GraphNode,
    parentSymbol: string | undefined,
    route: Route,
    authStep?: AuthStep,
  ) {
    for (const call of calls) {
      const evidence: EvidenceRef = {
        routeId: route.id,
        callId: call.id,
        ...(authStep ? { authStepId: authStep.id } : {}),
      };
      aggregate(parentSymbol, call, evidence);
      const accesses = route.dataAccesses
        .filter((access) => access.callId === call.id)
        .map((access) => ({ route, access }));
      const resolvedSymbol =
        call.resolution === 'resolved' && call.symbolId
          ? symbols.get(call.symbolId)
          : undefined;
      const node: GraphNode = {
        id: callNodeId(route.id, call.id, authStep?.id),
        name: call.calleeName,
        subtitle: `${call.resolution} · ${call.callSite.file}:${call.callSite.startLine}`,
        kind:
          call.resolution === 'ambiguous'
            ? 'gap'
            : accesses.length
              ? 'data'
              : 'call',
        parent: parent.id,
        groupId: parent.groupId,
        route,
        call,
        children: [],
        evidence,
        range: call.callSite,
        symbol: resolvedSymbol,
        accesses,
        authSteps: [],
      };
      nodes.set(node.id, node);
      parent.children.push(node.id);
      edges.push({
        id: `occurrence:${node.id}`,
        from: parent.id,
        to: node.id,
        kind: node.kind === 'gap' ? 'unresolved' : 'call',
        evidence: [evidence],
      });
      if (resolvedSymbol)
        edges.push({
          id: `definition:${node.id}`,
          from: node.id,
          to: resolvedSymbol.id,
          kind: 'definition',
          evidence: [evidence],
        });
      addCalls(call.children, node, resolvedSymbol?.id, route, authStep);
    }
  }
  for (const route of document.routes) {
    const handler = nodes.get(route.handler.symbolId);
    if (!handler)
      throw new Error(`Missing handler symbol: ${route.handler.symbolId}`);
    handler.kind = 'route';
    handler.route ??= route;
    handler.groupedRoutes = [...(handler.groupedRoutes || []), route];
    addCalls(route.callGraph, handler, handler.id, route);
    for (const step of route.authChain) {
      const id = authNodeId(route.id, step.id);
      const node: GraphNode = {
        id,
        name: step.qualifiedName.split('.').at(-1)!,
        subtitle: `${step.kind} · ${step.mechanism}`,
        kind: 'auth',
        parent: handler.id,
        groupId: handler.groupId,
        route,
        children: [],
        symbol: step.symbolId ? symbols.get(step.symbolId) : undefined,
        range: step.range,
        accesses: [],
        authSteps: [{ route, step }],
      };
      nodes.set(id, node);
      handler.children.push(id);
      edges.push({
        id: `context:${id}`,
        from: handler.id,
        to: id,
        kind: 'context',
        evidence: [],
      });
      if (node.symbol) {
        nodes.get(node.symbol.id)!.authSteps.push({ route, step });
        edges.push({
          id: `definition:${id}`,
          from: id,
          to: node.symbol.id,
          kind: 'definition',
          evidence: [],
        });
      }
      addCalls(step.calls, node, step.symbolId, route, step);
    }
  }
  for (const group of groups.values())
    nodes.set(group.id, {
      id: group.id,
      name: group.name,
      subtitle: group.file,
      sourceFile: group.file,
      kind: 'group',
      children: group.members,
      accesses: [],
      authSteps: [],
    });
  return {
    document,
    nodes,
    groups: [...groups.values()],
    baseIds: document.symbolIndex.map((symbol) => symbol.id),
    edges: [...pairs.values(), ...edges],
    defaultId: document.routes[0].handler.symbolId,
  };
}

export function visibleIds(
  graph: AtlasGraph,
  expanded: ReadonlySet<string>,
  collapsed: ReadonlySet<string>,
): Set<string> {
  const visible = new Set(graph.groups.map((group) => group.id));
  function visit(id: string) {
    visible.add(id);
    if (expanded.has(id)) graph.nodes.get(id)!.children.forEach(visit);
  }
  for (const id of graph.baseIds)
    if (!collapsed.has(graph.nodes.get(id)!.groupId!)) visit(id);
  return visible;
}

/** Collapsed files keep their real boundary connections and the original evidence. */
export function visibleEdges(
  graph: AtlasGraph,
  visible: ReadonlySet<string>,
  collapsed: ReadonlySet<string>,
): GraphEdge[] {
  const endpoint = (id: string) => {
    const node = graph.nodes.get(id)!;
    return node.canonical &&
      !visible.has(id) &&
      (collapsed.has(node.groupId!) || visible.has(node.groupId!))
      ? node.groupId!
      : id;
  };
  return graph.edges.flatMap((edge) => {
    const from = endpoint(edge.from),
      to = endpoint(edge.to);
    if (
      !visible.has(from) ||
      !visible.has(to) ||
      (from === to && edge.from !== edge.to)
    )
      return [];
    return [{ ...edge, from, to }];
  });
}
