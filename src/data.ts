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

export function openDocument(document: GraphDocument): AtlasGraph {
  if (!Array.isArray(document.routes) || !Array.isArray(document.symbolIndex))
    throw new Error('The scan document is missing its route or symbol index.');
  return adaptGraph(document);
}
