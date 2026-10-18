import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Dimensions, StyleSheet, View, Text, TouchableOpacity } from 'react-native';
import Mapbox, { Camera, MapView, ShapeSource, LineLayer, CircleLayer, SymbolLayer, Images, type MapState } from '@rnmapbox/maps';
import type { Coordinate, Place, Route } from '../api/types';
import { revealLine, revealSegments } from './routeDrawing';
import { fitCamera } from './fitCamera';
import { glideLeft, glidePoint, nextGlide, type Glide } from './glide';
import { angleDelta, useHeading } from '../location/heading';
import { COLORS } from '../theme';

const CENTER: Coordinate = [-118.4452, 34.0689];
const TOKEN = process.env.EXPO_PUBLIC_MAPBOX_TOKEN;
if (TOKEN?.startsWith('pk.')) Mapbox.setAccessToken(TOKEN);

// this used to run 1.2-2.4 s because the backend answered in well under a
// second, so the drawing stood in for the calculating. the backend takes about
// 2 s now (mostly the shadow model) and the cards wait for the drawing, so a
// long draw-in only stacked more waiting on top. it's a short finishing touch now.
const drawMs = (meters: number) => Math.min(1000, Math.max(600, 600 + meters * 0.5));
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
  // asks for a gps fix when the compass is tapped before we know where you are
  onLocate?: () => Promise<Coordinate | null>;
};


const canonical = (r: Route) => r.same_as ?? r.id;

export function ShadyMap({ routes, activeMode, origin, originIsCurrent = false, destination, destinationIsCurrent = false, position, navigating, calculating, insets, onDrawn, onLocate }: Props) {
  // which way the phone faces. it lives here rather than in the app screen
  // because every reading used to re-render the whole screen, and buttons that
  // got re-rendered mid-tap lost the tap.
  const heading = useHeading(true);
  const active = routes.find(r => r.mode === activeMode) ?? null;
  const [located, setLocated] = useState<Coordinate | null>(null);
  const [size, setSize] = useState(() => { const { width, height } = Dimensions.get('window'); return { width, height }; });
  // the needle turns through an animated value instead of state, because the
  // camera reports every frame while the map turns and re-rendering the whole
  // map that often made it (and every button) sluggish
  const needleTurn = useRef(new Animated.Value(0)).current;
  const mapBearing = useRef(0);
  // zoomed: close up and following you. faceUp: the map turns with you.
  const [zoomed, setZoomed] = useState(false);
  const [faceUp, setFaceUp] = useState(false);

  // while we wait on the gps fix and the backend, a soft ring pulses out of the
  // start (or the destination, until we know where you are)
  const pulseAt = calculating && !active ? (origin ?? destination) : null;

  const ends = useMemo(() => ({
    type: 'FeatureCollection',
    features: [origin && !originIsCurrent && { place: origin, role: 'origin' }, destination && !destinationIsCurrent && { place: destination, role: 'destination' }]
      .filter(Boolean).map((e: any, i) => ({ type: 'Feature', id: i, properties: { role: e.role }, geometry: { type: 'Point', coordinates: e.place.coordinate } })),
  }), [origin, originIsCurrent, destination, destinationIsCurrent]);
  // one blue dot for "you": the gps or demo position while walking, otherwise
  // the fix the route was planned from
  const you = navigating && position ? position
    : originIsCurrent && origin ? origin.coordinate
    : destinationIsCurrent && destination ? destination.coordinate : located;

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
  // worked out during render, not in an effect, because the dot (a child)
  // starts gliding in its own effect, and child effects run before the parent's
  const glide = useRef<Glide | null>(null);
  const glideKey = useRef('');
  if (youKey !== glideKey.current) {
    glideKey.current = youKey;
    glide.current = you ? nextGlide(glide.current, you, Date.now()) : null;
  }
  useEffect(() => {
    if (!zoomed || !you) return;
    if (!flownIn.current) {
      // stepping into the route: close, tilted, facing the way you face
      flownIn.current = true;
      flyingUntil.current = Date.now() + 950;
      camera.current?.setCamera({ centerCoordinate: you, zoomLevel: fitPoints ? 18.5 : 17, pitch: fitPoints ? 45 : 0, ...(faceUp && heading !== null ? { heading } : {}), padding, animationDuration: 900 });
      return;
    }
    // after that only the center (and direction) follow you, so a pinch zoom
    // sticks. both go in one call: a separate heading call cancelled the
    // centering animation halfway, which left the dot drifting off center.
    // a straight line timed to land with the dot's glide. every camera call
    // cancels the last one, and heading steps come every 100 ms while you turn,
    // so an ease that restarted each time stuttered back and forth. a straight
    // line toward the same point just carries on from wherever it got to.
    const follow = () => camera.current?.setCamera({
      centerCoordinate: you, ...(faceUp && heading !== null ? { heading } : {}), padding,
      animationDuration: Math.max(250, glideLeft(glide.current, Date.now())), animationMode: 'linearTo',
    });
    const wait = flyingUntil.current - Date.now();
    if (wait <= 0) { follow(); return; }
    const timer = setTimeout(follow, wait);
    return () => clearTimeout(timer);
  }, [zoomed, youKey, insets.bottom, faceUp, heading]);

  useEffect(() => {
    // zoomed in, the follow effect above already turns the map
    if (zoomed || !faceUp || heading === null) return;
    const wait = flyingUntil.current - Date.now();
    const turn = () => camera.current?.setCamera({ heading, animationDuration: 250, animationMode: 'linearTo' });
    if (wait <= 0) { turn(); return; }
    const timer = setTimeout(turn, wait);
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
    // no route yet: the compass just takes you to where you are, and back out
    if (zoomed) {
      flyingUntil.current = Date.now() + 700;
      setZoomed(false); setFaceUp(false);
      return;
    }
    setZoomed(true); setFaceUp(false);
    if (!you) void onLocate?.().then(coordinate => { if (coordinate) setLocated(coordinate); else setZoomed(false); });
  };
  const cameraChanged = (state: MapState) => {
    const b = state.properties.heading;
    if (Math.abs(angleDelta(mapBearing.current, b)) > 0.5) { mapBearing.current = b; needleTurn.setValue(-b); }
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
    {pulseAt && <Pulse at={pulseAt.coordinate} color={originIsCurrent && pulseAt === origin ? COLORS.here : COLORS.ink} />}
    <RouteLayers routes={routes} active={active} onDrawn={onDrawn} />
    <ShapeSource id="shady-ends" shape={ends as any}>
      <CircleLayer id="shady-ends-circle" style={{
        circleRadius: 8, circleStrokeWidth: 3,
        circleColor: ['match', ['get', 'role'], 'origin', '#ffffff', COLORS.ink] as any,
        circleStrokeColor: ['match', ['get', 'role'], 'origin', COLORS.ink, '#ffffff'] as any,
      }} />
    </ShapeSource>
    {you && <YouDot glide={glide} version={youKey} heading={heading} />}
  </MapView>
    <TouchableOpacity accessibilityLabel={zoomed ? 'Show the whole route' : 'Zoom in on your location'}
      style={[styles.compass, { top: insets.top + 8 }, (zoomed || faceUp) && styles.compassOn]} onPress={tapCompass}>
      {/* the needle counter-rotates against the map, so red always points at real north.
          it's drawn from border triangles rather than an image so it stays sharp at any density. */}
      <Animated.View style={[styles.needle, { transform: [{ rotate: needleTurn.interpolate({ inputRange: [-360, 360], outputRange: ['-360deg', '360deg'] }) }] }]}>
        <View style={styles.needleNorth} /><View style={styles.needleSouth} />
        <View style={styles.needlePin} />
      </Animated.View>
    </TouchableOpacity>
  </View>;
}

// the waiting ring. its own component so the 30 fps pulse only re-renders the
// ring and not the whole map.
function Pulse({ at, color }: { at: Coordinate; color: string }) {
  const [pulse, setPulse] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setPulse(((Date.now() - started) % PULSE_MS) / PULSE_MS), 33);
    return () => clearInterval(timer);
  }, []);
  return <ShapeSource id="shady-pulse" shape={{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: at } } as any}>
    <CircleLayer id="shady-pulse-ring" style={{
      circleRadius: 10 + 26 * pulse, circleColor: color, circleOpacity: 0.28 * (1 - pulse),
      circleStrokeWidth: 1.5, circleStrokeColor: color, circleStrokeOpacity: 0.6 * (1 - pulse),
    }} />
  </ShapeSource>;
}

// the routes and their draw-in. the draw updates every frame, so it lives in
// its own component and only these three sources re-render while it runs.
function RouteLayers({ routes, active, onDrawn }: { routes: Route[]; active: Route | null; onDrawn?: () => void }) {
  // each draw progress remembers which route(s) it belongs to. a plain number
  // still said "fully drawn" from the last route on the first frame of a new
  // one, so the whole new line flashed on screen before the draw-in started.
  const [draw, setDraw] = useState<{ route: Route | null; t: number }>({ route: null, t: 0 });
  const [altDraw, setAltDraw] = useState<{ routes: Route[] | null; t: number }>({ routes: null, t: 0 });
  const drawn = draw.route === active ? draw.t : 0;
  const altDrawn = altDraw.routes === routes ? altDraw.t : 0;
  const drawnCallback = useRef(onDrawn);
  drawnCallback.current = onDrawn;

  // keyed on the route object, not its path, so a fresh answer that happens to
  // be the same path (say after a temperature change) still draws and still
  // tells the sheet it's done, otherwise the sheet would wait forever.
  useEffect(() => {
    if (!active) return;
    const route = active;
    setDraw({ route, t: 0 });
    const duration = drawMs(route.distance_m);
    const started = Date.now();
    let frame = requestAnimationFrame(function tick() {
      const t = Math.min(1, (Date.now() - started) / duration);
      setDraw({ route, t: easeInOut(t) });
      if (t < 1) frame = requestAnimationFrame(tick);
      else drawnCallback.current?.();
    });
    return () => cancelAnimationFrame(frame);
  }, [active]);

  // the other routes draw in alongside the chosen one, but only when a new set
  // of routes arrives. picking a different card redraws just that route, and
  // the rest stay where they are.
  useEffect(() => {
    if (!routes.length) return;
    const set = routes;
    setAltDraw({ routes: set, t: 0 });
    const duration = drawMs(active?.distance_m ?? 0);
    const started = Date.now();
    let frame = requestAnimationFrame(function tick() {
      const t = Math.min(1, (Date.now() - started) / duration);
      setAltDraw({ routes: set, t: easeInOut(t) });
      if (t < 1) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [routes]);

  const activeShape = useMemo(() => ({ type: 'FeatureCollection', features: active ? revealSegments(active.segments, drawn) : [] }), [active, drawn]);
  const head = useMemo(() => {
    const features = activeShape.features;
    if (drawn >= 1 || !features.length) return null;
    const line = features[features.length - 1].geometry.coordinates;
    return { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: line[line.length - 1] } };
  }, [activeShape, drawn]);
  const alternatives = useMemo(() => {
    const seen = new Set(active ? [canonical(active)] : []);
    const lines = routes.filter(r => { const key = canonical(r); if (seen.has(key)) return false; seen.add(key); return true; });
    const features = lines.map((r, i) => ({ type: 'Feature', id: i, properties: {}, geometry: { type: 'LineString', coordinates: revealLine(r.geometry.coordinates, altDrawn) } }));
    return { type: 'FeatureCollection', features: features.filter(f => f.geometry.coordinates.length >= 2) };
  }, [routes, active, altDrawn]);

  return <>
    <ShapeSource id="shady-alternatives" shape={alternatives as any}>
      {/* faded so the chosen route reads as the one you're taking, even mid-draw */}
      <LineLayer id="shady-alternatives-line" style={{ lineColor: '#8E8E8E', lineWidth: 4.5, lineOpacity: 0.45, lineCap: 'round', lineJoin: 'round' }} />
    </ShapeSource>
    <ShapeSource id="shady-route" shape={activeShape as any}>
      <LineLayer id="shady-outline" style={{ lineColor: '#ffffff', lineWidth: 10, lineOpacity: .95, lineCap: 'round', lineJoin: 'round' }} />
      <LineLayer id="shady-color" style={{ lineWidth: 6, lineOpacity: .98, lineCap: 'round', lineJoin: 'round', lineColor:
        ['match', ['get', 'shade'], 'shade', COLORS.shade, 'sun', COLORS.sun, COLORS.unknown] as any }} />
    </ShapeSource>
    {head && <ShapeSource id="shady-head" shape={head as any}>
      <CircleLayer id="shady-head-dot" style={{ circleRadius: 6, circleColor: COLORS.unknown, circleStrokeWidth: 2.5, circleStrokeColor: '#ffffff' }} />
    </ShapeSource>}
  </>;
}

// the blue "you" dot. it's its own component so the glide, which updates every
// frame, only re-renders the dot and not the whole map.
function YouDot({ glide, version, heading }: { glide: React.MutableRefObject<Glide | null>; version: string; heading: number | null }) {
  const [point, setPoint] = useState<Coordinate | null>(() => (glide.current ? glidePoint(glide.current, Date.now()) : null));
  useEffect(() => {
    let frame = requestAnimationFrame(function tick() {
      const current = glide.current;
      if (!current) return;
      setPoint(glidePoint(current, Date.now()));
      if (glideLeft(current, Date.now()) > 0) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [version]);
  if (!point) return null;
  return <ShapeSource id="shady-you" shape={{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: point } } as any}>
    <SymbolLayer id="shady-you-beam" style={{
      // map alignment keeps the beam on the compass direction as the map
      // rotates or tilts, instead of on the screen
      iconImage: 'heading-beam', iconRotate: heading ?? 0, iconOpacity: heading === null ? 0 : 1, iconRotationAlignment: 'map', iconPitchAlignment: 'map',
      iconAllowOverlap: true, iconIgnorePlacement: true, iconSize: 0.7,
    }} />
    <CircleLayer id="shady-you-dot" style={{ circleRadius: 8, circleColor: COLORS.here, circleStrokeWidth: 3, circleStrokeColor: '#ffffff' }} />
  </ShapeSource>;
}

const styles = StyleSheet.create({
  missing: { ...StyleSheet.absoluteFill, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.fill, padding: 30 },
  missingText: { textAlign: 'center', color: COLORS.ink, fontSize: 16 },
  // no overflow: 'hidden' here, and the border is always 2.5 wide (just
  // transparent when off). on android, clipping a rounded view that has a
  // rotated child, then changing its border on tap, made the contents vanish.
  compass: { position: 'absolute', right: 12, width: 48, height: 48, borderRadius: 24, backgroundColor: COLORS.ink, alignItems: 'center', justifyContent: 'center', elevation: 6, borderWidth: 2.5, borderColor: 'transparent' },
  compassOn: { borderColor: COLORS.here },
  needle: { width: 12, height: 34, alignItems: 'center' },
  needleNorth: { width: 0, height: 0, borderLeftWidth: 5, borderRightWidth: 5, borderBottomWidth: 17, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderBottomColor: '#E5483B' },
  needleSouth: { width: 0, height: 0, borderLeftWidth: 5, borderRightWidth: 5, borderTopWidth: 17, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: '#F2F2F2' },
  needlePin: { position: 'absolute', top: 14, left: 3, width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.ink, borderWidth: 1.5, borderColor: '#F2F2F2' },
});
