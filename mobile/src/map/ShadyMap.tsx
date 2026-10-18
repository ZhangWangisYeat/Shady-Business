import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Dimensions, StyleSheet, View, Text } from 'react-native';
import Mapbox, { Camera, MapView, ShapeSource, LineLayer, CircleLayer, PointAnnotation } from '@rnmapbox/maps';
import type { Coordinate, Place, Route } from '../api/types';
import { revealSegments } from './routeDrawing';
import { fitCamera } from './fitCamera';
import { COLORS } from '../theme';

const CENTER: Coordinate = [-118.4452, 34.0689];
const TOKEN = process.env.EXPO_PUBLIC_MAPBOX_TOKEN;
if (TOKEN?.startsWith('pk.')) Mapbox.setAccessToken(TOKEN);

// the backend answers in well under a second, so the drawing *is* the
// "calculating" moment: longer walks take a little longer to draw, which feels
// like the path is being worked out step by step rather than popping in.
const drawMs = (meters: number) => Math.min(2400, Math.max(1200, 1200 + meters * 1.5));
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const PULSE_MS = 1400;

type Props = {
  routes: Route[];
  activeMode: Route['mode'] | null;
  origin: Place | null;
  originIsCurrent?: boolean;
  destination: Place | null;
  position?: Coordinate | null;
  navigating: boolean;
  calculating: boolean;
  insets: { top: number; bottom: number };
  // fires when the route has finished drawing, so the sheet can wait for it
  onDrawn?: () => void;
};

const canonical = (r: Route) => r.same_as ?? r.id;

export function ShadyMap({ routes, activeMode, origin, originIsCurrent = false, destination, position, navigating, calculating, insets, onDrawn }: Props) {
  const active = routes.find(r => r.mode === activeMode) ?? null;
  const [drawn, setDrawn] = useState(1);
  const [pulse, setPulse] = useState(0);
  const drawnCallback = useRef(onDrawn);
  drawnCallback.current = onDrawn;
  const [size, setSize] = useState(() => { const { width, height } = Dimensions.get('window'); return { width, height }; });

  // keyed on the route object, not its path, so a fresh answer that happens to
  // be the same path (say after a temperature change) still draws and still
  // tells the sheet it's done, otherwise the sheet would wait forever.
  useEffect(() => {
    if (!active) return;
    setDrawn(0);
    const duration = drawMs(active.distance_m);
    const started = Date.now();
    let frame = requestAnimationFrame(function tick() {
      const t = Math.min(1, (Date.now() - started) / duration);
      setDrawn(easeInOut(t));
      if (t < 1) frame = requestAnimationFrame(tick);
      else drawnCallback.current?.();
    });
    return () => cancelAnimationFrame(frame);
  }, [active]);

  // while we wait on the gps fix and the backend, a soft ring pulses out of the
  // start (or the destination, until we know where you are)
  const pulseAt = calculating && !active ? (origin ?? destination) : null;
  useEffect(() => {
    if (!pulseAt) return;
    const started = Date.now();
    const timer = setInterval(() => setPulse(((Date.now() - started) % PULSE_MS) / PULSE_MS), 33);
    return () => clearInterval(timer);
  }, [!!pulseAt]);

  const activeShape = useMemo(() => ({ type: 'FeatureCollection', features: active ? revealSegments(active.segments, drawn) : [] }), [active, drawn]);
  const head = useMemo(() => {
    const features = activeShape.features;
    if (drawn >= 1 || !features.length) return null;
    const line = features[features.length - 1].geometry.coordinates;
    return { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: line[line.length - 1] } };
  }, [activeShape, drawn]);
  const alternatives = useMemo(() => {
    // the other options only show up once the main line has finished drawing
    if (drawn < 1) return { type: 'FeatureCollection', features: [] };
    const seen = new Set(active ? [canonical(active)] : []);
    const lines = routes.filter(r => { const key = canonical(r); if (seen.has(key)) return false; seen.add(key); return true; });
    return { type: 'FeatureCollection', features: lines.map((r, i) => ({ type: 'Feature', id: i, properties: {}, geometry: r.geometry })) };
  }, [routes, active, drawn >= 1]);
  const ends = useMemo(() => ({
    type: 'FeatureCollection',
    features: [origin && { place: origin, role: originIsCurrent ? 'here' : 'origin' }, destination && { place: destination, role: 'destination' }]
      .filter(Boolean).map((e: any, i) => ({ type: 'Feature', id: i, properties: { role: e.role }, geometry: { type: 'Point', coordinates: e.place.coordinate } })),
  }), [origin, originIsCurrent, destination]);

  const padding = { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24, paddingLeft: 40, paddingRight: 40 };
  const fitPoints = active ? active.geometry.coordinates : origin && destination ? [origin.coordinate, destination.coordinate] : null;
  // mapbox keeps viewport padding between camera moves (an edge you leave out
  // keeps its old value), so every view sets all of it.
  const view = navigating && position
    ? { centerCoordinate: position, zoomLevel: 17, pitch: 50, padding }
    : fitPoints
      ? { ...fitCamera(fitPoints, size, padding), pitch: 0, padding }
      : { centerCoordinate: (origin ?? destination)?.coordinate ?? CENTER, zoomLevel: origin || destination ? 16 : 15, pitch: 0, padding };
  // the sheet changes height right after routes arrive, and the Camera
  // component kept the fit it made with the old, shorter sheet (route hidden
  // behind it). setting the camera ourselves whenever the view changes re-fits.
  const camera = useRef<Camera>(null);
  const viewKey = JSON.stringify(view);
  // the sheet grows a frame after routes arrive, so waiting for layout to settle
  // sends one fit with the final padding instead of two back to back.
  useEffect(() => {
    const timer = setTimeout(() => camera.current?.setCamera({ ...view, animationDuration: 650 }), 120);
    return () => clearTimeout(timer);
  }, [viewKey]);

  if (!TOKEN || !TOKEN.startsWith('pk.')) return (
    <View style={styles.missing}><Text style={styles.missingText}>Set EXPO_PUBLIC_MAPBOX_TOKEN to display the real UCLA map.</Text></View>
  );

  return <MapView
    style={StyleSheet.absoluteFill} styleURL="mapbox://styles/mapbox/standard"
    onLayout={e => setSize({ width: e.nativeEvent.layout.width, height: e.nativeEvent.layout.height })}
    scaleBarEnabled={false} compassEnabled compassPosition={{ top: insets.top + 8, right: 12 }}
    // the mapbox logo and attribution are required to stay visible, and the
    // default bottom corners are hidden under the sheet, so they ride above it.
    logoPosition={{ bottom: insets.bottom + 6, left: 10 }} attributionPosition={{ bottom: insets.bottom + 6, right: 10 }}
  >
    <Camera ref={camera} defaultSettings={{ centerCoordinate: CENTER, zoomLevel: 15 }} />
    {pulseAt && <ShapeSource id="shady-pulse" shape={{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: pulseAt.coordinate } } as any}>
      <CircleLayer id="shady-pulse-ring" style={{
        circleRadius: 10 + 26 * pulse, circleColor: originIsCurrent && pulseAt === origin ? COLORS.here : COLORS.ink,
        circleOpacity: 0.28 * (1 - pulse), circleStrokeWidth: 1.5, circleStrokeColor: originIsCurrent && pulseAt === origin ? COLORS.here : COLORS.ink,
        circleStrokeOpacity: 0.6 * (1 - pulse),
      }} />
    </ShapeSource>}
    <ShapeSource id="shady-alternatives" shape={alternatives as any}>
      <LineLayer id="shady-alternatives-line" style={{ lineColor: '#9A9A9A', lineWidth: 5, lineOpacity: 0.8, lineCap: 'round', lineJoin: 'round' }} />
    </ShapeSource>
    <ShapeSource id="shady-route" shape={activeShape as any}>
      <LineLayer id="shady-outline" style={{ lineColor: '#ffffff', lineWidth: 10, lineOpacity: .95, lineCap: 'round', lineJoin: 'round' }} />
      <LineLayer id="shady-color" style={{ lineWidth: 6, lineOpacity: .98, lineCap: 'round', lineJoin: 'round', lineColor:
        ['match', ['get', 'shade'], 'shade', COLORS.shade, 'sun', COLORS.sun, COLORS.unknown] as any }} />
    </ShapeSource>
    {head && <ShapeSource id="shady-head" shape={head as any}>
      <CircleLayer id="shady-head-dot" style={{ circleRadius: 6, circleColor: COLORS.unknown, circleStrokeWidth: 2.5, circleStrokeColor: '#ffffff' }} />
    </ShapeSource>}
    <ShapeSource id="shady-ends" shape={ends as any}>
      <CircleLayer id="shady-ends-circle" style={{
        circleRadius: 8, circleStrokeWidth: 3,
        circleColor: ['match', ['get', 'role'], 'origin', '#ffffff', 'here', COLORS.here, COLORS.ink] as any,
        circleStrokeColor: ['match', ['get', 'role'], 'origin', COLORS.ink, '#ffffff'] as any,
      }} />
    </ShapeSource>
    {position && <PointAnnotation id="current-position" coordinate={position}>
      <View style={styles.dot} />
    </PointAnnotation>}
  </MapView>;
}

const styles = StyleSheet.create({
  missing: { ...StyleSheet.absoluteFill, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.fill, padding: 30 },
  missingText: { textAlign: 'center', color: COLORS.ink, fontSize: 16 },
  dot: { width: 18, height: 18, borderRadius: 9, backgroundColor: COLORS.here, borderColor: '#fff', borderWidth: 3 },
});
