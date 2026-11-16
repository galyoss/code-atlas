import type { AtlasGraph, Camera, Point } from './types';

export const NODE_WIDTH = 244;
export const NODE_HEIGHT = 64;
const COLUMN_GAP = 306;
const CALL_PITCH = 112;

/** Sibling lanes are bounded vertically. Descendants start beyond the full sibling block.
 * Only one branch opens per depth, so every simultaneously visible node has its own slot.
 * Coordinates depend on recorded structure, never expansion, selection or camera. */
export function layoutGraph(graph: AtlasGraph): Map<string, Point> {
  const positions = new Map<string, Point>();
  if (graph.nodes.get(graph.defaultId)?.kind === 'repository') {
    const groups = graph.baseIds.filter((id) => id !== graph.defaultId);
    positions.set(graph.defaultId, { x: 496, y: 0 });
    groups.forEach((id, i) =>
      positions.set(id, {
        x: 190 + (i % 3) * COLUMN_GAP,
        y: 130 + Math.floor(i / 3) * 110,
      }),
    );
    return positions;
  }
  const ofKind = (kind: string) => graph.baseIds.filter((id) => graph.nodes.get(id)!.kind === kind);
  const routes = ofKind('route');
  const context = graph.baseIds.filter((id) => graph.nodes.get(id)!.kind !== 'route');
  context.forEach((id, i) =>
    positions.set(id, {
      x: 190 - (1 + Math.floor(i / 6)) * COLUMN_GAP,
      y: 230 + ((i % 6) - (Math.min(context.length, 6) - 1) / 2) * CALL_PITCH,
    }),
  );
  function placeChildren(id: string, startX: number) {
    const parent = positions.get(id)!;
    const children = graph.nodes.get(id)!.children;
    const rows = Math.min(children.length, 6);
    const nextX = startX + Math.ceil(children.length / 6) * COLUMN_GAP;
    children.forEach((child, index) => {
      positions.set(child, {
        x: startX + Math.floor(index / 6) * COLUMN_GAP,
        y: parent.y + ((index % 6) - (rows - 1) / 2) * CALL_PITCH,
      });
      placeChildren(child, nextX);
    });
  }
  routes.forEach((id, i) => {
    positions.set(id, { x: 190, y: 230 + i * 800 });
    placeChildren(id, 190 + COLUMN_GAP);
  });
  return positions;
}

export function initialCamera(
  positions: Map<string, Point>,
  graph: AtlasGraph,
  width: number,
  height: number,
): Camera {
  const overview = fitCamera(positions, new Set(graph.baseIds), width, height);
  const readableScale = 0.95;
  if (overview.scale >= readableScale) return overview;

  // Keep the selected route readable when either canvas dimension constrains the overview.
  const selected = positions.get(graph.defaultId)!;
  return {
    scale: readableScale,
    x: Math.min(80, width * 0.08) - selected.x * readableScale,
    y: height * 0.42 - selected.y * readableScale,
  };
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
  return {
    scale,
    x: (width - (maxX + minX) * scale) / 2,
    y: (height - (maxY + minY) * scale) / 2,
  };
}

export function zoomCamera(camera: Camera, factor: number, center: Point): Camera {
  const scale = Math.max(0.45, Math.min(1.8, camera.scale * factor));
  return {
    scale,
    x: center.x - ((center.x - camera.x) * scale) / camera.scale,
    y: center.y - ((center.y - camera.y) * scale) / camera.scale,
  };
}
