import { ancestors, visibleIds } from './adapter';
import type { AtlasGraph, Camera } from './types';

export interface ViewSnapshot {
  path: string[];
  selected: string;
  camera: Camera;
}
export interface NavigationState extends ViewSnapshot {
  history: ViewSnapshot[];
}
export type NavigationAction =
  | { type: 'select' | 'expand' | 'collapse'; id: string }
  | { type: 'camera'; camera: Camera }
  | { type: 'breadcrumb'; depth: number }
  | { type: 'back' };
const snapshot = ({ path, selected, camera }: ViewSnapshot): ViewSnapshot => ({
  path: [...path],
  selected,
  camera: { ...camera },
});
export const initialNavigation = (graph: AtlasGraph): NavigationState => ({
  path: [],
  selected: graph.defaultId,
  camera: { scale: 1, x: 0, y: 0 },
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
    return previous ? { ...snapshot(previous), history: state.history.slice(0, -1) } : state;
  }
  if (action.type === 'breadcrumb') {
    if (action.depth < 0 || action.depth >= state.path.length) return state;
    const path = state.path.slice(0, action.depth);
    const prior = state.history.findLastIndex(
      (item) => item.path.length === path.length && item.path.every((id, i) => id === path[i]),
    );
    if (prior >= 0) return { ...snapshot(state.history[prior]), history: state.history.slice(0, prior) };
    return {
      ...state,
      path,
      selected: state.path[action.depth],
      history: [...state.history, snapshot(state)],
    };
  }
  const node = graph.nodes.get(action.id);
  if (!node || !visibleIds(graph, state.path).has(action.id)) return state;
  if (action.type === 'select') return { ...state, selected: action.id };
  if (action.type === 'expand') {
    if (!node.children.length || state.path.includes(node.id)) return state;
    return {
      ...state,
      selected: node.id,
      path: ancestors(graph, node.id),
      history: [...state.history, snapshot(state)],
    };
  }
  const index = state.path.indexOf(node.id);
  if (index < 0) return state;
  return {
    ...state,
    selected: node.id,
    path: state.path.slice(0, index),
    history: [...state.history, snapshot(state)],
  };
}
