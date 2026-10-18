import type { Coordinate, RouteSegment, ShadeState } from '../api/types';
import { meters } from '../navigation/progress';

export type SegmentFeature = {
  type: 'Feature'; id: number; properties: { shade: ShadeState };
  geometry: { type: 'LineString'; coordinates: Coordinate[] };
};

function lineLength(coords: Coordinate[]): number {
  let total = 0;
  for (let i = 1; i < coords.length; i++) total += meters(coords[i - 1], coords[i]);
  return total;
}

function cutLine(coords: Coordinate[], distance: number): Coordinate[] {
  const out: Coordinate[] = [coords[0]];
  let left = distance;
  for (let i = 1; i < coords.length; i++) {
    const step = meters(coords[i - 1], coords[i]);
    if (left >= step) { out.push(coords[i]); left -= step; continue; }
    const t = step ? left / step : 0;
    out.push([coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * t, coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * t]);
    break;
  }
  return out;
}

// the route "draws itself" from start to finish by only showing the first
// `fraction` of its length, and it's cut per segment so the shade colours stay
// on the right stretches while it animates.
export function revealSegments(segments: RouteSegment[], fraction: number): SegmentFeature[] {
  const lengths = segments.map(s => lineLength(s.geometry.coordinates));
  let budget = Math.max(0, Math.min(1, fraction)) * lengths.reduce((a, b) => a + b, 0);
  const features: SegmentFeature[] = [];
  segments.forEach((segment, i) => {
    if (budget <= 0) return;
    const coords = budget >= lengths[i] ? segment.geometry.coordinates : cutLine(segment.geometry.coordinates, budget);
    budget -= lengths[i];
    if (coords.length >= 2) features.push({ type: 'Feature', id: i, properties: { shade: segment.shade_state }, geometry: { type: 'LineString', coordinates: coords } });
  });
  return features;
}
