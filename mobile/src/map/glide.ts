import type { Coordinate } from '../api/types';
import { meters } from '../navigation/progress';

// gps fixes come about once a second, and jumping the dot to each one made it
// hop. instead it glides from where it is to the new fix over about the time
// until the next one, so by the time a fix lands the dot is just arriving.
export type Glide = { from: Coordinate; to: Coordinate; start: number; duration: number };

const MIN_MS = 300;
const MAX_MS = 1200;
// past this the dot teleports, because sliding 50 m across buildings (a new
// fix after the gps dropped out, say) looks worse than just appearing there
const JUMP_M = 40;

export function glidePoint(glide: Glide, now: number): Coordinate {
  const t = Math.max(0, Math.min(1, (now - glide.start) / glide.duration));
  return [glide.from[0] + (glide.to[0] - glide.from[0]) * t, glide.from[1] + (glide.to[1] - glide.from[1]) * t];
}

export const glideLeft = (glide: Glide | null, now: number) => (glide ? Math.max(0, glide.start + glide.duration - now) : 0);

// picks up from wherever the dot is right now, even mid-glide, so a fix that
// arrives early doesn't make it snap back to the last one first
export function nextGlide(previous: Glide | null, to: Coordinate, now: number): Glide {
  if (!previous) return { from: to, to, start: now, duration: MIN_MS };
  const from = glidePoint(previous, now);
  if (meters(from, to) > JUMP_M) return { from: to, to, start: now, duration: MIN_MS };
  return { from, to, start: now, duration: Math.max(MIN_MS, Math.min(MAX_MS, now - previous.start)) };
}
