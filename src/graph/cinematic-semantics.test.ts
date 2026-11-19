import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import { adaptGraph } from './adapter';
import { cosmicGraph } from './cinematic';
import { filterCosmic } from './cinematic-controls';
import { focusVisibility, recordedFocus, semanticIndex } from './cinematic-semantics';
import type { AtlasGraph, GraphDocument } from './types';

const graph = adaptGraph(raw as GraphDocument);
function byName(name: string) { return graph.baseIds.find(id => graph.nodes.get(id)!.name === name)!; }
function oracleBranch(g: AtlasGraph, id: string) {
  const ids = new Set<string>();
  function children(key: string) {
    ids.add(key);
    g.nodes.get(key)!.children.forEach(children);
  }
  children(id);
  let p = g.nodes.get(id)!.parent;
  while (p) { ids.add(p); p = g.nodes.get(p)!.parent; }
  return ids;
}

describe('semantic roles and exact recorded focus', () => {
  it('separates evidence roles without promoting external libraries to services', () => {
    const roles = semanticIndex(graph).roles;
    const counts = [...roles.values()].reduce((result, role) => ({ ...result, [role]: (result[role] || 0) + 1 }), {} as Record<string, number>);
    expect(counts.entry).toBe(59);
    expect(counts.read).toBe(254);
    expect(counts.write).toBe(243);
    expect(counts.service || 0).toBe(0);
    for (const node of graph.nodes.values()) {
      if (node.call?.resolution === 'external' && node.call.touchesPersistence === 'none') expect(roles.get(node.id)).toBe('external');
      if (node.canonical && !node.groupedRoutes?.length) expect(roles.get(node.id)).toBe('core');
    }
  });

  it('retains exact data paths and a truthful fallback for entries without terminals', () => {
    const run = recordedFocus(graph, byName('create_run'));
    expect(run.paths.size).toBe(43);
    expect(run.terminals.size).toBe(34);
    const health = graph.document.routes.find(route => route.pathTemplate === '/health' && route.httpMethod === 'GET')!;
    expect(recordedFocus(graph, health.handler.symbolId).paths.size).toBe(2);
    const empty = recordedFocus(graph, byName('create_assistant'));
    expect(empty.kind).toBe('recorded-tree');
    expect(empty.paths).toEqual(oracleBranch(graph, byName('create_assistant')));
    expect(empty.paths.size).toBe(27);
    expect(empty.terminals.size).toBe(0);
    for (const edge of graph.edges.filter(edge => run.edges.has(edge.id))) expect(edge.aggregated).not.toBe(true);
  });

  it('traces occurrence ancestry/descendants without siblings or cross-route shortcuts', () => {
    const occurrence = [...graph.nodes.values()].find(node => node.call && node.children.length > 3)!;
    const focus = recordedFocus(graph, occurrence.id);
    expect(focus.paths).toEqual(oracleBranch(graph, occurrence.id));
    for (const edge of graph.edges.filter(edge => focus.edges.has(edge.id))) {
      expect(edge.aggregated).not.toBe(true);
      expect(focus.paths.has(edge.from)).toBe(true);
      expect(focus.paths.has(edge.to) || (edge.kind === 'definition' && focus.definitions.has(edge.to))).toBe(true);
    }
    const auth = [...graph.nodes.values()].find(node => node.kind === 'auth')!;
    expect(recordedFocus(graph, auth.id).paths).toEqual(oracleBranch(graph, auth.id));
  });

  it('unions only recorded contexts for shared symbols and explains untraced classes', () => {
    const index = semanticIndex(graph);
    const id = graph.baseIds.find(id => !graph.nodes.get(id)!.groupedRoutes?.length && (index.contexts.get(id)?.length || 0) > 2)!;
    const expected = new Set([id]);
    const occurrences = [...graph.nodes.values()].filter(node => !node.canonical && node.symbol?.id === id && (node.kind === 'auth' || node.call?.resolution === 'resolved'));
    occurrences.forEach(node => oracleBranch(graph, node.id).forEach(key => expected.add(key)));
    const focus = recordedFocus(graph, id);
    expect(focus.paths).toEqual(expected);
    expect(focus.contexts).toBe(occurrences.length);
    const missing = graph.baseIds.filter(key => !graph.nodes.get(key)!.groupedRoutes?.length && !index.contexts.has(key));
    expect(missing).toHaveLength(22);
    expect(recordedFocus(graph, missing[0])).toMatchObject({ kind: 'untraced', contexts: 0 });
    expect(recordedFocus(graph, missing[0]).paths).toEqual(new Set([missing[0]]));
  });

  it('expands an ancestor context even when a deeper recursive context was indexed first', () => {
    const symbol = [...graph.nodes.values()].find(n => n.canonical && !n.groupedRoutes?.length && n.symbol)!;
    const call = [...graph.nodes.values()].find(n => n.call?.resolution === 'resolved')!;
    const entry = graph.nodes.get(byName('create_run'))!;
    const occurrence = (id: string, parent: string, children: string[], matching: boolean) => ({
      ...call, id, parent, children, symbol: matching ? symbol.symbol : undefined,
      call: { ...call.call!, touchesPersistence: 'none' }, accesses: [],
    });
    const fixture: AtlasGraph = { ...graph, baseIds: ['entry', symbol.id], edges: [], nodes: new Map([
      ['inner', occurrence('inner', 'outer', ['leaf'], true)],
      ['outer', occurrence('outer', 'entry', ['inner', 'sibling'], true)],
      ['leaf', occurrence('leaf', 'inner', [], false)],
      ['sibling', occurrence('sibling', 'outer', [], false)],
      ['entry', { ...entry, id: 'entry', children: ['outer'] }],
      [symbol.id, { ...symbol, children: [] }],
    ]) };
    const focus = recordedFocus(fixture, symbol.id);
    expect(focus.contexts).toBe(2);
    expect(focus.paths).toEqual(new Set([symbol.id, 'entry', 'outer', 'inner', 'leaf', 'sibling']));
  });

  it('temporarily reveals exact focus outside filters and restores the untouched base', () => {
    const cosmic = cosmicGraph(graph);
    const base = filterCosmic(cosmic, { resolution: 'symbols', group: '', query: 'create_run' });
    const before = [...base.nodes];
    const focus = recordedFocus(graph, byName('create_run'));
    const visible = focusVisibility(cosmic, base, focus);
    for (const id of [...focus.paths, ...focus.definitions]) expect(visible.nodes.has(cosmic.index.get(id)!)).toBe(true);
    expect([...base.nodes]).toEqual(before);
    expect(focusVisibility(cosmic, base, null)).toBe(base);
    for (const i of visible.edges) {
      expect(visible.nodes.has(cosmic.index.get(cosmic.edges[i].from)!)).toBe(true);
      expect(visible.nodes.has(cosmic.index.get(cosmic.edges[i].to)!)).toBe(true);
    }
  });

  it('recognizes RPC and read/write evidence in alternate input, including ambiguous targets', () => {
    const document = structuredClone(raw) as GraphDocument;
    const route = document.routes.find(r => r.dataAccesses.length)!;
    document.routes = [route];
    const access = route.dataAccesses[0];
    access.persistenceApi = 'rpc';
    let rpcId = '';
    function change(calls: typeof route.callGraph) {
      for (const call of calls) {
        if (call.id === access.callId) { rpcId = call.id; call.resolution = 'ambiguous'; delete call.symbolId; }
        change(call.children);
      }
    }
    change(route.callGraph); route.authChain.forEach(step => change(step.calls));
    const alternative = adaptGraph(document);
    const node = [...alternative.nodes.values()].find(n => n.call?.id === rpcId)!;
    expect(semanticIndex(alternative).roles.get(node.id)).toBe('service');
    const plain = [...alternative.nodes.values()].find(n => n.call && !n.children.length && !n.accesses.length)!;
    plain.call!.touchesPersistence = 'read_write';
    const second = { ...alternative };
    expect(semanticIndex(second).roles.get(plain.id)).toBe('both');
  });
});
