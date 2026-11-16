import { visibleIds } from './adapter';
import type { AtlasGraph, Camera } from './types';
export interface ViewSnapshot {
  expanded: Set<string>;
  collapsed: Set<string>;
  selected: string | null;
  camera: Camera;
}
export interface NavigationState extends ViewSnapshot {
  history: ViewSnapshot[];
}
export type NavigationAction =
  | { type: 'select'; id: string | null }
  | { type: 'toggle'; id: string }
  | { type: 'reveal'; id: string; camera?: Camera }
  | { type: 'camera'; camera: Camera }
  | { type: 'back' };
const snapshot = (state: ViewSnapshot): ViewSnapshot => ({
  expanded: new Set(state.expanded),
  collapsed: new Set(state.collapsed),
  selected: state.selected,
  camera: { ...state.camera },
});
export const initialNavigation = (): NavigationState => ({
  expanded: new Set(),
  collapsed: new Set(),
  selected: null,
  camera: { x: 0, y: 0, scale: 1 },
  history: [],
});
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
  if (action.id && !graph.nodes.has(action.id)) return state;
  const next = {
    ...snapshot(state),
    history: [...state.history, snapshot(state)],
  };
  if (action.type === 'select') {
    if (
      action.id &&
      !visibleIds(graph, state.expanded, state.collapsed).has(action.id)
    )
      return state;
    next.selected = action.id;
  } else if (action.type === 'reveal') {
    const node = graph.nodes.get(action.id)!;
    if (!node.canonical) return state;
    next.collapsed.delete(node.groupId!);
    next.selected = action.id;
    if (action.camera) next.camera = action.camera;
  } else {
    const node = graph.nodes.get(action.id)!;
    if (!visibleIds(graph, state.expanded, state.collapsed).has(node.id))
      return state;
    if (node.kind === 'group') {
      if (next.collapsed.has(node.id)) next.collapsed.delete(node.id);
      else next.collapsed.add(node.id);
    } else {
      if (!node.children.length) return state;
      if (next.expanded.has(node.id)) next.expanded.delete(node.id);
      else next.expanded.add(node.id);
    }
    next.selected = node.id;
  }
  return next;
}
