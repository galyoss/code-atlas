import type { GraphNode } from './types';
export type GraphView = 'code' | 'entries' | 'data';
export type DataEffect = 'read' | 'write' | 'both';
const operations: Record<string, DataEffect> = {
  load: 'read',
  query: 'read',
  create: 'write',
  update: 'write',
  delete: 'write',
};
export function accessSummary(node: GraphNode) {
  let read = 0,
    write = 0,
    unknown = 0;
  for (const { access } of node.accesses) {
    const effect = operations[access.operation];
    if (effect === 'read') read++;
    else if (effect === 'write') write++;
    else unknown++;
  }
  return { read, write, unknown, total: node.accesses.length };
}
/** A canonical badge summarizes named accesses in its body; call effects stay local. */
export function dataEffect(node: GraphNode): DataEffect | null {
  const { read, write } = accessSummary(node);
  if (read || write) return read && write ? 'both' : read ? 'read' : 'write';
  if (node.canonical) return null;
  return persistenceEffect(node.call?.touchesPersistence);
}
export function persistenceEffect(value?: string): DataEffect | null {
  return value === 'read_write'
    ? 'both'
    : value === 'read' || value === 'write'
      ? value
      : null;
}
export const effectLabel = (effect: DataEffect) =>
  ({ read: 'Read', write: 'Write', both: 'Read + write' })[effect];
export const effectGlyph = (effect: DataEffect) =>
  ({ read: 'R', write: 'W', both: 'RW' })[effect];
export function emphasized(node: GraphNode, view: GraphView) {
  return (
    view === 'code' ||
    (view === 'entries'
      ? !!node.groupedRoutes?.length
      : node.accesses.length > 0)
  );
}
export function semanticDescription(node: GraphNode) {
  const routes = node.groupedRoutes
    ?.map((r) => `${r.httpMethod} ${r.pathTemplate}`)
    .join('\n');
  const counts = accessSummary(node),
    effect = dataEffect(node);
  const data = counts.total
    ? `${counts.read} read · ${counts.write} write${counts.unknown ? ` · ${counts.unknown} unknown` : ''} ${node.canonical ? 'route-scoped access records in this function body' : 'named object access records'}`
    : effect
      ? `${effectLabel(effect)} persistence effect; no named object access recorded`
      : '';
  const objects = !node.canonical
    ? node.accesses
        .map(({ access }) => `${access.operation} ${access.object.name}`)
        .join(' · ')
    : '';
  return [routes, objects, data].filter(Boolean).join('\n');
}

const operationLabels: Record<string, string> = {
  load: 'Read',
  query: 'Query',
  create: 'Create',
  update: 'Update',
  delete: 'Delete',
};
export function nodeLabel(node: GraphNode) {
  if (node.canonical || !node.accesses.length) return node.name;
  return [
    ...new Set(
      node.accesses.map(
        ({ access }) =>
          `${operationLabels[access.operation] || access.operation} ${access.object.name}`,
      ),
    ),
  ].join(' · ');
}
