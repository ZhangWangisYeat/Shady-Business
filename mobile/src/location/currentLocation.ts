import * as Location from 'expo-location';
import type { Coordinate } from '../api/types';
import { meters } from '../navigation/progress';

const CAMPUS_CENTER: Coordinate = [-118.4452, 34.0689];
// the backend's walking graph covers 1400 m around campus center, so past
// this the route call would fail anyway with a much less helpful error.
const CAMPUS_RADIUS_M = 1500;
const FIX_TIMEOUT_MS = 10000;

export class LocationUnavailable extends Error {}

// one fix, not a watcher, because planning only needs "where am i right now"
// and AGENTS.md says not to keep tracking location when we aren't navigating.
export async function currentCoordinate(): Promise<Coordinate> {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) throw new LocationUnavailable('Location permission denied. Choose a starting point to preview routes instead.');
  // asking for a brand new fix every time made each recalculation (even a
  // temperature tap) sit for 5-10 s, so a fix from the last minute that's good
  // to 50 m is reused. walking speed means you've moved under ~80 m since.
  const recent = await Location.getLastKnownPositionAsync({ maxAge: 60_000, requiredAccuracy: 50 });
  const fix = recent ?? await Promise.race([
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
    new Promise<never>((_, reject) => setTimeout(() => reject(new LocationUnavailable('Could not get your location. Try again outside, or choose a starting point to preview routes.')), FIX_TIMEOUT_MS)),
  ]);
  const here: Coordinate = [fix.coords.longitude, fix.coords.latitude];
  if (meters(here, CAMPUS_CENTER) > CAMPUS_RADIUS_M) {
    throw new LocationUnavailable("You're not on the UCLA campus, so walking from your location isn't available. Choose a starting point to preview routes.");
  }
  return here;
}
