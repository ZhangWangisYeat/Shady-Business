import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Dimensions, StyleSheet, View, Text, TouchableOpacity } from 'react-native';
import Mapbox, { Camera, MapView, ShapeSource, LineLayer, CircleLayer, SymbolLayer, Images, type MapState } from '@rnmapbox/maps';
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
const BEAM = require('./heading-beam.png');

type Props = {
  routes: Route[];
  activeMode: Route['mode'] | null;
  origin: Place | null;
  originIsCurrent?: boolean;
  destinationIsCurrent?: boolean;
  destination: Place | null;
  position?: Coordinate | null;
  navigating: boolean;
  calculating: boolean;
  insets: { top: number; bottom: number };
  // fires when the route has finished drawing, so the sheet can wait for it
  onDrawn?: () => void;
  // which way the blue dot is facing, degrees clockwise from north
  heading?: number | null;
};


const canonical = (r: Route) => r.same_as ?? r.id;

export function ShadyMap({ routes, activeMode, origin, originIsCurrent = false, destination, destinationIsCurrent = false, position, navigating, calculating, insets, onDrawn, heading = null }: Props) {
  const active = routes.find(r => r.mode === activeMode) ?? null;
  const [drawn, setDrawn] = useState(1);
  const [pulse, setPulse] = useState(0);
  const drawnCallback = useRef(onDrawn);
  drawnCallback.current = onDrawn;
  const [size, setSize] = useState(() => { const { width, height } = Dimensions.get('window'); return { width, height }; });
  const [mapBearing, setMapBearing] = useState(0);
  // zoomed: close up and following you. faceUp: the map turns with you.
  const [zoomed, setZoomed] = useState(false);
  const [faceUp, setFaceUp] = useState(false);

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
    features: [origin && !originIsCurrent && { place: origin, role: 'origin' }, destination && !destinationIsCurrent && { place: destination, role: 'destination' }]
      .filter(Boolean).map((e: any, i) => ({ type: 'Feature', id: i, properties: { role: e.role }, geometry: { type: 'Point', coordinates: e.place.coordinate } })),
  }), [origin, originIsCurrent, destination, destinationIsCurrent]);
  // one blue dot for "you": the gps or demo position while walking, otherwise
  // the fix the route was planned from
  const you = navigating && position ? position
    : originIsCurrent && origin ? origin.coordinate
    : destinationIsCurrent && destination ? destination.coordinate : null;
  const youShape = useMemo(() => you ? { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: you } } : null, [you?.[0], you?.[1]]);

  const padding = { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24, paddingLeft: 40, paddingRight: 40 };
  const fitPoints = active ? active.geometry.coordinates : origin && destination ? [origin.coordinate, destination.coordinate] : null;
  // the overview is always north up because fitCamera's math assumes it, and it
  // sets all four padding edges since mapbox keeps any edge you leave out
  const overview = fitPoints
    ? { ...fitCamera(fitPoints, size, padding), pitch: 0, heading: 0, padding }
    : { centerCoordinate: (origin ?? destination)?.coordinate ?? CENTER, zoomLevel: origin || destination ? 16 : 15, pitch: 0, heading: 0, padding };
  const camera = useRef<Camera>(null);
  // every camera call cancels whatever animation is running, and heading
  // updates arrive a frame after a fly-in starts, which killed the zoom (the
  // map only rotated). heading updates wait until the fly-in is done.
  const flyingUntil = useRef(0);
  const flownIn = useRef(false);

  // a walk starts zoomed in on you; a new route or destination starts on the
  // overview. this is the same switch the compass flips.
  useEffect(() => { setZoomed(navigating); setFaceUp(navigating); }, [navigating]);
  useEffect(() => { if (!navigating) { setZoomed(false); setFaceUp(false); } }, [active?.id, destination?.id]);

  const overviewKey = JSON.stringify(overview);
  useEffect(() => {
    if (zoomed) return;
    flownIn.current = false;
    // the sheet changes height a frame after routes arrive, so waiting for
    // layout to settle sends one fit with the final padding instead of two
    const timer = setTimeout(() => camera.current?.setCamera({ ...overview, animationDuration: 650 }), 120);
    return () => clearTimeout(timer);
  }, [zoomed, overviewKey]);

  const youKey = you ? `${you[0]},${you[1]}` : '';
  useEffect(() => {
    if (!zoomed || !you) return;
    if (!flownIn.current) {
      // stepping into the route: close, tilted, facing the way you face
      flownIn.current = true;
      flyingUntil.current = Date.now() + 950;
      camera.current?.setCamera({ centerCoordinate: you, zoomLevel: 18.5, pitch: 45, ...(faceUp && heading !== null ? { heading } : {}), padding, animationDuration: 900 });
      return;
    }
    // after that only the center (and direction) follow you, so a pinch zoom
    // sticks. both go in one call: a separate heading call cancelled the
    // centering animation halfway, which left the dot drifting off center.
    const follow = () => camera.current?.setCamera({ centerCoordinate: you, ...(faceUp && heading !== null ? { heading } : {}), padding, animationDuration: 500 });
    const wait = flyingUntil.current - Date.now();
    if (wait <= 0) { follow(); return; }
    const timer = setTimeout(follow, wait);
    return () => clearTimeout(timer);
  }, [zoomed, youKey, insets.bottom, faceUp, heading]);

  useEffect(() => {
    // zoomed in, the follow effect above already turns the map
    if (zoomed || !faceUp || heading === null) return;
    const wait = flyingUntil.current - Date.now();
    if (wait <= 0) { camera.current?.setCamera({ heading, animationDuration: 300 }); return; }
    const timer = setTimeout(() => camera.current?.setCamera({ heading, animationDuration: 300 }), wait);
    return () => clearTimeout(timer);
  }, [zoomed, faceUp, heading]);

  const tapCompass = () => {
    if (fitPoints && you) {
      // with a route on screen the compass flips between "me, up close" and
      // "the whole route", whether you're planning or walking
      const next = !zoomed;
      if (!next) flyingUntil.current = Date.now() + 700;
      setZoomed(next);
      setFaceUp(next);
      return;
    }
    // no route yet: just heading-up vs north-up
    if (faceUp || heading === null) {
      setFaceUp(false);
      camera.current?.setCamera({ heading: 0, animationDuration: 500 });
    } else setFaceUp(true);
  };
  const cameraChanged = (state: MapState) => {
    const b = state.properties.heading;
    setMapBearing(prev => (Math.abs(prev - b) > 1 ? b : prev));
    // a two finger twist means you want to aim the map yourself
    if (state.gestures.isGestureActive) setFaceUp(false);
  };

  if (!TOKEN || !TOKEN.startsWith('pk.')) return (
    <View style={styles.missing}><Text style={styles.missingText}>Set EXPO_PUBLIC_MAPBOX_TOKEN to display the real UCLA map.</Text></View>
  );

  return <View style={StyleSheet.absoluteFill} pointerEvents="box-none"><MapView
    style={StyleSheet.absoluteFill} styleURL="mapbox://styles/mapbox/standard"
    onLayout={e => setSize({ width: e.nativeEvent.layout.width, height: e.nativeEvent.layout.height })}
    onCameraChanged={cameraChanged}
    // pinch zoom and two finger rotate are mapbox defaults, spelled out so
    // nobody turns them off by accident. the built in compass can only reset
    // north, so ours below replaces it.
    zoomEnabled rotateEnabled scaleBarEnabled={false} compassEnabled={false}
    // the mapbox logo and attribution are required to stay visible, and the
    // default bottom corners are hidden under the sheet, so they ride above it.
    logoPosition={{ bottom: insets.bottom + 6, left: 10 }} attributionPosition={{ bottom: insets.bottom + 6, right: 10 }}
  >
    <Camera ref={camera} defaultSettings={{ centerCoordinate: CENTER, zoomLevel: 15 }} />
    <Images images={{ 'heading-beam': BEAM }} />
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
        circleColor: ['match', ['get', 'role'], 'origin', '#ffffff', COLORS.ink] as any,
        circleStrokeColor: ['match', ['get', 'role'], 'origin', COLORS.ink, '#ffffff'] as any,
      }} />
    </ShapeSource>
    {youShape && <ShapeSource id="shady-you" shape={youShape as any}>
      <SymbolLayer id="shady-you-beam" style={{
        // map alignment keeps the beam on the compass direction as the map
        // rotates or tilts, instead of on the screen
        iconImage: 'heading-beam', iconRotate: heading ?? 0, iconOpacity: heading === null ? 0 : 1, iconRotationAlignment: 'map', iconPitchAlignment: 'map',
        iconAllowOverlap: true, iconIgnorePlacement: true, iconSize: 0.7,
      }} />
      <CircleLayer id="shady-you-dot" style={{ circleRadius: 8, circleColor: COLORS.here, circleStrokeWidth: 3, circleStrokeColor: '#ffffff' }} />
    </ShapeSource>}
  </MapView>
    <TouchableOpacity accessibilityLabel={zoomed ? 'Show the whole route' : 'Zoom in on your location'}
      style={[styles.compass, { top: insets.top + 8 }, (zoomed || faceUp) && styles.compassOn]} onPress={tapCompass}>
      {/* the needle counter-rotates against the map, so red always points at real north */}
      <View style={{ alignItems: 'center', transform: [{ rotate: `${-mapBearing}deg` }] }}>
        <View style={styles.needleNorth} /><View style={styles.needleSouth} />
      </View>
    </TouchableOpacity>
  </View>;
}

const styles = StyleSheet.create({
  missing: { ...StyleSheet.absoluteFill, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.fill, padding: 30 },
  missingText: { textAlign: 'center', color: COLORS.ink, fontSize: 16 },
  compass: { position: 'absolute', right: 12, width: 46, height: 46, borderRadius: 23, backgroundColor: COLORS.ink, alignItems: 'center', justifyContent: 'center', elevation: 6 },
  compassOn: { borderWidth: 2.5, borderColor: COLORS.here },
  needleNorth: { width: 0, height: 0, borderLeftWidth: 6, borderRightWidth: 6, borderBottomWidth: 15, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderBottomColor: '#E5483B' },
  needleSouth: { width: 0, height: 0, borderLeftWidth: 6, borderRightWidth: 6, borderTopWidth: 15, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: '#ffffff' },
});
