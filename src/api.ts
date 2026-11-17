import type { GraphDocument, Snippet } from './graph/types';

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
export interface ScanRequest {
  repositoryUrl: string;
  revision?: string;
  model: string;
  agentCount: number;
  agreementThreshold: number;
}
export interface ReviewStatus {
  configured: boolean;
  detail: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

const base = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(base + path, init);
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error;
    throw new ApiError(
      'The scan service is not reachable. Start it with `scan-api` and try again.',
      0,
    );
  }
  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    // A proxy error page is not JSON; the status below explains it.
  }
  if (!response.ok) {
    const message =
      body && typeof body === 'object' && 'error' in body
        ? String((body as { error: unknown }).error)
        : response.status >= 500 && !body
          ? 'The scan service is not reachable. Start it with `scan-api` and try again.'
          : `The scan service returned HTTP ${response.status}.`;
    throw new ApiError(message, response.status);
  }
  return body as T;
}

export const listScans = (signal?: AbortSignal) =>
  request<{ scans: ScanSummary[] }>('/scans', { signal }).then(
    (body) => body.scans,
  );
export const scanSummary = (id: string, signal?: AbortSignal) =>
  request<ScanSummary>(`/scans/${encodeURIComponent(id)}/summary`, { signal });
export const scanGraph = (id: string, signal?: AbortSignal) =>
  request<GraphDocument>(`/scans/${encodeURIComponent(id)}/graph`, { signal });
export const scanFiles = (id: string, signal?: AbortSignal) =>
  request<FileManifest>(`/scans/${encodeURIComponent(id)}/files`, { signal });
export const scanGraphUrl = (id: string) =>
  `${base}/scans/${encodeURIComponent(id)}/graph`;
export const reviewStatus = (signal?: AbortSignal) =>
  request<ReviewStatus>('/review', { signal });
/** A failed configuration returns a body with error and, for setup failures, details. */
export const createScan = (scan: ScanRequest) =>
  request<ScanSummary>('/scans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(scan),
  });

/** owner/name from a GitHub URL, for compact headers and lists. */
export function repositoryName(url: string) {
  const match = /github\.com\/([^/]+)\/([^/#?]+?)(?:\.git)?\/?$/.exec(url);
  return match ? `${match[1]}/${match[2]}` : url;
}
