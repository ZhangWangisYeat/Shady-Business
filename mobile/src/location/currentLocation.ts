import * as Location from 'expo-location';
import type { Coordinate } from '../api/types';
import { meters } from '../navigation/progress';

const CAMPUS_CENTER: Coordinate = [-118.4452, 34.0689];
// the backend's walking graph covers 1400 m around campus center, so past
// this the route call would fail anyway with a much less helpful error.
const CAMPUS_RADIUS_M = 1500;
const FIX_TIMEOUT_MS = 10000;
const RECENT_MS = 60_000;

export class LocationUnavailable extends Error {}

// a fix that's on its way (or arrived in the last minute), shared so the
// warm-up below and the route request don't each start their own
let pending: { fix: Promise<Location.LocationObject>; startedAt: number } | null = null;
function freshFix(): Promise<Location.LocationObject> {
  if (!pending || Date.now() - pending.startedAt > RECENT_MS) {
    const fix = Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
    pending = { fix, startedAt: Date.now() };
    fix.catch(() => { if (pending?.fix === fix) pending = null; });
  }
  return pending.fix;
}

// a fresh fix takes a few seconds, and picking a destination used to sit on
// "Finding you" for all of it before the route search even began. so opening a
// search box starts one fix in the background (only if location is already
// allowed; it never asks), and the route request picks it up. it's still one
// fix and not a watcher, because AGENTS.md says not to keep tracking location
// when we aren't navigating.
export async function warmUpLocation(): Promise<void> {
  try {
    if (!(await Location.getForegroundPermissionsAsync()).granted) return;
    if (await Location.getLastKnownPositionAsync({ maxAge: RECENT_MS, requiredAccuracy: 50 })) return;
    void freshFix().catch(() => {});
  } catch { /* warming up is only a head start, so a failure here changes nothing */ }
}

// one fix, not a watcher, because planning only needs "where am i right now"
// and AGENTS.md says not to keep tracking location when we aren't navigating.
export async function currentCoordinate(): Promise<Coordinate> {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) throw new LocationUnavailable('Location permission denied. Choose a starting point to preview routes instead.');
  // asking for a brand new fix every time made each recalculation (even a
  // temperature tap) sit for 5-10 s, so a fix from the last minute that's good
  // to 50 m is reused. walking speed means you've moved under ~80 m since.
  const recent = await Location.getLastKnownPositionAsync({ maxAge: RECENT_MS, requiredAccuracy: 50 });
  const fix = recent ?? await Promise.race([
    freshFix(),
    new Promise<never>((_, reject) => setTimeout(() => reject(new LocationUnavailable('Could not get your location. Try again outside, or choose a starting point to preview routes.')), FIX_TIMEOUT_MS)),
  ]);
  const here: Coordinate = [fix.coords.longitude, fix.coords.latitude];
  if (meters(here, CAMPUS_CENTER) > CAMPUS_RADIUS_M) {
    throw new LocationUnavailable("You're not on the UCLA campus, so walking from your location isn't available. Choose a starting point to preview routes.");
  }
  return here;
}
