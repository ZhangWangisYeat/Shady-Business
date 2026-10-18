import { useEffect, useState } from 'react';
import { Platform } from 'react-native';
import * as Location from 'expo-location';
import type { Coordinate } from '../api/types';

// android only sends a reading after the phone turns ~2 degrees, so a phone held
// still pointing north sends nothing at first. a random direction is only for
// emulators, which may never send one; a real phone just waits for its first.
const NO_SENSOR_MS = 2000;
const constants = Platform.constants as { Fingerprint?: string; Model?: string };
const IS_EMULATOR = Platform.OS === 'android' && /generic|emulator|sdk_gphone/i.test(`${constants.Fingerprint ?? ''} ${constants.Model ?? ''}`);
// readings wobble a little even when the phone is still, and every change
// re-renders the map
const MIN_CHANGE_DEG = 3;

// signed shortest turn from a to b, so 350 -> 10 is +20 and not -340
export const angleDelta = (a: number, b: number) => ((b - a + 540) % 360) - 180;

export function bearing(from: Coordinate, to: Coordinate): number {
  const mid = Math.cos(((from[1] + to[1]) / 2) * Math.PI / 180);
  const dx = (to[0] - from[0]) * mid, dy = to[1] - from[1];
  return (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
}

// compass direction the phone is facing, degrees clockwise from north. only
// runs while the blue dot is on screen, and stops with it.
export function useHeading(enabled: boolean): number | null {
  const [heading, setHeading] = useState<number | null>(null);
  useEffect(() => {
    if (!enabled) { setHeading(null); return; }
    let cancelled = false;
    let heard = false;
    let subscription: Location.LocationSubscription | null = null;
    const fallback = IS_EMULATOR ? setTimeout(() => {
      if (!heard && !cancelled) setHeading(Math.round(Math.random() * 359));
    }, NO_SENSOR_MS) : undefined;
    Location.watchHeadingAsync(reading => {
      // trueHeading is -1 until the phone knows where it is; magnetic north is
      // within a dozen degrees of true north in LA, close enough for a beam
      const raw = reading.trueHeading >= 0 ? reading.trueHeading : reading.magHeading;
      if (cancelled || raw == null || raw < 0) return;
      heard = true;
      // jump straight to each reading. easing toward it only moved part of the
      // way per reading, and since android stops sending once you stop turning,
      // the beam was left 10-20 degrees short of where the phone pointed.
      setHeading(prev => (prev === null || Math.abs(angleDelta(prev, raw)) >= MIN_CHANGE_DEG ? raw : prev));
    }).then(sub => { if (cancelled) sub.remove(); else subscription = sub; }).catch(() => {
      // no compass at all: on an emulator the fallback gives it a direction
    });
    return () => { cancelled = true; if (fallback) clearTimeout(fallback); subscription?.remove(); };
  }, [enabled]);
  return heading;
}
