import { routeNodeId } from './adapter';
import type { AtlasGraph, GraphDocument, GraphNode, Route } from './types';

export interface RouteGroup {
  file: string;
  name: string;
  routes: Route[];
}

export function routeGroups(document: GraphDocument): RouteGroup[] {
  const groups = new Map<string, Route[]>();
  for (const route of document.routes) {
    const file = route.handler.range.file;
    const group = groups.get(file) || [];
    group.push(route);
    groups.set(file, group);
  }
  return [...groups]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([file, routes]) => ({
      file,
      name: file.split('/').at(-1)!,
      routes,
    }));
}

/** Match literal, case-insensitive terms against recorded fields, never inferred categories. */
export function matchingRoutes(groups: RouteGroup[], query: string): RouteGroup[] {
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return groups
    .map((group) => ({
      ...group,
      routes: group.routes.filter((route) => {
        const fields =
          `${route.httpMethod} ${route.pathTemplate} ${route.handler.qualifiedName} ${group.file}`.toLocaleLowerCase();
        return terms.every((term) => fields.includes(term));
      }),
    }))
    .filter((group) => group.routes.length > 0);
}

export const handlerName = (route: Route) => route.handler.qualifiedName.split('.').at(-1)!;
export const routeChoice = (route: Route) => ({
  id: routeNodeId(route.id),
  name: handlerName(route),
});

export function overviewGraph(graph: AtlasGraph, name = 'Repository'): AtlasGraph {
  const nodes = new Map<string, GraphNode>();
  nodes.set('repository', {
    id: 'repository',
    name,
    subtitle: `${graph.document.routes.length} routes · ${graph.document.symbolIndex.length} symbols`,
    kind: 'repository',
    children: [],
    accesses: [],
    authSteps: [],
    groupedRoutes: graph.document.routes,
  });
  for (const group of routeGroups(graph.document)) {
    const id = `source:${group.file}`;
    nodes.set(id, {
      id,
      name: group.name,
      subtitle: `${group.routes.length} routes · ${group.file.startsWith('examples/') ? 'example code' : 'source file'}`,
      kind: 'group',
      children: [],
      accesses: [],
      authSteps: [],
      groupedRoutes: group.routes,
      sourceFile: group.file,
    });
  }
  return {
    document: graph.document,
    nodes,
    baseIds: [...nodes.keys()],
    defaultId: 'repository',
    edges: [...nodes.keys()]
      .filter((id) => id !== 'repository')
      .map((id) => ({
        id: `contains:${id}`,
        from: 'repository',
        to: id,
        kind: 'contains',
      })),
  };
}
