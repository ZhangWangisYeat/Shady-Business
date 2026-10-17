import type { Maneuver, RouteStep } from '../api/types';

export const MANEUVER_ICON: Record<Maneuver, string> = {
  depart: '↑', straight: '↑', slight_left: '↖', slight_right: '↗',
  left: '←', right: '→', sharp_left: '↙', sharp_right: '↘', arrive: '◉',
};

// feet and miles because the rest of the app already speaks °F to US users
export function formatDistance(m: number): string {
  const feet = m * 3.28084;
  if (feet < 1000) return `${Math.max(10, Math.round(feet / 10) * 10)} ft`;
  return `${(m / 1609.34).toFixed(1)} mi`;
}

// each step's distance_m is how far you walk after that maneuver, so the step
// you're on is the last one whose start you've already passed, and the "next"
// instruction to show is the one after it.
export function stepProgress(steps: RouteStep[], walkedM: number): { current: number; next: RouteStep | null; toNextM: number } {
  let start = 0;
  for (let i = 0; i < steps.length; i++) {
    const end = start + steps[i].distance_m;
    if (walkedM < end || i === steps.length - 1) {
      return { current: i, next: steps[i + 1] ?? null, toNextM: Math.max(0, end - walkedM) };
    }
    start = end;
  }
  return { current: 0, next: null, toNextM: 0 };
}
