import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import provenance from '../../docs/scans/aegra-v0.11.0.provenance.json';
import type { Call, EvidenceRef, GraphDocument } from './types';
import { adaptGraph, callNodeId, visibleEdges, visibleIds } from './adapter';
import { matchingSymbols } from './catalog';
import { DetailAnchors, fitCamera, initialCamera, layoutGraph } from './layout';
import { placeLabels } from './labels';
import { initialNavigation, navigate } from './navigation';
const document = raw as GraphDocument,
  graph = adaptGraph(document);
const flatten = (items: Call[]): Call[] =>
  items.flatMap((call) => [call, ...flatten(call.children)]);
// Independent raw traversal; no adapter IDs, helpers, or expected projection output.
function oracle() {
  const indexed = new Set(document.symbolIndex.map((symbol) => symbol.id));
  const pairs = new Map<string, EvidenceRef[]>();
  for (const route of document.routes) {
    const visit = (items: Call[], parent?: string, authStepId?: string) => {
      for (const call of items) {
        const target =
          call.resolution === 'resolved' && indexed.has(call.symbolId || '')
            ? call.symbolId
            : undefined;
        if (parent && indexed.has(parent) && target) {
          const key = JSON.stringify([parent, target]);
          pairs.set(key, [
            ...(pairs.get(key) || []),
            {
              routeId: route.id,
              callId: call.id,
              ...(authStepId ? { authStepId } : {}),
            },
          ]);
        }
        visit(call.children, target, authStepId);
      }
    };
    visit(route.callGraph, route.handler.symbolId);
    for (const step of route.authChain)
      visit(step.calls, step.symbolId, step.id);
  }
  return pairs;
}
describe('immutable scan and honest canonical projection', () => {
  it('preserves raw bytes, revision, coverage and all 5,586 occurrences', () => {
    const bytes = readFileSync(
      new URL('../../docs/scans/aegra-v0.11.0.graph.json', import.meta.url),
    );
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(
      provenance.sha256,
    );
    expect(document.illustrative).toBe(false);
    expect(document.repo.revision).toBe(provenance.sourceRevision);
    expect(document.routes).toHaveLength(59);
    expect(document.symbolIndex).toHaveLength(213);
    expect(
      document.routes.filter((r) =>
        Object.values(r.budget.coverage).includes('partial'),
      ),
    ).toHaveLength(55);
    expect([...graph.nodes.values()].filter((node) => node.call)).toHaveLength(
      5586,
    );
    for (const route of document.routes) {
      for (const call of flatten(route.callGraph))
        expect(graph.nodes.get(callNodeId(route.id, call.id))?.call).toBe(call);
      for (const step of route.authChain)
        for (const call of flatten(step.calls))
          expect(
            graph.nodes.get(callNodeId(route.id, call.id, step.id))?.call,
          ).toBe(call);
    }
  });
  it('opens every symbol and exact call pair, retaining all original refs including auth trees', () => {
    const expected = oracle(),
      edges = graph.edges.filter((edge) => edge.aggregated);
    expect([...graph.baseIds].sort()).toEqual(
      document.symbolIndex.map((symbol) => symbol.id).sort(),
    );
    expect(expected.size).toBe(244);
    expect(edges).toHaveLength(244);
    expect(graph.groups).toHaveLength(43);
    expect(edges.reduce((total, edge) => total + edge.evidence.length, 0)).toBe(
      1222,
    );
    for (const edge of edges)
      expect(edge.evidence).toEqual(
        expected.get(JSON.stringify([edge.from, edge.to])),
      );
    expect(
      edges.filter(
        (edge) =>
          graph.nodes.get(edge.from)!.range!.file !==
          graph.nodes.get(edge.to)!.range!.file,
      ),
    ).toHaveLength(141);
    for (const route of document.routes)
      expect(graph.baseIds).toContain(route.handler.symbolId);
  });
  it('does not infer targets by common name or jump over unresolved parents', () => {
    const fixture = structuredClone(document);
    const route = fixture.routes[0],
      target = fixture.symbolIndex[1].id;
    route.callGraph = [
      {
        id: 'unresolved',
        order: 1,
        depth: 1,
        calleeName: fixture.symbolIndex[1].name,
        qualifiedName: 'ambiguous',
        resolution: 'ambiguous',
        symbolId: target,
        touchesPersistence: 'none',
        expanded: 'yes',
        callSite: route.handler.range,
        children: [
          {
            id: 'resolved-child',
            order: 2,
            depth: 2,
            calleeName: 'target',
            qualifiedName: 'target',
            resolution: 'resolved',
            symbolId: target,
            touchesPersistence: 'none',
            expanded: 'no',
            callSite: route.handler.range,
            children: [],
          },
        ],
      },
    ];
    const adapted = adaptGraph(fixture);
    expect(
      adapted.edges
        .filter((edge) => edge.aggregated)
        .flatMap((edge) => edge.evidence)
        .some((ref) => ['unresolved', 'resolved-child'].includes(ref.callId)),
    ).toBe(false);
    expect(
      adapted.nodes.get(callNodeId(route.id, 'unresolved'))?.symbol,
    ).toBeUndefined();
    const names = new Map<string, string[]>();
    for (const symbol of document.symbolIndex)
      names.set(symbol.name, [...(names.get(symbol.name) || []), symbol.id]);
    expect([...names.values()].some((ids) => ids.length > 1)).toBe(true);
    for (const ids of names.values())
      for (const id of ids) expect(graph.nodes.get(id)?.symbol?.id).toBe(id);
  });
  it('search highlights original symbols and returns a real empty result', () => {
    expect(matchingSymbols(graph, 'api/runs.py create_run')).toEqual([
      'sym_create_run',
      'sym_apply_create_run_auth',
    ]);
    expect(matchingSymbols(graph, 'no_such_symbol_zzz')).toEqual([]);
    expect(matchingSymbols(graph, '')).toEqual([]);
    for (const route of document.routes)
      expect(matchingSymbols(graph, route.handler.qualifiedName)).toContain(
        route.handler.symbolId,
      );
  });
});
describe('rich fixed network and in-place detail', () => {
  it('fits all 213 code glyphs at desktop size, with no overlapping glyphs', () => {
    const layout = layoutGraph(graph),
      camera = fitCamera(
        layout.positions,
        new Set(layout.positions.keys()),
        1440,
        802,
      );
    let onscreen = 0;
    for (const id of graph.baseIds) {
      const p = layout.positions.get(id)!,
        x = p.x * camera.scale + camera.x,
        y = p.y * camera.scale + camera.y;
      if (x > 10 && x < 1430 && y > 10 && y < 792) onscreen++;
    }
    expect(onscreen).toBe(213);
    expect(camera.scale).toBeGreaterThan(0.5);
    const points = graph.baseIds.map((id) => layout.positions.get(id)!);
    for (let i = 0; i < points.length; i++)
      for (let j = i + 1; j < points.length; j++)
        expect(
          Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y),
        ).toBeGreaterThan(25);
  });
  it('prioritizes revealed call names and gives a fresh phone view usable glyphs', () => {
    const layout = layoutGraph(graph),
      anchors = new DetailAnchors(layout);
    const route = document.routes.find((route) =>
      route.handler.qualifiedName.endsWith('.create_run'),
    )!;
    const prepare = route.callGraph.find(
      (call) => call.calleeName === '_prepare_run',
    )!;
    const id = callNodeId(route.id, prepare.id);
    let state = navigate(graph, initialNavigation(), {
      type: 'toggle',
      id: route.handler.symbolId,
    });
    state = navigate(graph, state, { type: 'toggle', id });
    const visible = visibleIds(graph, state.expanded, state.collapsed);
    const positions = anchors.ensure(graph, visible),
      children = graph.nodes.get(id)!.children;
    const labels = placeLabels(
      graph,
      positions,
      visible,
      [...children, ...graph.baseIds],
      0.88,
      id,
    );
    expect(
      children.filter((child) => labels.has(child)).length,
    ).toBeGreaterThanOrEqual(12);
    const camera = initialCamera(layout, graph, 390, 650),
      point = layout.positions.get(graph.defaultId)!;
    expect(camera.scale).toBe(1);
    expect(point.x * camera.scale + camera.x).toBe(195);
    expect(point.y * camera.scale + camera.y).toBe(325);
  });
  it('opens create_run and _prepare_run alongside another handler without moving prior anchors', () => {
    const first = document.routes.find((route) =>
      route.handler.qualifiedName.endsWith('.create_run'),
    )!;
    const second = document.routes.find((route) =>
      route.handler.qualifiedName.endsWith('.get_thread'),
    )!;
    const layout = layoutGraph(graph),
      anchors = new DetailAnchors(layout);
    let state = navigate(graph, initialNavigation(), {
      type: 'toggle',
      id: first.handler.symbolId,
    });
    const prepare = first.callGraph.find(
      (call) => call.calleeName === '_prepare_run',
    )!;
    anchors.ensure(graph, visibleIds(graph, state.expanded, state.collapsed));
    const before = new Map(anchors.positions);
    state = navigate(graph, state, {
      type: 'toggle',
      id: callNodeId(first.id, prepare.id),
    });
    state = navigate(graph, state, {
      type: 'toggle',
      id: second.handler.symbolId,
    });
    const visible = visibleIds(graph, state.expanded, state.collapsed);
    anchors.ensure(graph, visible);
    for (const [id, point] of before)
      expect(anchors.positions.get(id)).toEqual(point);
    expect(visible.has(callNodeId(first.id, prepare.children[0].id))).toBe(
      true,
    );
    expect(visible.has(callNodeId(second.id, second.callGraph[0].id))).toBe(
      true,
    );
    expect(graph.baseIds.every((id) => visible.has(id))).toBe(true);
    const glyphs = [...visible].filter(
      (id) => graph.nodes.get(id)!.kind !== 'group',
    );
    for (let i = 0; i < glyphs.length; i++)
      for (let j = i + 1; j < glyphs.length; j++) {
        const a = anchors.positions.get(glyphs[i])!,
          b = anchors.positions.get(glyphs[j])!;
        expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(25);
      }
    const group = graph.nodes.get(first.handler.symbolId)!.groupId!;
    state = navigate(graph, state, { type: 'toggle', id: group });
    expect(
      visibleEdges(
        graph,
        visibleIds(graph, state.expanded, state.collapsed),
        state.collapsed,
      ).some((edge) => edge.from === group || edge.to === group),
    ).toBe(true);
    expect(state.selected).toBe(group);
  });
});
