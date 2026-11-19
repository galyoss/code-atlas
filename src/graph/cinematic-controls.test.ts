import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import { adaptGraph } from './adapter';
import { cosmicGraph } from './cinematic';
import { flowIndex } from './flow';
import type { GraphDocument } from './types';
import { cosmicLayouts, filterCosmic, retargetBuffer, transitionProgress } from './cinematic-controls';

const graph = adaptGraph(raw as GraphDocument);
const cosmic = cosmicGraph(graph);

describe('3D controls preserve scan identity', () => {
  it('intersects resolution, cluster and literal search without forging edges', () => {
    const all = filterCosmic(cosmic, { resolution: 'all', group: '', query: '' });
    expect(all.nodes.size).toBe(5920);
    expect(all.edges.size).toBe(7294);
    const symbols = filterCosmic(cosmic, { resolution: 'symbols', group: '', query: '' });
    expect([...symbols.nodes].map(i => cosmic.nodes[i].node.id)).toEqual(graph.baseIds);
    expect(symbols.edges.size).toBe(244);
    const target = cosmic.nodes.find(({ node }) => node.name === 'create_run')!.node;
    const filter = { resolution: 'all' as const, group: target.groupId!, query: 'create_run' };
    const subset = filterCosmic(cosmic, filter);
    expect(subset.nodes.size).toBeGreaterThan(0);
    expect(subset.nodes.size).toBeLessThan(all.nodes.size);
    for (const i of subset.nodes) {
      const node = cosmic.nodes[i].node;
      expect(node.groupId).toBe(target.groupId);
      expect([node.name, node.subtitle, node.range?.file, node.route?.pathTemplate].join(' ').toLowerCase()).toContain('create_run');
    }
    for (const i of subset.edges) {
      expect(subset.nodes.has(cosmic.index.get(cosmic.edges[i].from)!)).toBe(true);
      expect(subset.nodes.has(cosmic.index.get(cosmic.edges[i].to)!)).toBe(true);
    }
    expect(filterCosmic(cosmic, { ...filter, query: 'no_such_symbol_887711' }).nodes.size).toBe(0);
    expect(filterCosmic(cosmic, { resolution: 'all', group: '', query: '' })).toEqual(all);
  });

  it('keeps stable finite nonplanar layouts and places genuine roles in separate bands', () => {
    const layouts = cosmicLayouts(graph, cosmic);
    const again = cosmicLayouts(graph, cosmic);
    const terminals = flowIndex(graph).terminals;
    expect(layouts).toEqual(again);
    expect(layouts.files).toEqual(cosmic.nodes.map(({ position }) => position));
    for (const positions of Object.values(layouts)) {
      expect(positions).toHaveLength(5920);
      expect(positions.flat().every(Number.isFinite)).toBe(true);
      for (let axis = 0; axis < 3; axis++) expect(new Set(positions.map(p => p[axis])).size).toBeGreaterThan(20);
    }
    cosmic.nodes.forEach(({ node }, i) => {
      if (node.groupedRoutes?.length) {
        expect(layouts.data[i][0]).toBeLessThan(-250);
        expect(layouts.entries[i][0]).toBeLessThan(-200);
      } else if (terminals.has(node.id)) expect(layouts.data[i][0]).toBeGreaterThan(250);
      else expect(Math.abs(layouts.data[i][0])).toBeLessThan(230);
    });
    const before = JSON.stringify(layouts);
    filterCosmic(cosmic, { resolution: 'symbols', group: '', query: 'run' });
    expect(JSON.stringify(layouts)).toBe(before);
  });

  it('retargets at the exact current pose without discontinuity', () => {
    const source = new Float32Array([0, 0, 10, 20, 30, 40]);
    const target = new Float32Array([20, 30, 40, 0, 0, 10]);
    const progress = transitionProgress(370, 900);
    const visiblePose = source.map((v, i) => v + (target[i] - v) * progress);
    retargetBuffer(source, target, progress);
    expect(source).toEqual(visiblePose);
    expect(transitionProgress(0, 900)).toBe(0);
    expect(transitionProgress(900, 900)).toBe(1);
    expect(transitionProgress(2000, 900)).toBe(1);
  });

  it('uses alternate input and schema roles, not repository or symbol names', () => {
    const document = structuredClone(raw) as GraphDocument;
    document.repo.name = 'a-different-scan';
    document.routes = [document.routes[0]];
    document.routes[0].callGraph = [];
    document.routes[0].authChain = [];
    document.routes[0].dataAccesses = [];
    document.symbolIndex = document.symbolIndex.filter(s => s.id === document.routes[0].handler.symbolId);
    const alternative = adaptGraph(document), projected = cosmicGraph(alternative);
    const layouts = cosmicLayouts(alternative, projected);
    expect(projected.nodes).toHaveLength(1);
    expect(layouts.data[0][0]).toBeLessThan(-250);
    expect(filterCosmic(projected, { resolution: 'all', group: '', query: '' }).edges.size).toBe(0);
  });
});
