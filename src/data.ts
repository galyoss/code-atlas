import graphUrl from '../docs/scans/aegra-v0.11.0.graph.json?url';
import provenance from '../docs/scans/aegra-v0.11.0.provenance.json';
import { adaptGraph } from './graph/adapter';
import type { GraphDocument } from './graph/types';

export const scan = { name: 'Aegra', tag: 'v0.11.0', graphUrl, provenance };

export async function loadScan(signal: AbortSignal) {
  const response = await fetch(graphUrl, { signal });
  if (!response.ok) throw new Error(`Graph request failed (${response.status}).`);
  const document = (await response.json()) as GraphDocument;
  if (document.illustrative !== false || !document.routes?.length || !document.symbolIndex) {
    throw new Error('The bundled document is not a real scan with recorded routes.');
  }
  return adaptGraph(document);
}
