import { useLayoutEffect, useRef, useSyncExternalStore } from 'react';
import type { ProjectView } from '../ProjectReport';

function subscribe(callback: () => void) {
  window.addEventListener('popstate', callback);
  return () => window.removeEventListener('popstate', callback);
}
export function useAddress() {
  return new URLSearchParams(
    useSyncExternalStore(subscribe, () => window.location.search),
  );
}
export function go(search: string, replace = false) {
  const destination = window.location.pathname + search;
  if (destination === window.location.pathname + window.location.search) return;
  window.history[replace ? 'replaceState' : 'pushState'](null, '', destination);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
/** Prefer an explicit private report even if a link also carries a sample parameter. */
export const isSample = (params: URLSearchParams) =>
  !params.has('project') &&
  !params.has('scan') &&
  params.get('sample') === 'aegra';

export function useMounted() {
  const mounted = useRef(false);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return mounted;
}
export function viewOf(params: URLSearchParams): ProjectView {
  const value = params.get('view');
  if (value === '2d' || value === 'routes' || value === 'issues') return value;
  if (!value && isSample(params)) return '2d'; // Original shared sample link.
  return '3d';
}
export const projectAddress = (id: string, view: ProjectView) =>
  '?' + new URLSearchParams({ project: id, view }).toString();
export const sampleAddress = (view: ProjectView = '3d') =>
  '?sample=aegra&view=' + view;
