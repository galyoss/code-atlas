import type { Snippet } from './graph/types';

/** Scan API shapes. The service's JSON stays authoritative. */
export type ScanStatus =
  'queued' | 'running' | 'partial' | 'completed' | 'failed';
export interface Vote {
  id: string;
  check: string;
  routeId: string;
  role: 'hunter' | 'skeptic';
  verdict: 'present' | 'absent' | 'inconclusive';
  reason: string;
  dataAccessId?: string;
}
export interface Finding {
  id: string;
  check: string;
  routeId: string;
  agreementThreshold: number;
  presentCount: number;
  voteIds: string[];
  dataAccessId?: string;
  evidence?: Snippet;
  /** Route-wide coverage; a finding on a partial route rests on its fully recorded cited path. */
  routeCoverage?: Record<'authChain' | 'callGraph' | 'dataFlow', string>;
}
export interface ScanSummary {
  id: string;
  createdAt: string | null;
  status: ScanStatus;
  progress: string;
  error: string | null;
  repositoryUrl: string;
  revision: string | null;
  resolvedRevision: string;
  model: string;
  agentCount: number;
  agreementThreshold: number;
  votes: Vote[];
  findings: Finding[];
  hasGraph: boolean;
  hasFiles?: boolean;
  inProgress: boolean;
  reviewing: boolean;
}
/** Tracked paths of the scanned checkout, recorded before it is deleted. */
export interface FileManifest {
  paths: string[];
  total: number;
  truncated: boolean;
}
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** owner/name from a GitHub URL, for compact headers and lists. */
export function repositoryName(url: string) {
  const match = /github\.com\/([^/]+)\/([^/#?]+?)(?:\.git)?\/?$/.exec(url);
  return match ? `${match[1]}/${match[2]}` : url;
}
