import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import document from '../../docs/scans/aegra-v0.11.0.graph.json';
import provenance from '../../docs/scans/aegra-v0.11.0.provenance.json';
import type { Call, GraphDocument } from './types';
import { adaptGraph, ancestors, callNodeId, routeGraph, routeNodeId, visibleIds } from './adapter';
import { matchingRoutes, overviewGraph, routeGroups } from './catalog';
import { initialCamera, layoutGraph, NODE_HEIGHT, NODE_WIDTH } from './layout';
import { initialNavigation, navigate } from './navigation';

const graph = adaptGraph(document as GraphDocument);
const groups = routeGroups(graph.document);
const calls = (items: Call[]): Call[] => items.flatMap((call) => [call, ...calls(call.children)]);

describe('the unchanged real scan and route discovery', () => {
  it('ships the recorded scan, not the prior two-route example or a rewritten document', () => {
    const bytes = readFileSync(new URL('../../docs/scans/aegra-v0.11.0.graph.json', import.meta.url));
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(provenance.sha256);
    expect(document.illustrative).toBe(false);
    expect(document.repo.revision).toBe(provenance.sourceRevision);
    expect(document.generatedAt).toBe(provenance.generatedAt);
    expect(document.routes).toHaveLength(59);
    expect(document.symbolIndex).toHaveLength(213);
    expect(
      document.routes.reduce(
        (sum, route) =>
          sum +
          calls(route.callGraph).length +
          route.authChain.reduce((sum, step) => sum + calls(step.calls).length, 0),
        0,
      ),
    ).toBe(5586);
    expect(document.routes.filter((r) => Object.values(r.budget.coverage).includes('partial'))).toHaveLength(
      55,
    );
  });
  it('exposes every route exactly once by source and matches literal route fields', () => {
    expect(groups).toHaveLength(9);
    expect(groups.flatMap((g) => g.routes.map((r) => r.id)).sort()).toEqual(
      document.routes.map((r) => r.id).sort(),
    );
    expect(groups.find((g) => g.file === 'examples/custom_routes_example.py')!.routes).toHaveLength(3);
    for (const route of graph.document.routes) {
      expect(
        matchingRoutes(groups, route.handler.qualifiedName)
          .flatMap((g) => g.routes)
          .some((r) => r.id === route.id),
      ).toBe(true);
      expect(routeGraph(graph, routeNodeId(route.id)).defaultId).toBe(routeNodeId(route.id));
    }
    expect(
      matchingRoutes(groups, 'libs/aegra-api/src/aegra_api/api/runs.py create_run')
        .flatMap((g) => g.routes)
        .map((r) => r.handler.qualifiedName.split('.').at(-1)),
    ).toEqual(['create_run']);
    expect(matchingRoutes(groups, 'no_such_route_zzz')).toEqual([]);
  });
  it('labels source containment separately from recorded calls and keeps example code visible', () => {
    const overview = overviewGraph(graph, 'Aegra');
    expect(overview.nodes.size).toBe(10);
    expect(overview.edges).toHaveLength(9);
    expect(overview.edges.every((e) => e.kind === 'contains')).toBe(true);
    expect(overview.nodes.get('source:examples/custom_routes_example.py')?.subtitle).toBe(
      '3 routes · example code',
    );
    expect(
      [...overview.nodes.values()].filter((n) => n.kind === 'group').flatMap((n) => n.groupedRoutes || []),
    ).toHaveLength(59);
  });
});

describe('real route exploration', () => {
  it('preserves source ranges, snippets, occurrence identity and all handler calls for every route', () => {
    for (const route of graph.document.routes) {
      const scoped = routeGraph(graph, routeNodeId(route.id));
      expect(scoped.nodes.get(scoped.defaultId)?.range).toEqual(route.handler.range);
      expect(scoped.nodes.get(scoped.defaultId)?.children).toHaveLength(route.callGraph.length);
      for (const call of calls(route.callGraph)) {
        const node = scoped.nodes.get(callNodeId(route.id, call.id))!;
        expect(node.call).toBe(call);
        expect(node.range).toEqual(call.callSite);
        expect(node.call?.snippet).toEqual(call.snippet);
      }
      expect([...scoped.nodes.values()].filter((node) => node.call)).toHaveLength(
        calls(route.callGraph).length,
      );
      expect(scoped.edges.filter((edge) => edge.kind === 'call' || edge.kind === 'unresolved')).toHaveLength(
        calls(route.callGraph).length,
      );
    }
  });
  it('keeps active nodes apart for every expandable real branch, including the 35-call handler', () => {
    let checked = 0;
    expect(Math.max(...graph.document.routes.map((r) => r.callGraph.length))).toBe(35);
    for (const route of graph.document.routes) {
      const scoped = routeGraph(graph, routeNodeId(route.id));
      const positions = layoutGraph(scoped);
      for (const node of scoped.nodes.values()) {
        if (!node.children.length) continue;
        const shown = [...visibleIds(scoped, ancestors(scoped, node.id))];
        for (let i = 0; i < shown.length; i++)
          for (let j = i + 1; j < shown.length; j++) {
            const a = positions.get(shown[i])!,
              b = positions.get(shown[j])!;
            const overlaps = Math.abs(a.x - b.x) < NODE_WIDTH && Math.abs(a.y - b.y) < NODE_HEIGHT;
            if (overlaps) throw new Error(`Overlap in ${route.id}: ${shown[i]} / ${shown[j]}`);
          }
        checked++;
      }
    }
    expect(checked).toBeGreaterThan(500);
  });
  it('restores scope, selection, expansion and exact camera through route switches and Back', () => {
    const first = graph.document.routes.find((r) => r.handler.qualifiedName.endsWith('.create_run'))!;
    const second = graph.document.routes.find((r) => r.handler.qualifiedName.endsWith('.get_thread'))!;
    const firstId = routeNodeId(first.id),
      secondId = routeNodeId(second.id);
    let state = initialNavigation(graph, null);
    state = navigate(graph, state, {
      type: 'select',
      id: `source:${first.handler.range.file}`,
    });
    state = navigate(graph, state, {
      type: 'camera',
      camera: { x: -35.5, y: 88.2, scale: 1.15 },
    });
    const overview = structuredClone(state);
    state = navigate(graph, state, {
      type: 'focus-route',
      id: firstId,
      camera: { x: 10, y: 20, scale: 0.95 },
    });
    state = navigate(graph, state, { type: 'expand', id: firstId });
    expect(first.callGraph).toHaveLength(6);
    expect(second.callGraph).toHaveLength(9);
    state = navigate(graph, state, {
      type: 'camera',
      camera: { x: -236.125, y: 92.875, scale: 1.152 },
    });
    const before = structuredClone(state);
    const expandable = first.callGraph.find((c) => c.children.length)!;
    state = navigate(graph, state, {
      type: 'expand',
      id: callNodeId(first.id, expandable.id),
    });
    expect(state.camera).toEqual(before.camera);
    state = navigate(graph, state, {
      type: 'camera',
      camera: { x: 66, y: 77, scale: 0.6 },
    });
    expect(navigate(graph, state, { type: 'back' })).toEqual(before);
    state = navigate(graph, before, {
      type: 'focus-route',
      id: secondId,
      camera: { x: 0, y: 0, scale: 1 },
    });
    expect(navigate(graph, state, { type: 'back' })).toEqual(before);
    expect(navigate(graph, state, { type: 'overview' })).toEqual(overview);
  });
  it('starts every focused route and the repository root readable at narrow and short sizes', () => {
    const scenes = [
      overviewGraph(graph),
      ...graph.document.routes.map((r) => routeGraph(graph, routeNodeId(r.id))),
    ];
    for (const scene of scenes)
      for (const [width, height] of [
        [390, 450],
        [1280, 300],
      ]) {
        const positions = layoutGraph(scene),
          point = positions.get(scene.defaultId)!;
        const camera = initialCamera(positions, scene, width, height);
        expect(camera.scale).toBeGreaterThanOrEqual(0.95);
        expect(point.x * camera.scale + camera.x).toBeGreaterThanOrEqual(0);
        expect(point.y * camera.scale + camera.y).toBeGreaterThanOrEqual(0);
        expect((point.x + NODE_WIDTH) * camera.scale + camera.x).toBeLessThanOrEqual(width);
        expect((point.y + NODE_HEIGHT) * camera.scale + camera.y).toBeLessThanOrEqual(height);
      }
  });
});
