import type { AtlasGraph } from './types';

/** Literal terms across recorded symbol, route and file fields; identity stays the symbol ID. */
export function matchingSymbols(graph: AtlasGraph, query: string): string[] {
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const matches = graph.baseIds.filter((id) => {
    const node = graph.nodes.get(id)!;
    const fields =
      `${node.symbol?.qualifiedName} ${node.range?.file} ${(node.groupedRoutes || []).map((route) => `${route.httpMethod} ${route.pathTemplate}`).join(' ')}`.toLocaleLowerCase();
    return terms.every((term) => fields.includes(term));
  });
  // Exact identifiers precede substring matches (create_run before apply_create_run_auth).
  const exact = (id: string) =>
    terms.includes(graph.nodes.get(id)!.name.toLocaleLowerCase());
  return matches.sort(
    (a, b) =>
      Number(exact(b)) - Number(exact(a)) ||
      graph.nodes.get(a)!.name.localeCompare(graph.nodes.get(b)!.name),
  );
}
