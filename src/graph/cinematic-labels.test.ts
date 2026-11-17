import { describe, expect, it } from 'vitest';
import { placeRegionLabel, type LabelRect } from './cinematic-labels';
const collides = (a: LabelRect, b: LabelRect) => a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
describe('projected semantic label placement', () => {
  it('moves a header-overlapping label into free graph space and keeps subsequent labels apart', () => {
    const viewport = { width: 1512, height: 827 }, size = { width: 155, height: 38 };
    const obstacles = [{ x: 0, y: 0, width: 1512, height: 84 }, { x: 430, y: 91, width: 660, height: 51 }];
    const first = placeRegionLabel({ x: 756, y: 33 }, size, viewport, obstacles)!;
    expect(first).not.toBeNull();
    expect(obstacles.some(rect => collides(first, rect))).toBe(false);
    const second = placeRegionLabel({ x: 756, y: 59 }, size, viewport, [...obstacles, first])!;
    expect(second).not.toBeNull();
    expect(collides(first, second)).toBe(false);
  });
  it('avoids the selected card and stays inside a narrow viewport, or hides when all space is occupied', () => {
    const viewport = { width: 390, height: 844 }, size = { width: 135, height: 35 };
    const card = { x: 18, y: 410, width: 354, height: 256 };
    const placed = placeRegionLabel({ x: 370, y: 440 }, size, viewport, [card])!;
    expect(placed).not.toBeNull();
    expect(placed.x).toBeGreaterThanOrEqual(14);
    expect(placed.x + placed.width).toBeLessThanOrEqual(376);
    expect(collides(placed, card)).toBe(false);
    expect(placeRegionLabel({ x: 195, y: 400 }, size, viewport, [{ x: 0, y: 0, ...viewport }])).toBeNull();
  });
});
