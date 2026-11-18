import { ApiError, type FileManifest, type ScanSummary } from '../api';
import type { GraphDocument } from '../graph/types';

export interface User {
  id: string;
  email: string;
}
export interface Project {
  id: string;
  repositoryUrl: string;
  scan: ScanSummary;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + path, {
    credentials: 'same-origin',
    cache: 'no-store',
    ...init,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body === null) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event('atlas-session-ended'));
    }
    throw new ApiError(
      body?.error ??
        'The workspace service is unavailable. Try again in a moment.',
      response.status,
    );
  }
  return body as T;
}
const json = (payload: object): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
});
const pathFor = (id: string) => '/projects/' + encodeURIComponent(id);
export const session = (signal?: AbortSignal) =>
  request<{ user: User | null }>('/session', { signal });
export const authenticate = (
  mode: 'login' | 'register',
  email: string,
  password: string,
) => request<{ user: User }>('/auth/' + mode, json({ email, password }));
export const signOut = () => request('/auth/logout', json({}));
export const listProjects = (signal: AbortSignal) =>
  request<{ projects: Project[] }>('/projects', { signal }).then(
    (r) => r.projects,
  );
export const newProject = (repositoryUrl: string) =>
  request<{ project: Project }>('/projects', json({ repositoryUrl })).then(
    (r) => r.project,
  );
export const getProject = (id: string, signal: AbortSignal) =>
  request<{ project: Project }>(pathFor(id), { signal }).then((r) => r.project);
export const retryProject = (id: string) =>
  request<{ project: Project }>(pathFor(id) + '/retry', json({})).then(
    (r) => r.project,
  );
export const getGraph = (id: string, signal: AbortSignal) =>
  request<GraphDocument>(pathFor(id) + '/graph', { signal });
export const getFiles = (id: string, signal: AbortSignal) =>
  request<FileManifest>(pathFor(id) + '/files', { signal });
