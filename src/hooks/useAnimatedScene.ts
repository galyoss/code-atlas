import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { AtlasGraph, Point } from '../graph/types';
export interface Pose extends Point {
  opacity: number;
}
const media =
  typeof window !== 'undefined'
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : undefined;
const subscribe = (callback: () => void) => {
  media?.addEventListener('change', callback);
  return () => media?.removeEventListener('change', callback);
};
export function useAnimatedScene(
  graph: AtlasGraph,
  positions: Map<string, Point>,
  visible: Set<string>,
) {
  const reduced = useSyncExternalStore(
    subscribe,
    () => media?.matches ?? false,
    () => false,
  );
  const [poses, setPoses] = useState<Map<string, Pose>>(
    () =>
      new Map(
        [...visible].map((id) => [id, { ...positions.get(id)!, opacity: 1 }]),
      ),
  );
  const current = useRef(poses);
  const [transitioning, setTransitioning] = useState(false);
  useEffect(() => {
    const from = new Map(current.current),
      target = new Map<string, Pose>();
    function origin(
      id: string,
      available: ReadonlyMap<string, Pose> | ReadonlySet<string>,
    ) {
      let node = graph.nodes.get(id)!;
      let parent = node.parent || node.groupId;
      while (parent && !available.has(parent)) {
        node = graph.nodes.get(parent)!;
        parent = node.parent || node.groupId;
      }
      return parent
        ? available instanceof Map
          ? available.get(parent)!
          : positions.get(parent)!
        : positions.get(id)!;
    }
    for (const id of visible) {
      target.set(id, { ...positions.get(id)!, opacity: 1 });
      if (!from.has(id)) from.set(id, { ...origin(id, from), opacity: 0 });
    }
    for (const id of from.keys())
      if (!visible.has(id))
        target.set(id, { ...origin(id, visible), opacity: 0 });
    let frame = 0;
    const start = performance.now(),
      duration = reduced ? 0 : 600;
    setTransitioning(!reduced);
    const tick = (now: number) => {
      const progress = duration ? Math.min(1, (now - start) / duration) : 1,
        eased = 1 - (1 - progress) ** 3;
      const next = new Map<string, Pose>();
      for (const [id, end] of target) {
        if (progress === 1 && !visible.has(id)) continue;
        const begin = from.get(id)!;
        next.set(id, {
          x: begin.x + (end.x - begin.x) * eased,
          y: begin.y + (end.y - begin.y) * eased,
          opacity: begin.opacity + (end.opacity - begin.opacity) * eased,
        });
      }
      current.current = next;
      setPoses(next);
      if (progress < 1) frame = requestAnimationFrame(tick);
      else setTransitioning(false);
    };
    if (duration) frame = requestAnimationFrame(tick);
    else tick(start);
    return () => cancelAnimationFrame(frame);
  }, [graph, positions, visible, reduced]);
  return { poses, transitioning };
}
