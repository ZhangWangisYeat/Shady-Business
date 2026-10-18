import type { Coordinate } from '../api/types';

const M_PER_DEG = 111_320;
// paths closer than this are the same walkway (gps and map noise is ~10 m)
const SAME_PATH_M = 15;
const SAMPLE_M = 10;

const toXY = (p: Coordinate, cosLat: number): [number, number] => [p[0] * M_PER_DEG * cosLat, p[1] * M_PER_DEG];

function distanceToLine(p: [number, number], line: [number, number][]): number {
  let best = Infinity;
  for (let i = 1; i < line.length; i++) {
    const [ax, ay] = line[i - 1], [bx, by] = line[i];
    const dx = bx - ax, dy = by - ay;
    const len2 = dx * dx + dy * dy;
    const t = len2 ? Math.max(0, Math.min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / len2)) : 0;
    best = Math.min(best, Math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy)));
  }
  return best;
}

// share of `path`'s length that runs more than 15 m from `other`, sampled every
// 10 m. 0 means it's the same walk, 1 means it never touches the other one.
export function distinctShare(path: Coordinate[], other: Coordinate[]): number {
  if (path.length < 2 || other.length < 2) return 0;
  const cosLat = Math.cos((path[0][1] * Math.PI) / 180);
  const a = path.map(p => toXY(p, cosLat));
  const b = other.map(p => toXY(p, cosLat));
  let total = 0, apart = 0;
  for (let i = 1; i < a.length; i++) {
    const [x0, y0] = a[i - 1], [x1, y1] = a[i];
    const len = Math.hypot(x1 - x0, y1 - y0);
    const steps = Math.max(1, Math.ceil(len / SAMPLE_M));
    for (let s = 0; s < steps; s++) {
      const t = (s + 0.5) / steps;
      const piece = len / steps;
      total += piece;
      if (distanceToLine([x0 + t * (x1 - x0), y0 + t * (y1 - y0)], b) > SAME_PATH_M) apart += piece;
    }
  }
  return total ? apart / total : 0;
}
