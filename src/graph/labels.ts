import type { AtlasGraph, Point } from './types';
interface Rect extends Point {
  width: number;
  height: number;
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
) {
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
      graph.nodes.get(active)!.name.length * 6.6 + 18,
      420,
    );
    placed.set(active, { x: 14, y: -14 });
    occupied.push({
      x: point.x * scale + 14,
      y: point.y * scale - 14,
      width,
      height: 28,
    });
  }
  for (const id of priority) {
    if (placed.size >= (active ? 36 : 23) || placed.has(id) || !visible.has(id))
      continue;
    const node = graph.nodes.get(id)!;
    if (node.kind === 'group') continue;
    const point = positions.get(id)!,
      width = Math.min(node.name.length * 6 + 6, 162),
      height = 16;
    const options = [
      { x: 14, y: -8 },
      { x: -width - 14, y: -8 },
      { x: -width / 2, y: -27 },
      { x: -width / 2, y: 13 },
    ];
    for (const offset of options) {
      const rect = {
        x: point.x * scale + offset.x,
        y: point.y * scale + offset.y,
        width,
        height,
      };
      if (occupied.some((other) => overlaps(rect, other))) continue;
      placed.set(id, offset);
      occupied.push(rect);
      break;
    }
  }
  return placed;
}
