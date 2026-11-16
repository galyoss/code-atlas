import type { AtlasGraph, Camera, Point } from './types';
import { nodeLabel } from './semantics';
export interface Rect extends Point {
  width: number;
  height: number;
}
export interface LabelViewport {
  width: number;
  height: number;
  blocked: Rect[];
}
const overlaps = (a: Rect, b: Rect) =>
  a.x < b.x + b.width &&
  a.x + a.width > b.x &&
  a.y < b.y + b.height &&
  a.y + a.height > b.y;

/** Labels can find space without changing any glyph's world anchor. Positions are
 * screen-pixel offsets from the glyph center, so names remain readable while zooming. */
export function placeLabels(
  graph: AtlasGraph,
  positions: Map<string, Point>,
  visible: ReadonlySet<string>,
  priority: string[],
  scale: number,
  active: string | null,
  viewport?: LabelViewport & { camera: Camera },
) {
  const allowed = (rect: Rect) => {
    if (!viewport) return true;
    const screen = {
      ...rect,
      x: rect.x + viewport.camera.x,
      y: rect.y + viewport.camera.y,
    };
    return (
      screen.x >= 4 &&
      screen.y >= 4 &&
      screen.x + screen.width <= viewport.width - 4 &&
      screen.y + screen.height <= viewport.height - 4 &&
      !viewport.blocked.some((block) => overlaps(screen, block))
    );
  };
  const placed = new Map<string, Point>();
  const occupied: Rect[] = [];
  for (const id of visible) {
    const point = positions.get(id)!,
      node = graph.nodes.get(id)!;
    const width =
      node.kind === 'group'
        ? (node.children.length >= 4
            ? Math.min(node.name.length * 6 + 40, 180)
            : 24) * scale
        : 20;
    const height = node.kind === 'group' ? 24 * scale : 20;
    occupied.push({
      x: point.x * scale - width / 2,
      y: point.y * scale - height / 2,
      width,
      height,
    });
  }
  if (
    active &&
    visible.has(active) &&
    graph.nodes.get(active)!.kind !== 'group'
  ) {
    const point = positions.get(active)!;
    const width = Math.min(
      nodeLabel(graph.nodes.get(active)!).length * 6.6 + 18,
      420,
    );
    for (const offset of [
      { x: 14, y: -14 },
      { x: -width - 14, y: -14 },
      { x: -width / 2, y: -42 },
      { x: -width / 2, y: 18 },
    ]) {
      const rect = {
        x: point.x * scale + offset.x,
        y: point.y * scale + offset.y,
        width,
        height: 28,
      };
      if (!allowed(rect)) continue;
      placed.set(active, offset);
      occupied.push(rect);
      break;
    }
  }
  for (const id of priority) {
    if (placed.size >= (active ? 36 : 23) || placed.has(id) || !visible.has(id))
      continue;
    const node = graph.nodes.get(id)!;
    if (node.kind === 'group') continue;
    const point = positions.get(id)!,
      width = Math.min(nodeLabel(node).length * 6 + 6, 162),
      height = 16;
    const options = [
      { x: 14, y: -8 },
      { x: -width - 14, y: -8 },
      { x: -width / 2, y: -27 },
      { x: -width / 2, y: 13 },
    ];
    // Named accesses deserve a readable label even inside a dense file cluster.
    // Search additional free positions; leaders retain the association to the glyph.
    if (!node.canonical && node.accesses.length)
      for (const distance of [38, 62, 86, 110])
        options.push(
          { x: distance, y: -8 },
          { x: -width - distance, y: -8 },
          { x: -width / 2, y: -distance },
          { x: -width / 2, y: distance },
          { x: distance, y: -distance },
          { x: -width - distance, y: distance },
        );
    for (const offset of options) {
      const rect = {
        x: point.x * scale + offset.x,
        y: point.y * scale + offset.y,
        width,
        height,
      };
      if (!allowed(rect) || occupied.some((other) => overlaps(rect, other)))
        continue;
      placed.set(id, offset);
      occupied.push(rect);
      break;
    }
  }
  return placed;
}
