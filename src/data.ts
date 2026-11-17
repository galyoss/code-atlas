import graphUrl from '../docs/scans/aegra-v0.11.0.graph.json?url';
import provenance from '../docs/scans/aegra-v0.11.0.provenance.json';
import { adaptGraph } from './graph/adapter';
import type { AtlasGraph, GraphDocument } from './graph/types';

/** The bundled scan is a labelled sample. It is never substituted for a requested scan. */
export const sample = {
  name: 'Aegra',
  tag: 'v0.11.0',
  graphUrl,
  provenance,
};

export async function loadSample(signal: AbortSignal) {
  const response = await fetch(graphUrl, { signal });
  if (!response.ok)
    throw new Error(`Graph request failed (${response.status}).`);
  const document = (await response.json()) as GraphDocument;
  if (document.illustrative !== false)
    throw new Error('The bundled document is not a real scan.');
  return openDocument(document);
}

export class EmptyScanError extends Error {}

export function openDocument(document: GraphDocument): AtlasGraph {
  if (!document.routes?.length || !document.symbolIndex?.length)
    throw new EmptyScanError(
      'The scanner recorded no HTTP routes in this repository, so there is no request flow to draw.',
    );
  return adaptGraph(document);
}
