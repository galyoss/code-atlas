import type { AtlasGraph, Camera, Point } from './types';

export const NODE_WIDTH = 244;
export const NODE_HEIGHT = 64;
const COLUMN_GAP = 306;
const CALL_PITCH = 112;

/** Fixed world coordinates depend only on the fixture, never on navigation or zoom. */
export function layoutGraph(graph: AtlasGraph): Map<string, Point> {
  const positions = new Map<string, Point>();
  const ofKind = (kind: string) => graph.baseIds.filter((id) => graph.nodes.get(id)!.kind === kind);
  const routes = ofKind('route');
  const auth = ofKind('auth');
  const models = ofKind('model');
  const height = Math.max(640, routes.length * 300, models.length * 200);
  const distribute = (ids: string[], x: number, start: number, end: number) =>
    ids.forEach((id, i) =>
      positions.set(id, {
        x,
        y: ids.length === 1 ? (start + end) / 2 : start + (i * (end - start)) / (ids.length - 1),
      }),
    );
  auth.forEach((id, i) => positions.set(id, { x: 130 + i * COLUMN_GAP, y: 42 }));
  distribute(routes, 190, 230, height - 110);
  distribute(models, 1020, 140, height - 70);
  function placeChildren(id: string) {
    const parent = positions.get(id)!;
    const children = graph.nodes.get(id)!.children;
    children.forEach((child, index) => {
      positions.set(child, {
        x: parent.x + COLUMN_GAP,
        y: parent.y + (index - (children.length - 1) / 2) * CALL_PITCH,
      });
      placeChildren(child);
    });
  }
  routes.forEach(placeChildren);
  return positions;
}

export function initialCamera(
  positions: Map<string, Point>,
  graph: AtlasGraph,
  width: number,
  height: number,
): Camera {
  if (width < 700) {
    const selected = positions.get(graph.defaultId)!;
    return { scale: 0.95, x: 32 - selected.x * 0.95, y: height * 0.42 - selected.y * 0.95 };
  }
  return fitCamera(positions, new Set(graph.baseIds), width, height);
}

export function fitCamera(
  positions: Map<string, Point>,
  ids: Set<string>,
  width: number,
  height: number,
): Camera {
  const points = [...ids].map((id) => positions.get(id)!);
  const minX = Math.min(...points.map((p) => p.x));
  const maxX = Math.max(...points.map((p) => p.x)) + NODE_WIDTH;
  const minY = Math.min(...points.map((p) => p.y));
  const maxY = Math.max(...points.map((p) => p.y)) + NODE_HEIGHT;
  const scale = Math.max(0.45, Math.min(1.1, (width - 100) / (maxX - minX), (height - 100) / (maxY - minY)));
  return { scale, x: (width - (maxX + minX) * scale) / 2, y: (height - (maxY + minY) * scale) / 2 };
}

export function zoomCamera(camera: Camera, factor: number, center: Point): Camera {
  const scale = Math.max(0.45, Math.min(1.8, camera.scale * factor));
  return {
    scale,
    x: center.x - ((center.x - camera.x) * scale) / camera.scale,
    y: center.y - ((center.y - camera.y) * scale) / camera.scale,
  };
}
