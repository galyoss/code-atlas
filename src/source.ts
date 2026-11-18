import { repositoryName, scanGraphUrl, type ScanSummary } from './api';
import { sample } from './data';

/** Where the open graph came from. The sample is always labelled as such. */
export type ScanSource =
  { kind: 'sample' } | { kind: 'api'; scan: ScanSummary; projectId?: string };

export function sourceIdentity(source: ScanSource) {
  return source.kind === 'sample'
    ? {
        name: sample.name,
        tag: sample.tag,
        graphUrl: sample.graphUrl,
        download: 'aegra-v0.11.0.graph.json',
      }
    : {
        name: repositoryName(source.scan.repositoryUrl),
        tag: source.scan.revision || 'default branch',
        graphUrl: source.projectId
          ? `/api/projects/${encodeURIComponent(source.projectId)}/graph`
          : scanGraphUrl(source.scan.id),
        download: `${source.scan.id}.graph.json`,
      };
}
