import { describe, expect, it } from 'vitest';
import { datasets } from '../data';
import { adaptGraph, callNodeId, routeNodeId, visibleIds } from './adapter';
import { layoutGraph, zoomCamera } from './layout';
import { initialNavigation, navigate } from './navigation';

const graph = datasets.aegra;
const route = routeNodeId('route_post_thread_runs');
const call = (id: string) => callNodeId('route_post_thread_runs', id);

describe('authoritative fixture adaptation', () => {
  it('preserves every handler call occurrence while leaving auth internals collapsed', () => {
    for (const [dataset, roots, totals] of [
      [datasets.aegra, [3, 5], [11, 6]],
      [datasets.papertrail, [4, 1], [5, 1]],
    ] as const) {
      dataset.document.routes.forEach((item, index) => {
        expect(dataset.nodes.get(routeNodeId(item.id))!.children).toHaveLength(roots[index]);
        expect(
          [...dataset.nodes.values()].filter((node) => node.route?.id === item.id && node.call),
        ).toHaveLength(totals[index]);
      });
      expect(
        [...dataset.nodes.values()]
          .filter((node) => node.kind === 'auth')
          .every((node) => node.children.length === 0),
      ).toBe(true);
      expect(dataset.edges.filter((edge) => edge.kind === 'call' || edge.kind === 'unresolved')).toHaveLength(
        totals.reduce((a, b) => a + b, 0),
      );
    }
  });
  it('keeps repeated symbols and identical source locations as distinct occurrences', () => {
    const threads = graph.nodes.get(call('call_cr_handle_threads'))!;
    const assistants = graph.nodes.get(call('call_cr_handle_assistants'))!;
    expect(threads.symbol?.id).toBe(assistants.symbol?.id);
    expect(threads.id).not.toBe(assistants.id);
    expect(threads.children).toEqual([call('call_cr_threads_handler')]);
    expect(assistants.children).toEqual([call('call_cr_assistants_handler')]);
    for (const id of [...threads.children, ...assistants.children]) {
      expect(graph.nodes.get(id)).toMatchObject({
        kind: 'gap',
        children: [],
        call: { resolution: 'ambiguous' },
      });
    }
  });
  it('qualifies call IDs by route, even if two route slices reuse an ID', () => {
    const document = structuredClone(datasets.papertrail.document);
    document.routes[1].callGraph[0].id = document.routes[0].callGraph[0].id;
    const adapted = adaptGraph(document);
    const first = adapted.nodes.get(routeNodeId(document.routes[0].id))!.children[0];
    const second = adapted.nodes.get(routeNodeId(document.routes[1].id))!.children[0];
    expect(first).not.toBe(second);
    expect(adapted.nodes.get(first)!.call?.callSite.file).toBe('app/api/runs.py');
    expect(adapted.nodes.get(second)!.call?.callSite.file).toBe('app/api/threads.py');
  });
  it('retains all data-summary accesses and their original source text', () => {
    const summary = graph.nodes.get('model:sym_thread')!;
    expect(summary.accesses).toHaveLength(2);
    expect(summary.accesses.map(({ access }) => access.ownershipEvidence.inPredicate)).toEqual(['no', 'yes']);
    const scalar = graph.nodes.get(call('call_cr_scalar'))!;
    expect(scalar.name).toBe('scalar');
    expect(scalar.accesses[0].access.snippet).toEqual(graph.document.routes[0].dataAccesses[0].snippet);
    expect(graph.nodes.get(route)!.symbol?.range.startLine).toBe(112);
  });
});

describe('local exploration and exact navigation history', () => {
  it('reveals only direct calls, retains ancestors, and never changes fixed positions or camera', () => {
    const positions = layoutGraph(graph);
    const anchors = new Map(positions);
    let state = navigate(graph, initialNavigation(graph), {
      type: 'camera',
      camera: { scale: 1.3, x: -121, y: 87 },
    });
    const camera = state.camera;
    state = navigate(graph, state, { type: 'expand', id: route });
    expect([...visibleIds(graph, state.path)].filter((id) => !graph.baseIds.includes(id))).toEqual(
      graph.nodes.get(route)!.children,
    );
    state = navigate(graph, state, { type: 'expand', id: call('call_cr_prepare') });
    expect(state.path).toEqual([route, call('call_cr_prepare')]);
    expect(visibleIds(graph, state.path).size).toBe(graph.baseIds.length + 3 + 4);
    expect(visibleIds(graph, state.path).has(call('call_cr_handle_threads'))).toBe(false);
    expect(state.camera).toEqual(camera);
    expect(layoutGraph(graph)).toEqual(anchors);
  });
  it('Back restores exact selection, path and camera after deeper panning and zooming', () => {
    let state = navigate(graph, initialNavigation(graph), { type: 'expand', id: route });
    state = navigate(graph, state, { type: 'select', id: call('call_cr_prepare') });
    state = navigate(graph, state, { type: 'camera', camera: { scale: 1.152, x: -235.15, y: 16.125 } });
    const before = structuredClone(state);
    state = navigate(graph, state, { type: 'expand', id: call('call_cr_prepare') });
    state = navigate(graph, state, { type: 'select', id: call('call_cr_add') });
    state = navigate(graph, state, { type: 'camera', camera: { scale: 0.6, x: 93, y: -207 } });
    state = navigate(graph, state, { type: 'back' });
    expect(state).toEqual(before);
  });
  it('switches one deep branch and rejects a stale selection or expansion from exiting nodes', () => {
    let state = navigate(graph, initialNavigation(graph), { type: 'expand', id: route });
    state = navigate(graph, state, { type: 'expand', id: call('call_cr_apply') });
    state = navigate(graph, state, { type: 'expand', id: call('call_cr_handle_threads') });
    state = navigate(graph, state, { type: 'select', id: call('call_cr_threads_handler') });
    expect(navigate(graph, state, { type: 'expand', id: call('call_cr_threads_handler') })).toBe(state);
    state = navigate(graph, state, { type: 'expand', id: call('call_cr_handle_assistants') });
    expect(state.path.at(-1)).toBe(call('call_cr_handle_assistants'));
    expect(visibleIds(graph, state.path).has(call('call_cr_threads_handler'))).toBe(false);
    expect(navigate(graph, state, { type: 'select', id: call('call_cr_threads_handler') })).toBe(state);
    state = navigate(graph, state, { type: 'collapse', id: call('call_cr_apply') });
    expect(state.selected).toBe(call('call_cr_apply'));
    expect(visibleIds(graph, state.path).has(state.selected)).toBe(true);
    expect(state.path).toEqual([route]);
  });
  it('breadcrumbs restore their saved view and a new dataset starts with its own clean state', () => {
    let state = navigate(graph, initialNavigation(graph), {
      type: 'camera',
      camera: { scale: 0.9, x: 77, y: -18 },
    });
    const overview = structuredClone(state);
    state = navigate(graph, state, { type: 'expand', id: route });
    state = navigate(graph, state, { type: 'expand', id: call('call_cr_prepare') });
    expect(navigate(graph, state, { type: 'breadcrumb', depth: 0 })).toEqual(overview);
    const paper = initialNavigation(datasets.papertrail);
    expect(paper.history).toEqual([]);
    expect(paper.path).toEqual([]);
    expect(datasets.papertrail.nodes.get(paper.selected)!.range?.file).toBe('app/api/runs.py');
  });
  it('zoom changes only the camera and preserves the world point under its center', () => {
    const state = navigate(graph, initialNavigation(graph), { type: 'expand', id: route });
    const camera = { scale: 0.8, x: 32, y: -56 };
    const center = { x: 600, y: 300 };
    const nextCamera = zoomCamera(camera, 1.15, center);
    expect((center.x - nextCamera.x) / nextCamera.scale).toBeCloseTo((center.x - camera.x) / camera.scale);
    const next = navigate(graph, state, { type: 'camera', camera: nextCamera });
    expect(next.path).toBe(state.path);
    expect(next.selected).toBe(state.selected);
    expect(next.history).toBe(state.history);
  });
});
