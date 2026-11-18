import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import { adaptGraph } from './adapter';
import { flowIndex } from './flow';
import {
  activeFlow,
  initialNavigation,
  navigate,
  navigationVisibleIds,
  branchDepth,
  primaryNodeAction,
} from './navigation';
import { ViewAnchors } from './view-layout';
import { layoutGraph } from './layout';
import type { Call, GraphDocument, Route } from './types';
const document = raw as GraphDocument;
const graph = adaptGraph(document);
const sorted = (ids: Iterable<string>) => [...ids].sort();

// Independent raw traversal: accumulate complete root-to-leaf records and select
// frontiers by descendant evidence, without adapter parent links or flow helpers.
function oracle(route: Route) {
  const terminals = new Set<string>(),
    paths = new Set<string>([route.handler.symbolId]);
  const named = new Set<string>(),
    namedPaths = new Set<string>(),
    edges = new Set<string>();
  const definitions = new Set<string>();
  const symbols = new Set(document.symbolIndex.map((s) => s.id));
  function walk(calls: Call[], ancestry: string[], auth?: string): boolean {
    let found = false;
    for (const call of calls) {
      const id = `call:${JSON.stringify([route.id, auth ?? null, call.id])}`;
      const chain = [...ancestry, id];
      const descendant = walk(call.children, chain, auth);
      const access = route.dataAccesses.some((a) => a.callId === call.id);
      if (access) {
        named.add(id);
        chain.forEach((p) => namedPaths.add(p));
      }
      if (
        access ||
        (!descendant &&
          ['read', 'write', 'read_write'].includes(call.touchesPersistence))
      ) {
        terminals.add(id);
        chain.forEach((p) => paths.add(p));
        found = true;
      }
      if (descendant) found = true;
      if (
        (access || descendant || terminals.has(id)) &&
        call.resolution === 'resolved' &&
        call.symbolId &&
        symbols.has(call.symbolId)
      )
        definitions.add(call.symbolId);
    }
    return found;
  }
  walk(route.callGraph, [route.handler.symbolId]);
  for (const auth of route.authChain) {
    const id = `auth:${JSON.stringify([route.id, auth.id])}`;
    if (
      walk(auth.calls, [route.handler.symbolId, id], auth.id) &&
      auth.symbolId &&
      symbols.has(auth.symbolId)
    )
      definitions.add(auth.symbolId);
  }
  for (const id of paths) {
    if (id.startsWith('call:')) edges.add(`occurrence:${id}`);
    if (id.startsWith('auth:')) edges.add(`context:${id}`);
  }
  // Definition evidence is checked against each raw record below, not by edge membership.
  function definitionEdges(calls: Call[], auth?: string) {
    calls.forEach((call) => {
      const id = `call:${JSON.stringify([route.id, auth ?? null, call.id])}`;
      if (
        paths.has(id) &&
        call.resolution === 'resolved' &&
        call.symbolId &&
        symbols.has(call.symbolId)
      )
        edges.add(`definition:${id}`);
      definitionEdges(call.children, auth);
    });
  }
  definitionEdges(route.callGraph);
  for (const auth of route.authChain) {
    const id = `auth:${JSON.stringify([route.id, auth.id])}`;
    if (paths.has(id) && auth.symbolId && symbols.has(auth.symbolId))
      edges.add(`definition:${id}`);
    definitionEdges(auth.calls, auth.id);
  }
  return { paths, terminals, definitions, edges, named, namedPaths };
}

describe('recorded entry-to-data evidence', () => {
  it('matches the complete independently traversed path, terminal, definition and edge sets for every real route', () => {
    for (const route of document.routes) {
      const actual = flowIndex(graph).entries.get(route.handler.symbolId)!;
      const expected = oracle(route);
      for (const key of ['paths', 'terminals', 'definitions', 'edges'] as const)
        expect(
          sorted(actual[key]),
          `${route.httpMethod} ${route.pathTemplate}: ${key}`,
        ).toEqual(sorted(expected[key]));
      expect([...actual.edges].some((id) => id.startsWith('pair:'))).toBe(
        false,
      );
    }
    const index = flowIndex(graph);
    expect(index.terminals.size).toBe(497);
    expect(index.entries.get('sym_create_run')!.terminals.size).toBe(34);
    expect(index.entries.get('sym_create_run')!.paths.size).toBe(43);
    expect(index.entries.get('sym_get_thread')!.terminals.size).toBe(6);
    const expectedOverview = new Set(
      document.routes.flatMap((r) => [...oracle(r).namedPaths]),
    );
    expect(sorted(index.overview.paths)).toEqual(sorted(expectedOverview));
    expect(index.overview.terminals.size).toBe(108);
    expect(
      [...index.overview.paths].filter((id) => !graph.nodes.get(id)!.canonical),
    ).toHaveLength(182);
  });
  it('isolates shared function names and route/auth-qualified occurrences while unioning a multi-route handler', () => {
    const fixture = structuredClone(document),
      original = fixture.routes.find(
        (r) => r.handler.symbolId === 'sym_create_run',
      )!;
    original.authChain = [
      {
        ...original.authChain[0],
        calls: [
          {
            ...original.callGraph[0],
            touchesPersistence: 'read',
            children: [],
          },
        ],
      },
    ];
    const other = {
      ...structuredClone(original),
      id: 'second-route',
      pathTemplate: '/second',
    };
    fixture.routes = [original, other];
    const adapted = adaptGraph(fixture),
      actual = flowIndex(adapted).entries.get(original.handler.symbolId)!;
    for (const key of ['paths', 'terminals', 'definitions', 'edges'] as const)
      expect(sorted(actual[key])).toEqual(
        sorted(new Set([...oracle(original)[key], ...oracle(other)[key]])),
      );
    const originalState = navigate(adapted, initialNavigation(), {
      type: 'reveal',
      id: original.handler.symbolId,
      routeId: original.id,
    });
    const otherState = navigate(adapted, originalState, {
      type: 'reveal',
      id: other.handler.symbolId,
      routeId: other.id,
    });
    for (const [route, state] of [
      [original, originalState],
      [other, otherState],
    ] as const) {
      expect(state.flowRoute).toBe(route.id);
      const expected = oracle(route);
      const active = activeFlow(adapted, state)!;
      for (const key of ['paths', 'terminals', 'definitions', 'edges'] as const)
        expect(sorted(active[key])).toEqual(sorted(expected[key]));
      const visible = navigationVisibleIds(adapted, state);
      for (const id of actual.paths)
        expect(visible.has(id)).toBe(expected.paths.has(id));
    }
    expect(navigate(adapted, otherState, { type: 'back' })).toEqual(
      originalState,
    );
    const wholeHandler = navigate(adapted, otherState, {
      type: 'select',
      id: other.handler.symbolId,
    });
    expect(wholeHandler.flowRoute).toBeNull();
    expect(activeFlow(adapted, wholeHandler)).toBe(actual);
    expect(actual.terminals.size).toBe(70);
    const authFlow = [...flowIndex(adapted).entries.values()].find((flow) =>
      [...flow.edges].some((id) => id.startsWith('context:')),
    )!;
    expect(authFlow).toBeDefined();
    for (const edge of adapted.edges.filter(
      (edge) => authFlow.edges.has(edge.id) && edge.id.startsWith('context:'),
    ))
      expect(edge.kind).toBe('context');
    const otherHandler = graph.nodes.get('sym_get_thread')!;
    expect(
      flowIndex(graph)
        .entries.get('sym_create_run')!
        .paths.has(otherHandler.id),
    ).toBe(false);
  });
  it('retains named parents with children, excludes propagated wrappers and never infers data from unknown effects', () => {
    const fixture = structuredClone(document),
      route = fixture.routes[0];
    fixture.routes = [route];
    route.authChain = [];
    const make = (id: string, effect: string, children: Call[] = []): Call => ({
      id,
      order: 1,
      depth: 1,
      calleeName: 'same_name',
      qualifiedName: 'same_name',
      resolution: 'external',
      touchesPersistence: effect,
      expanded: 'no',
      callSite: route.handler.range,
      children,
    });
    route.callGraph = [
      make('wrapper', 'write', [
        make('named-parent', 'unknown', [make('leaf', 'read')]),
      ]),
      make('unknown', 'unknown'),
    ];
    route.dataAccesses = [
      {
        ...document.routes.flatMap((r) => r.dataAccesses)[0],
        callId: 'named-parent',
      },
    ];
    const actual = flowIndex(adaptGraph(fixture)).entries.get(
      route.handler.symbolId,
    )!;
    expect(
      [...actual.terminals].map((id) => JSON.parse(id.slice(5))[2]).sort(),
    ).toEqual(['leaf', 'named-parent']);
    expect([...actual.paths].some((id) => id.includes('unknown'))).toBe(false);
    for (const candidate of document.routes.filter(
      (r) =>
        r.pathTemplate === '/health' ||
        (r.httpMethod === 'POST' && r.pathTemplate === '/assistants'),
    )) {
      const flow = flowIndex(graph).entries.get(candidate.handler.symbolId)!;
      expect(flow.terminals.size).toBe(
        candidate.pathTemplate === '/health' ? 1 : 0,
      );
    }
  });
});

describe('automatic, manual and mode visibility', () => {
  it('one-click and search reveal a full flow, preserve manual work and keep context through inspection and exact Back', () => {
    let state = navigate(graph, initialNavigation(), {
      type: 'toggle',
      id: 'sym_get_thread',
    });
    const manual = new Set(state.expanded);
    state = navigate(graph, state, { type: 'select', id: 'sym_create_run' });
    expect(state.flowEntry).toBe('sym_create_run');
    for (const id of oracle(
      document.routes.find((r) => r.handler.symbolId === 'sym_create_run')!,
    ).paths)
      expect(navigationVisibleIds(graph, state).has(id)).toBe(true);
    expect(branchDepth(graph, state)).toBe('mixed');
    const intermediate = [
      ...flowIndex(graph).entries.get(state.flowEntry!)!.paths,
    ].find(
      (id) =>
        !graph.nodes.get(id)!.canonical && graph.nodes.get(id)!.children.length,
    )!;
    state = navigate(graph, state, { type: 'select', id: intermediate });
    expect(state.flowEntry).toBe('sym_create_run');
    state = navigate(graph, state, {
      type: 'camera',
      camera: { x: 91, y: -47, scale: 1.4 },
    });
    const before = structuredClone(state);
    state = navigate(graph, state, { type: 'reveal', id: 'sym_get_thread' });
    expect(state.flowEntry).toBe('sym_get_thread');
    expect(state.expanded).toEqual(manual);
    expect(navigate(graph, state, { type: 'back' })).toEqual(before);
    state = navigate(graph, before, { type: 'depth', depth: 0 });
    expect(state.flowEntry).toBeNull();
    expect(navigationVisibleIds(graph, state).has(intermediate)).toBe(true);
    expect(branchDepth(graph, state)).toBe(0);
    state = navigate(graph, before, { type: 'clear-flow' });
    expect(state.flowEntry).toBeNull();
    expect(state.selected).toBeNull();
    expect(state.expanded).toEqual(manual);
  });
  it('primary Clear flow preserves overlapping manual calls and owner paths exactly like the top clear action', () => {
    for (const withOwnerPaths of [false, true]) {
      let state = navigate(graph, initialNavigation(), {
        type: 'select',
        id: 'sym_create_run',
      });
      state = navigate(graph, state, { type: 'depth', depth: 1 });
      const manualDetails = [...navigationVisibleIds(graph, state)].filter(
        (id) =>
          !graph.nodes.get(id)!.canonical &&
          graph.nodes.get(id)!.kind !== 'group',
      );
      expect(manualDetails).toHaveLength(10);
      if (withOwnerPaths)
        state = navigate(graph, state, {
          type: 'accesses',
          id: 'sym_create_run',
        });
      const saved = structuredClone(state),
        savedVisible = navigationVisibleIds(graph, saved);
      state = navigate(graph, state, { type: 'select', id: 'sym_create_run' });
      state = navigate(graph, state, { type: 'view', view: 'data' });
      const primary = primaryNodeAction(graph, state, 'sym_create_run');
      expect(primary.label).toBe('Clear flow');
      const cleared = navigate(graph, state, primary.action);
      expect(cleared.expanded).toEqual(saved.expanded);
      expect(cleared.revealed).toEqual(saved.revealed);
      expect(cleared).toEqual(navigate(graph, state, { type: 'clear-flow' }));
      expect(navigate(graph, cleared, { type: 'back' })).toEqual(state);
      const code = navigate(graph, cleared, { type: 'view', view: 'code' });
      expect(navigationVisibleIds(graph, code)).toEqual(savedVisible);
      // Explicit collapse still removes the selected branch's manual detail.
      const collapse = primaryNodeAction(graph, code, 'sym_create_run');
      expect(collapse.label).toBe('Collapse calls');
      expect(
        navigate(graph, code, collapse.action).expanded.has('sym_create_run'),
      ).toBe(false);
    }
  });
  it('mode-only details come and go independently and Files preserves all saved layers', () => {
    let state = navigate(graph, initialNavigation(), {
      type: 'view',
      view: 'data',
    });
    const details = [...navigationVisibleIds(graph, state)].filter(
      (id) =>
        !graph.nodes.get(id)!.canonical &&
        graph.nodes.get(id)!.kind !== 'group',
    );
    expect(details).toHaveLength(182);
    expect(state.revealed.size).toBe(0);
    expect(state.expanded.size).toBe(0);
    const opened = navigate(graph, state, {
      type: 'toggle',
      id: 'sym_get_thread',
    });
    expect(opened.expanded.has('sym_get_thread')).toBe(true);
    const closed = navigate(graph, opened, {
      type: 'toggle',
      id: 'sym_get_thread',
    });
    expect(closed.expanded.has('sym_get_thread')).toBe(false);
    expect(navigationVisibleIds(graph, closed)).toEqual(
      navigationVisibleIds(graph, state),
    );
    expect(branchDepth(graph, closed)).toBe('mixed');
    state = navigate(graph, state, { type: 'select', id: 'sym_create_run' });
    const selected = structuredClone(state);
    state = navigate(graph, state, { type: 'resolution', resolution: 'files' });
    expect(navigationVisibleIds(graph, state).size).toBe(43);
    state = navigate(graph, state, {
      type: 'resolution',
      resolution: 'functions',
    });
    expect(navigationVisibleIds(graph, state)).toEqual(
      navigationVisibleIds(graph, selected),
    );
    state = navigate(graph, state, { type: 'view', view: 'code' });
    expect(
      [...navigationVisibleIds(graph, state)].filter(
        (id) =>
          !graph.nodes.get(id)!.canonical &&
          graph.nodes.get(id)!.kind !== 'group',
      ),
    ).toHaveLength(42);
    state = navigate(graph, state, { type: 'select', id: null });
    expect(navigationVisibleIds(graph, state).size).toBe(256);
  });
});

describe('semantic view geometry', () => {
  it('moves identities across views, restores exact Code anchors and keeps flow bands ordered without glyph overlap', () => {
    const layout = layoutGraph(graph),
      anchors = new ViewAnchors(graph, layout);
    let state = navigate(graph, initialNavigation(), {
      type: 'select',
      id: 'sym_create_run',
    });
    const visible = navigationVisibleIds(graph, state),
      code = anchors.ensure('code', visible);
    const entries = anchors.ensure('entries', visible),
      data = anchors.ensure('data', visible);
    for (const id of graph.baseIds) {
      expect(entries.get(id)).not.toEqual(code.get(id));
      expect(data.get(id)).not.toEqual(code.get(id));
    }
    expect(anchors.ensure('code', visible)).toEqual(code);
    for (const positions of [entries, data])
      for (const id of visible) {
        if (graph.nodes.get(id)!.kind !== 'group')
          expect(positions.get(id)!.y).toBeLessThanOrEqual(250);
      }
    const flow = flowIndex(graph).entries.get('sym_create_run')!;
    const entrance = data.get('sym_create_run')!;
    const minTerminal = Math.min(
      ...[...flow.terminals].map((id) => data.get(id)!.x),
    );
    for (const id of flow.paths) {
      const node = graph.nodes.get(id)!;
      if (!node.canonical && !flow.terminals.has(id)) {
        expect(data.get(id)!.x).toBeGreaterThan(entrance.x);
        expect(data.get(id)!.x).toBeLessThan(minTerminal);
      }
    }
    state = navigate(graph, state, { type: 'view', view: 'data' });
    const full = navigationVisibleIds(graph, state),
      expanded = anchors.ensure('data', full);
    for (const [id, point] of data) expect(expanded.get(id)).toEqual(point);
    const points = [...full]
      .filter((id) => graph.nodes.get(id)!.kind !== 'group')
      .map((id) => expanded.get(id)!);
    for (let i = 0; i < points.length; i++)
      for (let j = i + 1; j < points.length; j++)
        expect(
          Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y),
        ).toBeGreaterThanOrEqual(34);
  });
});
