import React, { useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, View, Text } from 'react-native';
import Mapbox, { Camera, MapView, ShapeSource, LineLayer, CircleLayer, PointAnnotation } from '@rnmapbox/maps';
import type { Coordinate, Place, Route } from '../api/types';
import { boundsOf, revealSegments } from './routeDrawing';
import { COLORS } from '../theme';

const CENTER: Coordinate = [-118.4452, 34.0689];
const TOKEN = process.env.EXPO_PUBLIC_MAPBOX_TOKEN;
if (TOKEN?.startsWith('pk.')) Mapbox.setAccessToken(TOKEN);

const DRAW_MS = 900;
// cycling the dash pattern is the usual mapbox "marching ants" trick, which
// reads as "working on it" without needing a real progress number.
const DASH_FRAMES = [[0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5]];

type Props = {
  routes: Route[];
  activeMode: Route['mode'] | null;
  origin: Place | null;
  destination: Place | null;
  position?: Coordinate | null;
  navigating: boolean;
  calculating: boolean;
  insets: { top: number; bottom: number };
};

const canonical = (r: Route) => r.same_as ?? r.id;

export function ShadyMap({ routes, activeMode, origin, destination, position, navigating, calculating, insets }: Props) {
  const active = routes.find(r => r.mode === activeMode) ?? null;
  const [drawn, setDrawn] = useState(1);
  const [dash, setDash] = useState(0);

  // replay the draw-in whenever a different path becomes the active one
  const activeKey = active ? canonical(active) + active.geometry.coordinates.length : '';
  useEffect(() => {
    if (!active) return;
    setDrawn(0);
    const started = Date.now();
    let frame = requestAnimationFrame(function tick() {
      const t = Math.min(1, (Date.now() - started) / DRAW_MS);
      setDrawn(1 - (1 - t) ** 3);
      if (t < 1) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [activeKey]);

  const searching = calculating && !!origin && !!destination;
  useEffect(() => {
    if (!searching) return;
    const timer = setInterval(() => setDash(d => (d + 1) % DASH_FRAMES.length), 70);
    return () => clearInterval(timer);
  }, [searching]);

  const activeShape = useMemo(() => ({ type: 'FeatureCollection', features: active ? revealSegments(active.segments, drawn) : [] }), [active, drawn]);
  const alternatives = useMemo(() => {
    const seen = new Set(active ? [canonical(active)] : []);
    const lines = routes.filter(r => { const key = canonical(r); if (seen.has(key)) return false; seen.add(key); return true; });
    return { type: 'FeatureCollection', features: lines.map((r, i) => ({ type: 'Feature', id: i, properties: {}, geometry: r.geometry })) };
  }, [routes, active]);
  const ends = useMemo(() => ({
    type: 'FeatureCollection',
    features: [origin && { place: origin, role: 'origin' }, destination && { place: destination, role: 'destination' }]
      .filter(Boolean).map((e: any, i) => ({ type: 'Feature', id: i, properties: { role: e.role }, geometry: { type: 'Point', coordinates: e.place.coordinate } })),
  }), [origin, destination]);
  const searchLine = useMemo(() => origin && destination ? {
    type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [origin.coordinate, destination.coordinate] },
  } : null, [origin, destination]);

  const padding = { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24, paddingLeft: 40, paddingRight: 40 };
  const fitPoints = active ? active.geometry.coordinates : origin && destination ? [origin.coordinate, destination.coordinate] : null;
  const view = navigating && position
    ? { centerCoordinate: position, zoomLevel: 17, pitch: 50 }
    : fitPoints
      ? { bounds: { ...boundsOf(fitPoints), ...padding }, pitch: 0 }
      : { centerCoordinate: (origin ?? destination)?.coordinate ?? CENTER, zoomLevel: origin || destination ? 16 : 15, pitch: 0, padding };
  // the sheet changes height right after routes arrive, and the Camera
  // component kept the fit it made with the old, shorter sheet (route hidden
  // behind it). setting the camera ourselves whenever the view changes re-fits.
  const camera = useRef<Camera>(null);
  const viewKey = JSON.stringify(view);
  useEffect(() => { camera.current?.setCamera({ ...view, animationDuration: 650 }); }, [viewKey]);

  if (!TOKEN || !TOKEN.startsWith('pk.')) return (
    <View style={styles.missing}><Text style={styles.missingText}>Set EXPO_PUBLIC_MAPBOX_TOKEN to display the real UCLA map.</Text></View>
  );

  return <MapView
    style={StyleSheet.absoluteFill} styleURL="mapbox://styles/mapbox/standard"
    scaleBarEnabled={false} compassEnabled compassPosition={{ top: insets.top + 8, right: 12 }}
    // the mapbox logo and attribution are required to stay visible, and the
    // default bottom corners are hidden under the sheet, so they ride above it.
    logoPosition={{ bottom: insets.bottom + 6, left: 10 }} attributionPosition={{ bottom: insets.bottom + 6, right: 10 }}
  >
    <Camera ref={camera} defaultSettings={{ centerCoordinate: CENTER, zoomLevel: 15 }} />
    {searching && !active && searchLine && <ShapeSource id="shady-searching" shape={searchLine as any}>
      <LineLayer id="shady-searching-line" style={{ lineColor: COLORS.ink, lineWidth: 4, lineOpacity: 0.85, lineCap: 'butt', lineDasharray: DASH_FRAMES[dash] }} />
    </ShapeSource>}
    <ShapeSource id="shady-alternatives" shape={alternatives as any}>
      <LineLayer id="shady-alternatives-line" style={{ lineColor: '#9A9A9A', lineWidth: 5, lineOpacity: 0.8, lineCap: 'round', lineJoin: 'round' }} />
    </ShapeSource>
    <ShapeSource id="shady-route" shape={activeShape as any}>
      <LineLayer id="shady-outline" style={{ lineColor: '#ffffff', lineWidth: 10, lineOpacity: .95, lineCap: 'round', lineJoin: 'round' }} />
      <LineLayer id="shady-color" style={{ lineWidth: 6, lineOpacity: .98, lineCap: 'round', lineJoin: 'round', lineColor:
        ['match', ['get', 'shade'], 'shade', '#27A87A', 'sun', '#F29A38', '#1A1A1A'] as any }} />
    </ShapeSource>
    <ShapeSource id="shady-ends" shape={ends as any}>
      <CircleLayer id="shady-ends-circle" style={{
        circleRadius: 8, circleStrokeWidth: 3,
        circleColor: ['match', ['get', 'role'], 'origin', '#ffffff', COLORS.ink] as any,
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
  dot: { width: 18, height: 18, borderRadius: 9, backgroundColor: '#356FED', borderColor: '#fff', borderWidth: 3 },
});
