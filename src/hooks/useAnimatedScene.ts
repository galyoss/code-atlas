import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { AtlasGraph, Point } from '../graph/types';

export interface Pose extends Point {
  opacity: number;
}
const media =
  typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)') : undefined;
const subscribe = (callback: () => void) => {
  media?.addEventListener('change', callback);
  return () => media?.removeEventListener('change', callback);
};

export function useAnimatedScene(
  graph: AtlasGraph,
  positions: Map<string, Point>,
  visible: Set<string>,
  path: string[],
  selected: string,
) {
  const reducedMotion = useSyncExternalStore(
    subscribe,
    () => media?.matches ?? false,
    () => false,
  );
  const [poses, setPoses] = useState<Map<string, Pose>>(
    () => new Map([...visible].map((id) => [id, { ...positions.get(id)!, opacity: 1 }])),
  );
  const current = useRef(poses);
  const [transitioning, setTransitioning] = useState(false);
  useEffect(() => {
    const from = new Map(current.current);
    const target = new Map<string, Pose>();
    const activeParent = path.at(-1);
    for (const id of visible) {
      const node = graph.nodes.get(id)!;
      const active = !path.length || id === selected || path.includes(id) || node.parent === activeParent;
      target.set(id, { ...positions.get(id)!, opacity: active ? 1 : node.kind === 'model' ? 0.2 : 0.42 });
      if (!from.has(id)) {
        let parent = node.parent;
        while (parent && !from.has(parent)) parent = graph.nodes.get(parent)?.parent;
        from.set(id, { ...(parent ? from.get(parent)! : positions.get(id)!), opacity: 0 });
      }
    }
    for (const [id] of from) {
      if (visible.has(id)) continue;
      let parent = graph.nodes.get(id)?.parent;
      while (parent && !visible.has(parent)) parent = graph.nodes.get(parent)?.parent;
      target.set(id, { ...positions.get(parent || graph.defaultId)!, opacity: 0 });
    }
    let frame = 0;
    const start = performance.now();
    const duration = reducedMotion ? 0 : 600;
    setTransitioning(duration > 0);
    function tick(now: number) {
      const progress = duration ? Math.min(1, (now - start) / duration) : 1;
      const eased = 1 - (1 - progress) ** 3;
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
    }
    if (duration) frame = requestAnimationFrame(tick);
    else tick(start);
    return () => cancelAnimationFrame(frame);
  }, [graph, positions, visible, path, selected, reducedMotion]);
  return { poses, transitioning };
}
