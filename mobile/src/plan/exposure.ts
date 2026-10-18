import type { Route } from '../api/types';

export type Exposure = { sunPct: number | null; unknownPct: number };

// percentages of walking time, from the segments rather than the route total,
// because the route's sun_seconds goes null as soon as any stretch is unknown
// and that would hide a route that's 90% modeled. unknown time is never
// counted as shade (ADR-004), it gets its own number instead.
export function exposure(route: Route): Exposure {
  const total = route.segments.reduce((sum, s) => sum + s.duration_s, 0) || route.duration_s;
  if (!total) return { sunPct: null, unknownPct: 100 };
  const sun = route.segments.reduce((sum, s) => sum + (s.sun_seconds ?? 0), 0);
  const unknown = route.segments.reduce((sum, s) => sum + s.unknown_seconds, 0);
  const unknownPct = Math.round((unknown / total) * 100);
  return { sunPct: unknownPct >= 100 ? null : Math.round((sun / total) * 100), unknownPct };
}
