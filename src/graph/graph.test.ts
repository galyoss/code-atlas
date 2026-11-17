import { describe, expect, it } from 'vitest';
import aegra from '../../docs/code-graph-example-aegra.json';
import papertrail from '../../docs/code-graph-example.json';
import type { Call, GraphDocument } from './types';
import { adaptGraph, callNodeId, visibleIds } from './adapter';
import { DetailAnchors, layoutGraph, zoomCamera } from './layout';
import { initialNavigation, navigate } from './navigation';
const graph = adaptGraph(aegra as GraphDocument);
const route = graph.document.routes[0].handler.symbolId;
const call = (id: string) => callNodeId('route_post_thread_runs', id);
const flatten = (calls: Call[]): Call[] =>
  calls.flatMap((call) => [call, ...flatten(call.children)]);
describe('source and occurrence fidelity', () => {
  it('retains handler and authentication occurrences with exact original evidence', () => {
    for (const document of [aegra, papertrail] as GraphDocument[]) {
      const adapted = adaptGraph(document);
      for (const route of document.routes) {
        for (const item of flatten(route.callGraph))
          expect(adapted.nodes.get(callNodeId(route.id, item.id))?.call).toBe(
            item,
          );
        for (const step of route.authChain)
          for (const item of flatten(step.calls))
            expect(
              adapted.nodes.get(callNodeId(route.id, item.id, step.id))?.call,
            ).toBe(item);
      }
    }
  });
  it('keeps same-symbol occurrences and unresolved children distinct', () => {
    const a = graph.nodes.get(call('call_cr_handle_threads'))!,
      b = graph.nodes.get(call('call_cr_handle_assistants'))!;
    expect(a.symbol?.id).toBe(b.symbol?.id);
    expect(a.id).not.toBe(b.id);
    expect(a.children).toEqual([call('call_cr_threads_handler')]);
    expect(b.children).toEqual([call('call_cr_assistants_handler')]);
    expect(graph.nodes.get(a.children[0])?.kind).toBe('gap');
    const scalar = graph.nodes.get(call('call_cr_scalar'))!;
    expect(scalar.accesses[0].access.snippet).toEqual(
      graph.document.routes[0].dataAccesses[0].snippet,
    );
  });
  it('uses route, auth-step and call ID as a collision-safe tuple', () => {
    expect(callNodeId('a:b', 'c')).not.toBe(callNodeId('a', 'b:c'));
    expect(callNodeId('a', 'c', 'auth')).not.toBe(callNodeId('a', 'c'));
  });
});
describe('persistent exploration state', () => {
  it('keeps two branches open and restores the exact view with Back', () => {
    let state = navigate(graph, initialNavigation(), {
      type: 'toggle',
      id: route,
    });
    state = navigate(graph, state, {
      type: 'toggle',
      id: call('call_cr_prepare'),
    });
    state = navigate(graph, state, {
      type: 'camera',
      camera: { x: -23.5, y: 63.7, scale: 1.23 },
    });
    const before = structuredClone(state);
    state = navigate(graph, state, {
      type: 'toggle',
      id: call('call_cr_apply'),
    });
    expect(state.expanded.has(call('call_cr_prepare'))).toBe(true);
    expect(state.expanded.has(call('call_cr_apply'))).toBe(true);
    expect(state.camera).toEqual(before.camera);
    state = navigate(graph, state, {
      type: 'camera',
      camera: { x: 999, y: -200, scale: 0.7 },
    });
    expect(navigate(graph, state, { type: 'back' })).toEqual(before);
  });
  it('collapses groups in place and prevents stale hidden selections', () => {
    let state = navigate(graph, initialNavigation(), {
      type: 'toggle',
      id: route,
    });
    const group = graph.nodes.get(route)!.groupId!;
    state = navigate(graph, state, { type: 'toggle', id: group });
    expect(state.selected).toBe(group);
    expect(visibleIds(graph, state.expanded, state.collapsed).has(route)).toBe(
      false,
    );
    expect(
      navigate(graph, state, { type: 'select', id: call('call_cr_prepare') }),
    ).toBe(state);
    state = navigate(graph, state, { type: 'toggle', id: group });
    expect(
      visibleIds(graph, state.expanded, state.collapsed).has(
        call('call_cr_prepare'),
      ),
    ).toBe(true);
  });
  it('freezes canonical and previously allocated detail anchors across toggles', () => {
    const layout = layoutGraph(graph),
      anchors = new DetailAnchors(layout);
    let state = navigate(graph, initialNavigation(), {
      type: 'toggle',
      id: route,
    });
    anchors.ensure(graph, visibleIds(graph, state.expanded, state.collapsed));
    const before = new Map(anchors.positions);
    state = navigate(graph, state, {
      type: 'toggle',
      id: call('call_cr_prepare'),
    });
    anchors.ensure(graph, visibleIds(graph, state.expanded, state.collapsed));
    for (const [id, point] of before)
      expect(anchors.positions.get(id)).toEqual(point);
    expect(layoutGraph(graph)).toEqual(layout);
  });
  it('keeps the world point beneath pointer-centered zoom unchanged', () => {
    const camera = { scale: 0.8, x: 32, y: -56 },
      center = { x: 600, y: 300 },
      next = zoomCamera(camera, 1.15, center);
    expect((center.x - next.x) / next.scale).toBeCloseTo(
      (center.x - camera.x) / camera.scale,
    );
    expect((center.y - next.y) / next.scale).toBeCloseTo(
      (center.y - camera.y) / camera.scale,
    );
  });
});
