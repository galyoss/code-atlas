import { describe, expect, it } from 'vitest';
import raw from '../../docs/scans/aegra-v0.11.0.graph.json';
import type { Finding, Vote } from '../api';
import { adaptGraph } from './adapter';
import { indexFindings, nodeFindingKind } from './findings';
import {
  initialNavigation,
  navigate,
  navigationVisibleIds,
} from './navigation';
import type { GraphDocument } from './types';

const document = raw as GraphDocument;
const graph = adaptGraph(document);
// A route whose cited access carries a source snippet, as a present vote requires.
const route = document.routes.find((candidate) =>
  candidate.dataAccesses.some((access) => access.snippet),
)!;
const access = route.dataAccesses.find((candidate) => candidate.snippet)!;
const other = document.routes.find(
  (candidate) => candidate.id !== route.id && candidate.dataAccesses.length,
)!;

const vote = (
  id: string,
  routeId: string,
  verdict: Vote['verdict'],
  dataAccessId?: string,
): Vote => ({
  id,
  check: 'idor',
  routeId,
  role: Number(id.at(-1)) % 2 ? 'skeptic' : 'hunter',
  verdict,
  reason: `${verdict} reason`,
  ...(dataAccessId ? { dataAccessId } : {}),
});
const votes = [
  vote('v0', route.id, 'present', access.id),
  vote('v1', route.id, 'present', access.id),
  vote('v2', other.id, 'present', other.dataAccesses[0].id),
  vote('v3', other.id, 'absent'),
];
const finding: Finding = {
  id: 'finding_a',
  check: 'idor',
  routeId: route.id,
  agreementThreshold: 2,
  presentCount: 2,
  voteIds: ['v0', 'v1'],
  dataAccessId: access.id,
  evidence: access.snippet,
};

describe('findings on the code graph', () => {
  const index = indexFindings(graph, [finding], votes, 2);

  it('places a finding on its handler and the cited access occurrence', () => {
    const [item] = index.items;
    expect(item.kind).toBe('finding');
    expect(item.handlerId).toBe(route.handler.symbolId);
    expect(item.access?.id).toBe(access.id);
    const occurrence = graph.nodes.get(item.occurrenceId!)!;
    expect(occurrence.accesses.map((entry) => entry.access.id)).toContain(
      access.id,
    );
    expect(occurrence.route?.id).toBe(route.id);
    expect(item.supporting.map((entry) => entry.id)).toEqual(['v0', 'v1']);
    expect(item.votes).toHaveLength(2);
    expect(index.byNode.get(item.handlerId)).toContain(item);
    expect(index.byNode.get(item.occurrenceId!)).toContain(item);
  });

  it('follows only recorded parent links from the handler to the access', () => {
    const { path, occurrenceId, handlerId } = index.items[0];
    expect(path[0]).toBe(handlerId);
    expect(path.at(-1)).toBe(occurrenceId);
    for (let i = 1; i < path.length; i++)
      expect(graph.nodes.get(path[i])!.parent).toBe(path[i - 1]);
  });

  it('keeps present votes below the threshold as distinct candidates', () => {
    expect(index.items.map((item) => item.kind)).toEqual([
      'finding',
      'candidate',
    ]);
    const candidate = index.items[1];
    expect(candidate.route.id).toBe(other.id);
    expect(candidate.presentCount).toBe(1);
    expect(candidate.votes.map((entry) => entry.verdict)).toEqual([
      'present',
      'absent',
    ]);
    expect(nodeFindingKind(index.byNode.get(candidate.handlerId))).toBe(
      other.handler.symbolId === route.handler.symbolId
        ? 'finding'
        : 'candidate',
    );
    expect(index.verdicts).toEqual({ present: 3, absent: 1, inconclusive: 0 });
    expect(index.reviewedRoutes).toBe(2);
    expect(index.inconclusiveReasons).toEqual([]);
    const failed = indexFindings(
      graph,
      [],
      [
        vote('v4', route.id, 'inconclusive'),
        vote('v5', other.id, 'inconclusive'),
      ],
      2,
    );
    expect(failed.inconclusiveReasons).toEqual([['inconclusive reason', 2]]);
  });

  it('does not place votes for routes outside the graph or invent a path', () => {
    const stray = indexFindings(
      graph,
      [{ ...finding, id: 'finding_b', routeId: 'route_missing' }],
      [],
      2,
    );
    expect(stray.items).toEqual([]);
    const uncited = indexFindings(
      graph,
      [{ ...finding, id: 'finding_c', dataAccessId: undefined }],
      [],
      2,
    );
    expect(uncited.items[0].occurrenceId).toBeUndefined();
    expect(uncited.items[0].path).toEqual([route.handler.symbolId]);
  });

  it('shows the whole cited path once the entry flow opens', () => {
    const state = navigate(graph, initialNavigation(), {
      type: 'reveal',
      id: route.handler.symbolId,
    });
    const visible = navigationVisibleIds(graph, state);
    for (const id of index.items[0].path) expect(visible.has(id)).toBe(true);
  });
});
