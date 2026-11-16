import { accessPathIds, visibleIds } from './adapter';
import type { GraphView } from './semantics';
import type { AtlasGraph, Camera } from './types';
export interface ViewSnapshot {
  expanded: Set<string>;
  revealed: Set<string>;
  accessFocus: string | null;
  collapsed: Set<string>;
  selected: string | null;
  camera: Camera;
  view: GraphView;
  railOpen: boolean;
}
export interface NavigationState extends ViewSnapshot {
  history: ViewSnapshot[];
}
export type NavigationAction =
  | { type: 'select'; id: string | null }
  | { type: 'toggle'; id: string }
  | { type: 'reveal'; id: string; camera?: Camera }
  | { type: 'accesses'; id: string }
  | { type: 'view'; view: GraphView }
  | { type: 'rail'; open: boolean }
  | { type: 'resolution'; resolution: 'files' | 'functions' }
  | { type: 'depth'; depth: 0 | 1 | 2 | 3 }
  | { type: 'camera'; camera: Camera }
  | { type: 'back' };
const snapshot = (state: ViewSnapshot): ViewSnapshot => ({
  expanded: new Set(state.expanded),
  revealed: new Set(state.revealed),
  accessFocus: state.accessFocus,
  collapsed: new Set(state.collapsed),
  selected: state.selected,
  camera: { ...state.camera },
  view: state.view,
  railOpen: state.railOpen,
});
export const initialNavigation = (railOpen = true): NavigationState => ({
  expanded: new Set(),
  revealed: new Set(),
  accessFocus: null,
  collapsed: new Set(),
  selected: null,
  camera: { x: 0, y: 0, scale: 1 },
  view: 'code',
  railOpen,
  history: [],
});
export function resolution(graph: AtlasGraph, state: ViewSnapshot) {
  return !state.collapsed.size
    ? 'functions'
    : state.collapsed.size === graph.groups.length
      ? 'files'
      : 'mixed';
}
/** Compare visible depth, ignoring saved expansions beneath a closed ancestor. */
export function branchDepth(
  graph: AtlasGraph,
  state: ViewSnapshot,
): number | 'mixed' | null {
  const node = state.selected ? graph.nodes.get(state.selected) : null;
  if (!node?.children.length || node.kind === 'group') return null;
  function matches(id: string, remaining: number): boolean {
    const current = graph.nodes.get(id)!;
    if (!current.children.length) return true;
    const open = current.children.filter(
      (child) => state.expanded.has(id) || state.revealed.has(child),
    );
    if (!remaining) return open.length === 0;
    return (
      open.length === current.children.length &&
      current.children.every((child) => matches(child, remaining - 1))
    );
  }
  for (let depth = 0; depth <= 3; depth++)
    if (matches(node.id, depth)) return depth;
  return 'mixed';
}
export function navigate(
  graph: AtlasGraph,
  state: NavigationState,
  action: NavigationAction,
): NavigationState {
  if (action.type === 'camera') return { ...state, camera: action.camera };
  if (action.type === 'back') {
    const previous = state.history.at(-1);
    return previous
      ? { ...snapshot(previous), history: state.history.slice(0, -1) }
      : state;
  }
  if (action.type === 'select' && action.id === state.selected) return state;
  if ('id' in action && action.id && !graph.nodes.has(action.id)) return state;
  const next = {
    ...snapshot(state),
    history: [...state.history, snapshot(state)],
  };
  const visible = visibleIds(
    graph,
    state.expanded,
    state.collapsed,
    state.revealed,
  );
  if (action.type === 'view') {
    if (action.view === state.view) return state;
    next.view = action.view;
  } else if (action.type === 'rail') {
    if (action.open === state.railOpen) return state;
    next.railOpen = action.open;
  } else if (action.type === 'resolution') {
    if (resolution(graph, state) === action.resolution) return state;
    next.collapsed =
      action.resolution === 'files'
        ? new Set(graph.groups.map((group) => group.id))
        : new Set();
    if (next.selected && action.resolution === 'files') {
      const node = graph.nodes.get(next.selected)!;
      next.selected = node.groupId || node.id;
    }
  } else if (action.type === 'depth') {
    const node = state.selected ? graph.nodes.get(state.selected)! : null;
    if (
      !node?.children.length ||
      node.kind === 'group' ||
      !visible.has(node.id)
    )
      return state;
    // Local replacement: unrelated branches and their saved expansions survive.
    function setDepth(id: string, depth: number) {
      const current = graph.nodes.get(id)!;
      if (current.children.length && depth > 0) next.expanded.add(id);
      else next.expanded.delete(id);
      current.children.forEach((child) => {
        next.revealed.delete(child);
        setDepth(child, depth - 1);
      });
    }
    setDepth(node.id, action.depth);
    next.accessFocus = null;
  } else if (action.type === 'accesses') {
    const owner = graph.nodes.get(action.id)!;
    if (!owner.canonical || !owner.accesses.length) return state;
    for (const id of accessPathIds(graph, owner.id)) {
      const node = graph.nodes.get(id)!;
      if (!node.canonical) next.revealed.add(id);
      if (node.groupId) next.collapsed.delete(node.groupId);
    }
    next.accessFocus = owner.id;
    next.collapsed.delete(owner.groupId!);
    next.selected = owner.id;
  } else if (action.type === 'select') {
    if (action.id && !visible.has(action.id)) return state;
    next.selected = action.id;
    next.accessFocus = null;
  } else if (action.type === 'reveal') {
    const node = graph.nodes.get(action.id)!;
    if (!node.canonical) return state;
    next.collapsed.delete(node.groupId!);
    next.selected = action.id;
    if (action.camera) next.camera = action.camera;
    next.accessFocus = null;
  } else {
    const node = graph.nodes.get(action.id)!;
    if (!visible.has(node.id)) return state;
    if (node.kind === 'group') {
      if (next.collapsed.has(node.id)) next.collapsed.delete(node.id);
      else next.collapsed.add(node.id);
    } else {
      if (!node.children.length) return state;
      if (branchOpen(graph, state, node.id)) {
        next.expanded.delete(node.id);
        function hideRevealed(id: string) {
          for (const child of graph.nodes.get(id)!.children) {
            next.revealed.delete(child);
            hideRevealed(child);
          }
        }
        hideRevealed(node.id);
      } else next.expanded.add(node.id);
    }
    next.selected = node.id;
    next.accessFocus = null;
  }
  return next;
}

export function branchOpen(graph: AtlasGraph, state: ViewSnapshot, id: string) {
  return (
    state.expanded.has(id) ||
    graph.nodes.get(id)!.children.some((child) => state.revealed.has(child))
  );
}
