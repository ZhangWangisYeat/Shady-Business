import { useEffect, useState } from 'react';
import { Platform } from 'react-native';
import * as Location from 'expo-location';

// android only sends a reading after the phone turns ~2 degrees, so a phone held
// still pointing north sends nothing at first. a random direction is only for
// emulators, which may never send one; a real phone just waits for its first.
const NO_SENSOR_MS = 2000;
const constants = Platform.constants as { Fingerprint?: string; Model?: string };
const IS_EMULATOR = Platform.OS === 'android' && /generic|emulator|sdk_gphone/i.test(`${constants.Fingerprint ?? ''} ${constants.Model ?? ''}`);
// the compass wobbles 5-10 degrees between readings while you turn or walk, and
// sending each one straight to the map shook the dot and the whole map with it.
// so the shown heading eases toward the latest reading on its own clock: every
// tick it closes this share of the gap, which settles in about half a second.
const TICK_MS = 50;
const EASE = 0.18;
// the map only hears about changes this big, at most this often, because each
// one is a camera move
const MIN_CHANGE_DEG = 2;
const PUBLISH_MS = 100;

// signed shortest turn from a to b, so 350 -> 10 is +20 and not -340
export const angleDelta = (a: number, b: number) => ((b - a + 540) % 360) - 180;

// one tick of the easing. it goes the short way round, so 350 -> 10 passes
// through north instead of spinning all the way back through south.
export const easeAngle = (from: number, to: number, share = EASE) => (from + angleDelta(from, to) * share + 360) % 360;

// compass direction the phone is facing, degrees clockwise from north. only
// runs while the blue dot is on screen, and stops with it.
export function useHeading(enabled: boolean): number | null {
  const [heading, setHeading] = useState<number | null>(null);
  useEffect(() => {
    if (!enabled) { setHeading(null); return; }
    let cancelled = false;
    let latest: number | null = null;
    let shown: number | null = null;
    let published: number | null = null;
    let publishedAt = 0;
    let timer: ReturnType<typeof setInterval> | null = null;
    let subscription: Location.LocationSubscription | null = null;

    const publish = (value: number, settled: boolean) => {
      const now = Date.now();
      const moved = published === null || Math.abs(angleDelta(published, value)) >= MIN_CHANGE_DEG;
      // the last step of a turn always goes out, so the beam lands exactly where
      // the phone points instead of stopping up to 2 degrees short
      if ((moved && now - publishedAt >= PUBLISH_MS) || (settled && published !== value)) {
        published = value; publishedAt = now;
        if (!cancelled) setHeading(Math.round(value));
      }
    };
    // the easing keeps running after android stops sending (it stops once you
    // stop turning), which is what used to leave the beam short of the phone
    const tick = () => {
      if (latest === null) return;
      shown = shown === null ? latest : easeAngle(shown, latest);
      const settled = Math.abs(angleDelta(shown, latest)) < 0.5;
      if (settled) shown = latest;
      publish(shown, settled);
      if (settled && timer) { clearInterval(timer); timer = null; }
    };
    const take = (raw: number) => {
      latest = raw;
      if (!timer) { tick(); timer = setInterval(tick, TICK_MS); }
    };

    const fallback = IS_EMULATOR ? setTimeout(() => {
      if (latest === null && !cancelled) take(Math.round(Math.random() * 359));
    }, NO_SENSOR_MS) : undefined;
    Location.watchHeadingAsync(reading => {
      // trueHeading is -1 until the phone knows where it is; magnetic north is
      // within a dozen degrees of true north in LA, close enough for a beam
      const raw = reading.trueHeading >= 0 ? reading.trueHeading : reading.magHeading;
      if (cancelled || raw == null || raw < 0) return;
      take(raw);
    }).then(sub => { if (cancelled) sub.remove(); else subscription = sub; }).catch(() => {
      // no compass at all: on an emulator the fallback gives it a direction
    });
    return () => {
      cancelled = true;
      if (fallback) clearTimeout(fallback);
      if (timer) clearInterval(timer);
      subscription?.remove();
    };
  }, [enabled]);
  return heading;
}
