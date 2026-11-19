import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import { adaptGraph } from './adapter';
import { cosmicGraph, edgePoint } from './cinematic';
import type { Call, GraphDocument } from './types';

const document = raw as GraphDocument;

describe('cinematic graph fidelity', () => {
  it('renders every real symbol, auth step and qualified call without inventing connections', () => {
    const graph = adaptGraph(document), scene = cosmicGraph(graph);
    const expected = new Set(document.symbolIndex.map((symbol) => symbol.id));
    let callCount = 0;
    for (const route of document.routes) {
      function visit(calls: Call[], step: string | null) {
        for (const call of calls) {
          expected.add(`call:${JSON.stringify([route.id, step, call.id])}`);
          callCount++;
          visit(call.children, step);
        }
      }
      visit(route.callGraph, null);
      for (const step of route.authChain) {
        expected.add(`auth:${JSON.stringify([route.id, step.id])}`);
        visit(step.calls, step.id);
      }
    }
    expect(callCount).toBe(5586);
    expect(scene.nodes).toHaveLength(5920);
    expect(new Set(scene.nodes.map(({ node }) => node.id))).toEqual(expected);
    expect(scene.edges).toHaveLength(7294);
    expect(scene.edges).toEqual(graph.edges);
    for (const edge of scene.edges) {
      expect(expected.has(edge.from)).toBe(true);
      expect(expected.has(edge.to)).toBe(true);
    }
    expect(scene.nodes.filter(({ node }) => node.canonical)).toHaveLength(213);
  });

  it('produces repeatable finite nonplanar coordinates and curves anchored at their real endpoints', () => {
    const graph = adaptGraph(document), first = cosmicGraph(graph), second = cosmicGraph(graph);
    expect(first.nodes.map((node) => node.position)).toEqual(second.nodes.map((node) => node.position));
    for (const { position } of first.nodes) expect(position.every(Number.isFinite)).toBe(true);
    for (let axis = 0; axis < 3; axis++) {
      const values = first.nodes.map((node) => node.position[axis]);
      expect(Math.max(...values) - Math.min(...values)).toBeGreaterThan(200);
    }
    for (const edge of first.edges.filter((edge) => edge.aggregated)) {
      const a = first.nodes[first.index.get(edge.from)!].position;
      const b = first.nodes[first.index.get(edge.to)!].position;
      expect(edgePoint(a, b, 0, .5)).toEqual(a);
      edgePoint(a, b, 1, .5).forEach((value, i) => expect(value).toBeCloseTo(b[i], 8));
    }
  });

  it('uses the supplied scan, including an unknown repository with one real route', () => {
    const fixture = structuredClone(document);
    fixture.repo.name = 'another-repository';
    fixture.routes = [fixture.routes[0]];
    fixture.routes[0].callGraph = [];
    fixture.routes[0].authChain = [];
    fixture.routes[0].dataAccesses = [];
    fixture.symbolIndex = fixture.symbolIndex.filter((symbol) => symbol.id === fixture.routes[0].handler.symbolId);
    const before = JSON.stringify(fixture);
    const scene = cosmicGraph(adaptGraph(fixture));
    expect(scene.nodes).toHaveLength(1);
    expect(scene.nodes[0].node.id).toBe(fixture.routes[0].handler.symbolId);
    expect(scene.edges).toEqual([]);
    expect(JSON.stringify(fixture)).toBe(before);
  });
});
