import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import type { Call, DataAccess, GraphDocument } from './types';
import { adaptGraph, callNodeId, visibleIds } from './adapter';
import {
  branchDepth,
  initialNavigation,
  navigate,
  resolution,
} from './navigation';
import {
  accessSummary,
  dataEffect,
  emphasized,
  semanticDescription,
} from './semantics';
const document = raw as GraphDocument;
const graph = adaptGraph(document);

// Traverse producer records independently, without deriving expected owners from the adapter.
function accessOracle() {
  const owners = new Map<
    string,
    {
      routeId: string;
      callId: string;
      access: DataAccess;
      authStepId?: string;
    }[]
  >();
  for (const route of document.routes) {
    function visit(calls: Call[], parent?: string, authStepId?: string) {
      for (const call of calls) {
        for (const access of route.dataAccesses.filter(
          (a) => a.callId === call.id,
        )) {
          if (parent)
            owners.set(parent, [
              ...(owners.get(parent) || []),
              { routeId: route.id, callId: call.id, access, authStepId },
            ]);
        }
        visit(
          call.children,
          call.resolution === 'resolved' ? call.symbolId : undefined,
          authStepId,
        );
      }
    }
    visit(route.callGraph, route.handler.symbolId);
    route.authChain.forEach((step) =>
      visit(step.calls, step.symbolId, step.id),
    );
  }
  return owners;
}

describe('data ownership from recorded evidence', () => {
  it('projects the exact 108 records to 32 immediate owners and preserves every ambiguous occurrence', () => {
    const expected = accessOracle();
    const owners = graph.baseIds
      .map((id) => graph.nodes.get(id)!)
      .filter((n) => n.accesses.length);
    expect(expected.size).toBe(32);
    expect(owners.map((n) => n.id).sort()).toEqual([...expected.keys()].sort());
    let reads = 0,
      writes = 0,
      ambiguous = 0;
    for (const owner of owners) {
      expect(
        owner.accesses.map(({ route, access }) => [route.id, access.id]),
      ).toEqual(
        expected.get(owner.id)!.map((ref) => [ref.routeId, ref.access.id]),
      );
      for (const ref of expected.get(owner.id)!) {
        const node = graph.nodes.get(
          callNodeId(ref.routeId, ref.callId, ref.authStepId),
        )!;
        expect(node.accesses[0].access).toBe(ref.access);
        expect(node.range).toEqual(node.call!.callSite);
        if (node.call!.resolution === 'ambiguous') ambiguous++;
        if (ref.access.operation === 'load' || ref.access.operation === 'query')
          reads++;
        else writes++;
      }
    }
    expect([reads, writes, ambiguous]).toEqual([72, 36, 94]);
    expect(
      graph.nodes
        .get('sym_get_thread')!
        .accesses.map((r) => r.access.operation),
    ).toEqual(['load']);
    expect(
      graph.nodes
        .get('sym_prepare_run')!
        .accesses.filter((r) => r.access.operation === 'load'),
    ).toHaveLength(8);
    expect(
      graph.nodes
        .get('sym_prepare_run')!
        .accesses.filter((r) => r.access.operation === 'create'),
    ).toHaveLength(8);
    expect(
      graph.nodes
        .get('sym_delete_thread')!
        .accesses.every((r) => ['load', 'query'].includes(r.access.operation)),
    ).toBe(true);
  });
  it('does not attribute a known access through an unresolved parent or a same-name symbol', () => {
    const fixture = structuredClone(document);
    fixture.routes = [fixture.routes[0]];
    const route = fixture.routes[0],
      target = fixture.symbolIndex.find(
        (s) => s.id !== route.handler.symbolId,
      )!;
    const access = {
      ...document.routes.flatMap((r) => r.dataAccesses)[0],
      operation: 'load',
      callId: 'leaf',
    };
    const leaf: Call = {
      id: 'leaf',
      order: 2,
      depth: 2,
      calleeName: 'delete_everything',
      qualifiedName: 'x.delete_everything',
      resolution: 'ambiguous',
      touchesPersistence: 'unknown',
      expanded: 'no',
      callSite: target.range,
      children: [],
    };
    route.authChain = [];
    route.dataAccesses = [access];
    route.callGraph = [
      {
        ...leaf,
        id: 'parent',
        symbolId: target.id,
        calleeName: target.name,
        children: [leaf],
      },
    ];
    const adapted = adaptGraph(fixture);
    expect(
      adapted.baseIds.flatMap((id) => adapted.nodes.get(id)!.accesses),
    ).toEqual([]);
    const occurrence = adapted.nodes.get(callNodeId(route.id, 'leaf'))!;
    expect(occurrence.accesses[0].access).toBe(access);
    expect(dataEffect(occurrence)).toBe('read');
    expect(occurrence.call!.resolution).toBe('ambiguous');
    expect(adapted.nodes.get(target.id)!.accesses).toEqual([]);
  });
});

describe('semantic presentation', () => {
  it('distinguishes read-only names, unknown effects and explicit call effects from object accesses', () => {
    const readOnly = graph.nodes.get('sym_delete_thread')!;
    expect(accessSummary(readOnly).write).toBe(0);
    expect(dataEffect(readOnly)).toBe('read');
    expect(dataEffect(graph.nodes.get('sym_prepare_run')!)).toBe('both');
    const commit = [...graph.nodes.values()].find(
      (node) =>
        node.call?.touchesPersistence === 'write' && !node.accesses.length,
    )!;
    const unknown = {
      ...commit,
      name: 'delete_everything',
      call: { ...commit.call!, touchesPersistence: 'unknown' },
    };
    expect(dataEffect(unknown)).toBeNull();
    expect(dataEffect(commit)).toBe('write');
    expect(emphasized(commit, 'data')).toBe(false);
    expect(semanticDescription(commit)).toContain(
      'no named object access recorded',
    );
  });
  it('emphasizes exact handler and owner sets, with all route methods and paths exposed', () => {
    const entries = graph.baseIds.filter((id) =>
      emphasized(graph.nodes.get(id)!, 'entries'),
    );
    expect(entries.sort()).toEqual(
      [
        ...new Set(document.routes.map((route) => route.handler.symbolId)),
      ].sort(),
    );
    const owners = graph.baseIds.filter((id) =>
      emphasized(graph.nodes.get(id)!, 'data'),
    );
    expect(owners.sort()).toEqual([...accessOracle().keys()].sort());
    for (const route of document.routes)
      expect(
        semanticDescription(graph.nodes.get(route.handler.symbolId)!),
      ).toContain(`${route.httpMethod} ${route.pathTemplate}`);
    const multi = structuredClone(document);
    multi.routes.push({
      ...multi.routes[0],
      id: 'additional-route',
      httpMethod: 'HEAD',
      pathTemplate: '/another-path',
    });
    const node = adaptGraph(multi).nodes.get(multi.routes[0].handler.symbolId)!;
    expect(semanticDescription(node)).toContain(
      `${multi.routes[0].httpMethod} ${multi.routes[0].pathTemplate}`,
    );
    expect(semanticDescription(node)).toContain('HEAD /another-path');
  });
});

describe('same-canvas controls', () => {
  it('changes only a selected branch and restores resolution, view, rail, camera and expansions exactly', () => {
    const first = 'sym_create_run',
      second = 'sym_get_thread';
    let state = navigate(graph, initialNavigation(), {
      type: 'toggle',
      id: second,
    });
    state = navigate(graph, state, { type: 'select', id: first });
    state = navigate(graph, state, { type: 'depth', depth: 2 });
    expect(state.expanded.has(first)).toBe(true);
    expect(state.expanded.has(second)).toBe(true);
    const firstChild = graph.nodes
      .get(first)!
      .children.find((id) => graph.nodes.get(id)!.children.length)!;
    expect(state.expanded.has(firstChild)).toBe(true);
    expect(branchDepth(graph, state)).toBe(2);
    const mixed = navigate(graph, state, { type: 'toggle', id: firstChild });
    const reselected = navigate(graph, mixed, { type: 'select', id: first });
    expect(branchDepth(graph, reselected)).toBe('mixed');
    state = navigate(graph, state, {
      type: 'camera',
      camera: { x: 67, y: -119, scale: 1.1 },
    });
    const before = structuredClone(state);
    for (const action of [
      { type: 'view', view: 'data' },
      { type: 'rail', open: false },
      { type: 'resolution', resolution: 'files' },
    ] as const)
      state = navigate(graph, state, action);
    expect(state.collapsed.size).toBe(43);
    expect(resolution(graph, state)).toBe('files');
    const reopened = navigate(graph, state, {
      type: 'resolution',
      resolution: 'functions',
    });
    expect(reopened.expanded).toEqual(before.expanded);
    expect(
      visibleIds(
        graph,
        reopened.expanded,
        reopened.collapsed,
        reopened.revealed,
      ).has(firstChild),
    ).toBe(true);
    expect(
      resolution(
        graph,
        navigate(graph, state, { type: 'toggle', id: graph.groups[0].id }),
      ),
    ).toBe('mixed');
    expect(state.expanded).toEqual(before.expanded);
    expect(
      visibleIds(graph, state.expanded, state.collapsed, state.revealed).has(
        state.selected!,
      ),
    ).toBe(true);
    for (let i = 0; i < 3; i++)
      state = navigate(graph, state, { type: 'back' });
    expect(state).toEqual(before);
    state = navigate(graph, state, { type: 'depth', depth: 0 });
    expect(state.expanded.has(first)).toBe(false);
    expect(state.expanded.has(second)).toBe(true);
  });
  it('reveals recorded access ancestors without creating shortcut edges or merging occurrences', () => {
    const edges = graph.edges.map((e) => e.id);
    const before = initialNavigation();
    const state = navigate(graph, before, {
      type: 'accesses',
      id: 'sym_prepare_run',
    });
    const visible = visibleIds(
      graph,
      state.expanded,
      state.collapsed,
      state.revealed,
    );
    const refs = accessOracle().get('sym_prepare_run')!;
    expect(refs).toHaveLength(16);
    const expectedPaths = new Set<string>();
    for (const ref of refs) {
      let id: string | undefined = callNodeId(
        ref.routeId,
        ref.callId,
        ref.authStepId,
      );
      while (id) {
        expectedPaths.add(id);
        expect(visible.has(id)).toBe(true);
        id = graph.nodes.get(id)!.parent;
      }
    }
    expect(
      [...visible]
        .filter(
          (id) =>
            !graph.nodes.get(id)!.canonical &&
            graph.nodes.get(id)!.kind !== 'group',
        )
        .sort(),
    ).toEqual(
      [...expectedPaths].filter((id) => !graph.nodes.get(id)!.canonical).sort(),
    );
    expect(state.expanded).toEqual(before.expanded);
    expect(state.camera).toEqual(before.camera);
    expect(graph.edges.map((e) => e.id)).toEqual(edges);
    expect(navigate(graph, state, { type: 'back' })).toEqual(before);
    let files = navigate(graph, state, {
      type: 'resolution',
      resolution: 'files',
    });
    expect(
      visibleIds(graph, files.expanded, files.collapsed, files.revealed).size,
    ).toBe(43);
    files = navigate(graph, files, {
      type: 'resolution',
      resolution: 'functions',
    });
    expect(
      visibleIds(graph, files.expanded, files.collapsed, files.revealed),
    ).toEqual(visible);
    const root = document.routes.find((route) => route.id === refs[0].routeId)!
      .handler.symbolId;
    const selected = navigate(graph, state, { type: 'select', id: root });
    expect(branchDepth(graph, selected)).toBe('mixed');
    const closed = navigate(graph, selected, { type: 'depth', depth: 0 });
    expect(branchDepth(graph, closed)).toBe(0);
    const after = visibleIds(
      graph,
      closed.expanded,
      closed.collapsed,
      closed.revealed,
    );
    for (const ref of refs)
      expect(
        after.has(callNodeId(ref.routeId, ref.callId, ref.authStepId)),
      ).toBe(ref.routeId !== refs[0].routeId);
    expect(navigate(graph, closed, { type: 'back' })).toEqual(selected);
    const toggled = navigate(graph, state, { type: 'toggle', id: root });
    expect(
      visibleIds(graph, toggled.expanded, toggled.collapsed, toggled.revealed),
    ).toEqual(after);
  });
});
