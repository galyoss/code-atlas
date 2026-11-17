import type { Finding, Vote } from '../api';
import type { AtlasGraph, DataAccess, Route, Snippet } from './types';

export interface FindingItem {
  id: string;
  /** A finding met the scan's agreement threshold; a candidate has present votes below it. */
  kind: 'finding' | 'candidate';
  check: string;
  route: Route;
  handlerId: string;
  access?: DataAccess;
  /** The route-qualified call occurrence that performs the cited access. */
  occurrenceId?: string;
  presentCount: number;
  threshold: number;
  supporting: Vote[];
  /** Every vote on this route and check, including disagreement and failures. */
  votes: Vote[];
  evidence?: Snippet;
  /** True when the finding's route has unresolved calls outside the cited path. */
  partialRoute: boolean;
  /** Recorded ancestry from the handler to the cited access, never inferred. */
  path: string[];
}
export interface FindingIndex {
  items: FindingItem[];
  byNode: Map<string, FindingItem[]>;
  verdicts: Record<Vote['verdict'], number>;
  reviewedRoutes: number;
  /** Most frequent reasons first, so a failed provider explains itself. */
  inconclusiveReasons: [reason: string, count: number][];
}

const checkNames: Record<string, string> = {
  idor: 'Insecure direct object reference',
};
export const checkName = (check: string) =>
  checkNames[check] || check.replaceAll('_', ' ');

export function indexFindings(
  graph: AtlasGraph,
  findings: Finding[],
  votes: Vote[],
  threshold: number,
): FindingIndex {
  const routes = new Map(graph.document.routes.map((r) => [r.id, r]));
  const occurrences = new Map<string, string>();
  for (const node of graph.nodes.values())
    if (!node.canonical)
      for (const { route, access, occurrenceId } of node.accesses)
        occurrences.set(JSON.stringify([route.id, access.id]), occurrenceId);
  const byVote = new Map(votes.map((vote) => [vote.id, vote]));
  const routeVotes = (check: string, routeId: string) =>
    votes.filter((vote) => vote.check === check && vote.routeId === routeId);

  function item(
    id: string,
    kind: FindingItem['kind'],
    check: string,
    routeId: string,
    accessId: string | undefined,
    supporting: Vote[],
    presentCount: number,
    evidence?: Snippet,
    routeCoverage?: Finding['routeCoverage'],
  ): FindingItem | null {
    const route = routes.get(routeId);
    // A vote set that names a route outside this graph cannot be placed on it.
    if (!route) return null;
    const access = accessId
      ? route.dataAccesses.find((candidate) => candidate.id === accessId)
      : undefined;
    const occurrenceId = accessId
      ? occurrences.get(JSON.stringify([routeId, accessId]))
      : undefined;
    const path: string[] = [];
    let node = occurrenceId ? graph.nodes.get(occurrenceId) : undefined;
    while (node) {
      path.unshift(node.id);
      node = node.parent ? graph.nodes.get(node.parent) : undefined;
    }
    if (!path.length) path.push(route.handler.symbolId);
    return {
      id,
      kind,
      check,
      route,
      handlerId: route.handler.symbolId,
      access,
      occurrenceId,
      presentCount,
      threshold,
      supporting,
      votes: routeVotes(check, routeId),
      evidence: evidence || access?.snippet,
      partialRoute: Object.values(routeCoverage || route.budget.coverage).some(
        (axis) => axis !== 'complete',
      ),
      path,
    };
  }

  const items: FindingItem[] = [];
  const covered = new Set<string>();
  for (const finding of findings) {
    const key = JSON.stringify([
      finding.check,
      finding.routeId,
      finding.dataAccessId ?? null,
    ]);
    covered.add(key);
    const supporting = finding.voteIds.flatMap((id) => byVote.get(id) || []);
    const next = item(
      finding.id,
      'finding',
      finding.check,
      finding.routeId,
      finding.dataAccessId,
      supporting,
      finding.presentCount,
      finding.evidence,
      finding.routeCoverage,
    );
    if (next) items.push(next);
  }
  const candidates = new Map<string, Vote[]>();
  for (const vote of votes) {
    if (vote.verdict !== 'present') continue;
    const key = JSON.stringify([
      vote.check,
      vote.routeId,
      vote.dataAccessId ?? null,
    ]);
    if (covered.has(key)) continue;
    candidates.set(key, [...(candidates.get(key) || []), vote]);
  }
  for (const [key, supporting] of candidates) {
    const [check, routeId, accessId] = JSON.parse(key) as [
      string,
      string,
      string | null,
    ];
    const next = item(
      `candidate:${key}`,
      'candidate',
      check,
      routeId,
      accessId ?? undefined,
      supporting,
      supporting.length,
    );
    if (next) items.push(next);
  }
  items.sort(
    (a, b) =>
      Number(a.kind === 'candidate') - Number(b.kind === 'candidate') ||
      b.presentCount - a.presentCount ||
      a.route.pathTemplate.localeCompare(b.route.pathTemplate),
  );
  const byNode = new Map<string, FindingItem[]>();
  for (const finding of items)
    for (const id of new Set([finding.handlerId, finding.occurrenceId]))
      if (id) byNode.set(id, [...(byNode.get(id) || []), finding]);
  const verdicts = { present: 0, absent: 0, inconclusive: 0 };
  const reasons = new Map<string, number>();
  for (const vote of votes) {
    verdicts[vote.verdict]++;
    if (vote.verdict === 'inconclusive')
      reasons.set(vote.reason, (reasons.get(vote.reason) || 0) + 1);
  }
  return {
    items,
    byNode,
    verdicts,
    reviewedRoutes: new Set(votes.map((vote) => vote.routeId)).size,
    inconclusiveReasons: [...reasons].sort((a, b) => b[1] - a[1]).slice(0, 3),
  };
}

/** The strongest status a node carries, for its graph marker. */
export const nodeFindingKind = (items?: FindingItem[]) =>
  items?.some((item) => item.kind === 'finding')
    ? 'finding'
    : items?.length
      ? 'candidate'
      : null;
