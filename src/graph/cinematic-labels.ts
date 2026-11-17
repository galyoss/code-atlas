export interface LabelRect { x: number; y: number; width: number; height: number }
function intersects(a: LabelRect, b: LabelRect) {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

/** Keep a label near its projected anchor while avoiding real HUD and earlier labels. */
export function placeRegionLabel(anchor: { x: number; y: number }, size: { width: number; height: number },
  viewport: { width: number; height: number }, obstacles: LabelRect[]): LabelRect | null {
  const margin = 14, gap = 8, maxOffset = viewport.width <= 760 ? 145 : 210;
  const preferred = { x: anchor.x - size.width / 2, y: anchor.y - size.height };
  const maxX = viewport.width - size.width - margin, maxY = viewport.height - size.height - margin;
  if (maxX < margin || maxY < margin) return null;
  const clampX = (x: number) => Math.max(margin, Math.min(maxX, x));
  const clampY = (y: number) => Math.max(margin, Math.min(maxY, y));
  const xs = [clampX(preferred.x)], ys = [clampY(preferred.y)];
  for (const obstacle of obstacles) {
    xs.push(clampX(obstacle.x - size.width - gap), clampX(obstacle.x + obstacle.width + gap));
    ys.push(clampY(obstacle.y - size.height - gap), clampY(obstacle.y + obstacle.height + gap));
  }
  let best: LabelRect | null = null, bestDistance = maxOffset * maxOffset;
  for (const x of xs) for (const y of ys) {
    const distance = (x - preferred.x) ** 2 + (y - preferred.y) ** 2;
    if (distance > bestDistance) continue;
    const rect = { x, y, ...size };
    const padded = { x: x - gap / 2, y: y - gap / 2, width: size.width + gap, height: size.height + gap };
    if (obstacles.some(obstacle => intersects(padded, obstacle))) continue;
    best = rect; bestDistance = distance;
  }
  return best;
}
