import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, ScrollView, StatusBar as RNStatusBar, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as Location from 'expo-location';
import { ShadyMap } from './src/map/ShadyMap';
import { PlaceSearch, type Field, type StartPoint } from './src/search/PlaceSearch';
import { currentCoordinate } from './src/location/currentLocation';
import { bearing, useHeading } from './src/location/heading';
import { getRoutes } from './src/api/client';
import type { Coordinate, Place, Route, RouteEndpoint, RoutesResponse, ShadeState } from './src/api/types';
import { interpolateRoute, locateOnRoute, statusByTimeFraction } from './src/navigation/progress';
import { MANEUVER_ICON, formatDistance, stepProgress } from './src/navigation/steps';
import { COLORS } from './src/theme';
import { exposure } from './src/plan/exposure';

const routeName: Record<Route['mode'], string> = { fastest: 'Fastest', recommended: 'Recommended', maximum_shade: 'Most shade' };
const statusText: Record<ShadeState, string> = { shade: 'Shade', sun: 'Sun', unknown: 'Unknown' };
const MODE_ORDER: Route['mode'][] = ['recommended', 'fastest', 'maximum_shade'];
// android draws edge to edge under the status bar now. react native's SafeAreaView
// is deprecated, and the proper replacement (react-native-safe-area-context) is a
// native module that needs a rebuild, so ios gets a notch-sized guess until then.
const TOP_INSET = Platform.OS === 'android' ? (RNStatusBar.currentHeight ?? 24) : 50;

type Stage = 'plan' | 'navigate' | 'arrived';
export default function App() {
  const [stage, setStage] = useState<Stage>('plan');
  // walking from where you are is the main job, so that's the default start.
  // any other start is planning ahead: same routes and directions, but no
  // Start/Demo walk, since you can't be guided along a path you aren't on.
  const [origin, setOrigin] = useState<StartPoint>('current');
  // the destination can be 'current' too, but only by swapping: that previews
  // the way back to where you are from some other place
  const [destination, setDestination] = useState<StartPoint>(null);
  const [here, setHere] = useState<Coordinate | null>(null);
  const [locating, setLocating] = useState(false);
  const [retry, setRetry] = useState(0);
  const [searchFocused, setSearchFocused] = useState(false);
  const [temp, setTemp] = useState(29);
  const [routes, setRoutes] = useState<RoutesResponse | null>(null);
  const [calculating, setCalculating] = useState(false);
  // routes arrive before the map has drawn them; the cards wait for the drawing
  // so the sheet and the map finish together.
  const [revealed, setRevealed] = useState(false);
  const [chosen, setChosen] = useState<Route['mode']>('recommended');
  const [showDirections, setShowDirections] = useState(false);
  const [walkSteps, setWalkSteps] = useState(false);
  // a small bar with just shade and time, so the map gets nearly the whole screen
  const [compact, setCompact] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [position, setPosition] = useState<Coordinate | null>(null);
  const [shade, setShade] = useState<ShadeState>('unknown');
  const [demo, setDemo] = useState(false);
  const [cardHeight, setCardHeight] = useState(120);
  const [sheetHeight, setSheetHeight] = useState(260);
  const subscription = useRef<Location.LocationSubscription | null>(null);
  const interval = useRef<ReturnType<typeof setInterval> | null>(null);
  const requestId = useRef(0);
  const active = routes?.routes.find(r => r.mode === chosen) ?? null;
  // the compass only runs while the blue dot is on screen
  const deviceHeading = useHeading(stage === 'navigate' ? !demo : (origin === 'current' || destination === 'current') && here !== null);
  // a demo walk has no real phone to turn, so the dot faces along the route
  const demoHeading = stage === 'navigate' && demo && active && position
    ? bearing(position, interpolateRoute(active, Math.min(1, progress + 0.02)))
    : null;
  const fromHere = origin === 'current';
  const originKey = origin === 'current' ? 'current' : origin?.id ?? '';
  const originLabel = origin === 'current' ? 'Your location' : origin?.name ?? '';
  const toHere = destination === 'current';
  const destinationKey = destination === 'current' ? 'current' : destination?.id ?? '';
  const destinationName = destination === 'current' ? 'Your location' : destination?.name ?? '';
  const herePlace = (coordinate: Coordinate | null): Place | null =>
    coordinate ? { id: 'current-location', name: 'Your location', coordinate, category: 'Current location', address: null } : null;
  const stop = () => { subscription.current?.remove(); subscription.current = null; if (interval.current) clearInterval(interval.current); interval.current = null; };
  useEffect(() => () => stop(), []);

  // like google maps, picking both ends (or nudging the temperature) kicks off
  // the route search by itself instead of waiting for a "find routes" tap.
  useEffect(() => {
    setRoutes(null); setRevealed(false); setShowDirections(false); setError('');
    const id = ++requestId.current;
    if (!origin || !destination) { setCalculating(false); return; }
    if (originKey === destinationKey) { setCalculating(false); setError('Pick a different destination.'); return; }
    setCalculating(true);
    // the short delay means tapping the temperature a few times sends one request, not five
    const timer = setTimeout(async () => {
      try {
        // a fresh fix for every route, because you may have walked a block
        // since the last one and the route should start (or end) where you are now
        let coordinate: Coordinate | null = null;
        if (origin === 'current' || destination === 'current') {
          setLocating(true);
          coordinate = await currentCoordinate().finally(() => setLocating(false));
          if (id !== requestId.current) return;
          setHere(coordinate);
        }
        const endpoint = (end: Place | 'current'): RouteEndpoint => (end === 'current' ? { coordinate: coordinate! } : { place_id: end.id });
        const response = await getRoutes(endpoint(origin), endpoint(destination), temp);
        if (id === requestId.current) { setRoutes(response); setChosen('recommended'); }
      } catch (e) {
        if (id !== requestId.current) return;
        // a failed fix means we don't know where you are any more, so the old
        // blue dot (and a route fit around it) would be lying.
        if (origin === 'current' || destination === 'current') setHere(null);
        setError(e instanceof Error ? e.message : 'Could not calculate route.');
      } finally {
        if (id === requestId.current) setCalculating(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [originKey, destinationKey, temp, retry]);

  const select = (field: Field, value: StartPoint) => {
    if (field === 'origin') setOrigin(value);
    else setDestination(value);
  };
  const swap = () => { setOrigin(destination); setDestination(origin); };
  const pick = (mode: Route['mode']) => { setChosen(mode); setPosition(null); setProgress(0); };
  const complete = () => { stop(); setStage('arrived'); };
  const startDemo = () => {
    if (!active || !fromHere) return; stop(); setError(''); setDemo(true); setStage('navigate'); setProgress(0); setShade(statusByTimeFraction(active, 0));
    setPosition(interpolateRoute(active, 0)); let tick = 0;
    interval.current = setInterval(() => {
      tick++; const f = Math.min(1, tick / 75); setProgress(f); setPosition(interpolateRoute(active, f)); setShade(statusByTimeFraction(active, f));
      if (f >= 1) { clearInterval(interval.current!); interval.current = null; setStage('arrived'); }
    }, 650);
  };
  const startGps = async () => {
    if (!active || !fromHere) return; stop(); setError('');
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) { setError('Location permission denied. Use Demo Walk instead.'); return; }
      setDemo(false); setStage('navigate');
      subscription.current = await Location.watchPositionAsync({ accuracy: Location.Accuracy.BestForNavigation, timeInterval: 1000, distanceInterval: 2 }, sample => {
        const coord: Coordinate = [sample.coords.longitude, sample.coords.latitude];
        const match = locateOnRoute(active, coord, sample.coords.accuracy);
        setPosition(coord); setProgress(match.fraction); setShade(match.state);
        if (!match.offRoute && match.fraction > .97 && sample.coords.accuracy !== null && sample.coords.accuracy <= 25) { complete(); }
      });
    } catch (e) { setError(e instanceof Error ? e.message : 'GPS unavailable'); setStage('plan'); stop(); }
  };
  const endNavigation = () => { stop(); setWalkSteps(false); setCompact(false); setStage('plan'); setPosition(null); setProgress(0); };
  const reset = () => { stop(); setStage('plan'); setOrigin('current'); setDestination(null); setPosition(null); setProgress(0); setShade('unknown'); setError(''); };

  const Button = ({ text, onPress, primary = true, style }: { text: string, onPress: () => void, primary?: boolean, style?: object }) =>
    <TouchableOpacity onPress={onPress} style={[styles.button, !primary && styles.outline, style]}>
      <Text style={[styles.buttonText, !primary && styles.outlineText]}>{text}</Text>
    </TouchableOpacity>;
  const Stat = ({ value, label }: { value: string, label: string }) =>
    <View style={styles.stat}><Text style={styles.statValue}>{value}</Text><Text style={styles.statLabel}>{label}</Text></View>;
  const sunStat = (route: Route) => {
    const e = exposure(route);
    return e.sunPct === null ? <Stat value="—" label="Sun" /> : <Stat value={`${e.sunPct}%`} label={e.unknownPct ? `Sun, ${e.unknownPct}% unknown` : 'Sun'} />;
  };
  const minutes = (seconds: number) => Math.max(1, Math.ceil(seconds / 60));
  const arriveText = `Arrive at ${destinationName || 'your destination'}`;
  const tempRow = <View style={styles.tempRow}>
    <Text style={styles.eyebrow}>Temperature</Text>
    <View style={styles.tempControls}>
      <TouchableOpacity style={styles.tempButton} onPress={() => setTemp(v => Math.max(-5, v - 2))}><Text style={styles.tempLabel}>−</Text></TouchableOpacity>
      <Text style={styles.tempValue}>{Math.round(temp * 9 / 5 + 32)}°F</Text>
      <TouchableOpacity style={styles.tempButton} onPress={() => setTemp(v => Math.min(55, v + 2))}><Text style={styles.tempLabel}>+</Text></TouchableOpacity>
    </View>
  </View>;

  const plan = () => {
    if (!destination) return <>
      <Text style={styles.eyebrow}>{fromHere ? 'From your location' : 'Plan a walk'}</Text>
      <Text style={styles.heading}>Where to?</Text>
      <Text style={styles.muted}>Search for any UCLA building, library, café or landmark.</Text>
      {tempRow}
    </>;
    if (!origin) return <>
      <Text style={styles.eyebrow}>Starting point</Text>
      <Text style={styles.heading}>Where from?</Text>
      <Text style={styles.muted}>Choose Your location to walk there now, or any campus place to preview the route.</Text>
    </>;
    if (calculating || (!routes && !error) || (routes && !revealed)) return <>
      <Text style={styles.eyebrow}>{fromHere && locating ? 'Finding you' : 'Finding routes'}</Text>
      <Text style={styles.heading} numberOfLines={1}>{destinationName}</Text>
      <View style={styles.loadingRow}><ActivityIndicator color={COLORS.ink} /><Text style={[styles.muted, { marginLeft: 10, flex: 1 }]} numberOfLines={1}>From {originLabel.toLowerCase() === 'your location' ? 'your location' : originLabel}</Text></View>
    </>;
    if (!routes || !active) return <>
      <Text style={styles.eyebrow}>No route</Text>
      <Text style={styles.heading} numberOfLines={1}>{destinationName}</Text>
      <TouchableOpacity style={styles.link} onPress={() => setRetry(n => n + 1)}><Text style={styles.linkText}>Try again</Text></TouchableOpacity>
    </>;
    const previewNote = <Text style={styles.previewNote}>Preview only. Guided walks start from your location.</Text>;
    // previewing the way back to you, the guided version is the same trip the other way round
    const walkFromHere = <TouchableOpacity style={styles.link} onPress={() => (toHere ? swap() : setOrigin('current'))}><Text style={styles.linkText}>{toHere ? 'Walk from my location instead' : 'Walk there from my location'}</Text></TouchableOpacity>;
    if (showDirections) return <>
      <Text style={styles.eyebrow}>Directions</Text>
      <Text style={styles.heading} numberOfLines={1}>{destinationName}</Text>
      <View style={styles.stats}>
        <Stat value={`${minutes(active.duration_s)}`} label="Min" />
        <Stat value={formatDistance(active.distance_m)} label="Distance" />
        {sunStat(active)}
      </View>
      <ScrollView style={styles.steps}>
        {active.steps.map((step, i) => <View key={i} style={styles.step}>
          <Text style={styles.stepIcon}>{MANEUVER_ICON[step.maneuver]}</Text>
          <Text style={styles.stepText}>{step.maneuver === 'arrive' ? arriveText : step.instruction}</Text>
          {step.distance_m > 0 && <Text style={styles.stepDistance}>{formatDistance(step.distance_m)}</Text>}
        </View>)}
      </ScrollView>
      {fromHere ? <Button text="Start" onPress={() => void startGps()} /> : previewNote}
      <TouchableOpacity style={styles.link} onPress={() => setShowDirections(false)}><Text style={styles.linkText}>Back to routes</Text></TouchableOpacity>
    </>;
    // recommended first because it's the one we'd actually suggest; it already
    // equals fastest when it's cool out, so nothing is hidden by putting it on top.
    const ordered = [...routes.routes].sort((a, b) => MODE_ORDER.indexOf(a.mode) - MODE_ORDER.indexOf(b.mode));
    return <>
      <Text style={styles.eyebrow}>{fromHere ? 'Walking to' : 'Route preview'}</Text>
      <Text style={styles.heading} numberOfLines={1}>{destinationName}</Text>
      <Text style={styles.muted}>{routes.conditions.shade_model === 'unavailable' ? 'No shade data yet, so the three options may be the same path.' : 'Sun is modeled from building and tree data, not measured live.'}</Text>
      <View style={styles.routeList}>
        {ordered.map(route => {
          const on = chosen === route.mode;
          const e = exposure(route);
          return <TouchableOpacity key={route.mode} onPress={() => pick(route.mode)} style={styles.routeRow}>
            <View style={[styles.routeBar, on && styles.routeBarOn]} />
            <View style={{ flex: 1 }}>
              <Text style={[styles.routeName, !on && styles.routeNameOff]}>{routeName[route.mode]}</Text>
              <Text style={styles.routeMeta}>
                {formatDistance(route.distance_m)}, {e.sunPct === null ? 'sun unknown' : `${e.sunPct}% in sun`}{e.sunPct !== null && e.unknownPct > 0 ? `, ${e.unknownPct}% unknown` : ''}
              </Text>
            </View>
            <View style={styles.routeTime}>
              <Text style={[styles.routeMinutes, !on && styles.routeNameOff]}>{minutes(route.duration_s)}</Text>
              <Text style={styles.statLabel}>Min</Text>
            </View>
          </TouchableOpacity>;
        })}
      </View>
      {tempRow}
      {fromHere ? <>
        <Button text="Start" onPress={() => void startGps()} />
        <View style={styles.buttonRow}>
          <Button text="Directions" primary={false} style={{ flex: 1 }} onPress={() => setShowDirections(true)} />
          <Button text="Demo walk" primary={false} style={{ flex: 1 }} onPress={startDemo} />
        </View>
      </> : <>
        <Button text="Directions" onPress={() => setShowDirections(true)} />
        {previewNote}
        {walkFromHere}
      </>}
    </>;
  };

  const navigate = () => {
    const at = active ? stepProgress(active.steps, progress * active.distance_m) : null;
    const minutesLeft = Math.max(0, Math.ceil((active?.duration_s ?? 0) * (1 - progress) / 60));
    if (compact) return <TouchableOpacity style={styles.compactBar} onPress={() => setCompact(false)} accessibilityLabel="Show walk details">
      <View style={[styles.shadeChip, { backgroundColor: COLORS[shade] }]} />
      <Text style={styles.compactText}>{statusText[shade]}</Text>
      <Text style={[styles.compactText, { marginLeft: 'auto' }]}>{minutesLeft} min left</Text>
      <Text style={styles.chevron}>⌃</Text>
    </TouchableOpacity>;
    return <>
      <View style={styles.eyebrowRow}>
        <Text style={styles.eyebrow}>{demo ? 'Demo walk' : 'Walking'}</Text>
        <TouchableOpacity hitSlop={12} onPress={() => { setWalkSteps(false); setCompact(true); }} accessibilityLabel="Hide walk details">
          <Text style={styles.chevron}>⌄</Text>
        </TouchableOpacity>
      </View>
      {at?.next && <View style={styles.nextRow}>
        <Text style={styles.nextIcon}>{MANEUVER_ICON[at.next.maneuver]}</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.nextText}>{at.next.maneuver === 'arrive' ? arriveText : at.next.instruction}</Text>
          <Text style={styles.muted}>in {formatDistance(at.toNextM)}</Text>
        </View>
      </View>}
      <View style={styles.stats}>
        <Stat value={statusText[shade]} label="Right now" />
        <Stat value={`${minutesLeft}`} label="Min left" />
        <Stat value={`${Math.floor(progress * 100)}%`} label="Done" />
      </View>
      {shade === 'unknown' && !walkSteps && <Text style={styles.muted}>No shade estimate here, or your position is uncertain.</Text>}
      {walkSteps && active && <ScrollView style={styles.walkSteps}>
        {active.steps.map((step, i) => {
          // steps up to the current one are behind you; the one after it is
          // the turn you're walking toward
          const done = !!at && i <= at.current;
          const upcoming = !!at && i === at.current + 1;
          return <View key={i} style={styles.step}>
            <Text style={[styles.stepIcon, done && styles.stepDone]}>{MANEUVER_ICON[step.maneuver]}</Text>
            <Text style={[styles.stepText, done && styles.stepDone, upcoming && styles.stepNext]}>{step.maneuver === 'arrive' ? arriveText : step.instruction}</Text>
            {step.distance_m > 0 && <Text style={[styles.stepDistance, done && styles.stepDone]}>{formatDistance(step.distance_m)}</Text>}
          </View>;
        })}
      </ScrollView>}
      <View style={styles.buttonRow}>
        <Button text={walkSteps ? 'Hide directions' : 'Directions'} primary={false} style={{ flex: 1 }} onPress={() => setWalkSteps(v => !v)} />
        <Button text="End walk" primary={false} style={{ flex: 1 }} onPress={endNavigation} />
      </View>
    </>;
  };

  return <View style={styles.root}><StatusBar style="dark" />
    <ShadyMap routes={routes?.routes ?? []} activeMode={active ? chosen : null}
      origin={origin === 'current' ? herePlace(here) : origin} originIsCurrent={fromHere}
      destination={destination === 'current' ? herePlace(here) : destination} destinationIsCurrent={toHere}
      position={position} navigating={stage === 'navigate'} calculating={calculating} onDrawn={() => setRevealed(true)}
      heading={demo && stage === 'navigate' ? demoHeading : deviceHeading}
      insets={{ top: stage === 'plan' ? TOP_INSET + cardHeight : TOP_INSET, bottom: sheetHeight }} />
    <View style={[styles.safe, { paddingTop: TOP_INSET }]} pointerEvents="box-none">
      {stage === 'plan' && <View onLayout={e => setCardHeight(e.nativeEvent.layout.height + 8)}>
        <PlaceSearch origin={origin} destination={destination} onSelect={select} onSwap={swap} onFocusChange={setSearchFocused} />
      </View>}
      <View style={styles.spacer} pointerEvents="none" />
      {!searchFocused && <View style={styles.panel} onLayout={e => setSheetHeight(e.nativeEvent.layout.height)}>
        {stage === 'plan' && plan()}
        {stage === 'navigate' && navigate()}
        {stage === 'arrived' && <>
          <Text style={styles.eyebrow}>Arrived</Text>
          <Text style={styles.heading} numberOfLines={1}>{destinationName || 'Destination'}</Text>
          <Text style={styles.muted}>{demo ? 'Demo walk complete.' : 'You made it.'}</Text>
          <Button text="Plan another walk" onPress={reset} />
        </>}
        {!!error && !(stage === 'navigate' && compact) && <Text style={styles.error}>{error}</Text>}
        {!(stage === 'navigate' && compact) && <View style={styles.legend}>
          {([['shade', 'Shade'], ['sun', 'Sun'], ['unknown', 'Unknown']] as const).map(([key, text]) =>
            <View key={key} style={styles.legendItem}><View style={[styles.swatch, { backgroundColor: COLORS[key] }]} /><Text style={styles.legendText}>{text}</Text></View>)}
          <Text style={[styles.legendText, { marginLeft: 'auto' }]}>Estimates only</Text>
        </View>}
      </View>}
    </View>
  </View>;
}
// the look leans on the resume site's house style: square-ish 4 px corners, hairline rules
// between rows instead of boxed cards, and small uppercase tracked labels, so it
// reads more like a timetable than a stack of rounded app cards.
const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.fill }, safe: { flex: 1 }, spacer: { flex: 1 },
  panel: { backgroundColor: COLORS.paper, paddingHorizontal: 20, paddingTop: 20, paddingBottom: 22, borderTopLeftRadius: 10, borderTopRightRadius: 10, elevation: 10 },
  eyebrow: { fontSize: 11, fontWeight: '600', letterSpacing: 2, textTransform: 'uppercase', color: COLORS.muted },
  heading: { fontSize: 24, fontWeight: '700', color: COLORS.ink, letterSpacing: -0.3, marginTop: 4, marginBottom: 4 },
  muted: { color: COLORS.muted, fontSize: 13, lineHeight: 19 },
  tempRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14, marginBottom: 4 },
  tempControls: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  tempButton: { width: 32, height: 32, borderRadius: 4, borderWidth: 1, borderColor: COLORS.rule, alignItems: 'center', justifyContent: 'center' },
  tempLabel: { fontSize: 18, color: COLORS.ink }, tempValue: { fontSize: 16, fontWeight: '600', color: COLORS.ink, minWidth: 44, textAlign: 'center' },
  loadingRow: { flexDirection: 'row', alignItems: 'center', marginVertical: 10 },
  button: { backgroundColor: COLORS.ink, paddingVertical: 14, borderRadius: 4, alignItems: 'center', marginTop: 10 },
  buttonText: { color: COLORS.paper, fontSize: 13, fontWeight: '700', letterSpacing: 1.5, textTransform: 'uppercase' },
  buttonRow: { flexDirection: 'row', gap: 8 },
  outline: { backgroundColor: COLORS.paper, borderWidth: 1, borderColor: COLORS.ink }, outlineText: { color: COLORS.ink },
  routeList: { marginTop: 12, borderTopWidth: 1, borderTopColor: COLORS.rule },
  routeRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: COLORS.rule },
  routeBar: { width: 3, alignSelf: 'stretch', marginRight: 12, backgroundColor: 'transparent' }, routeBarOn: { backgroundColor: COLORS.ink },
  routeName: { color: COLORS.ink, fontSize: 16, fontWeight: '700' }, routeNameOff: { color: COLORS.muted, fontWeight: '500' },
  routeMeta: { color: COLORS.muted, fontSize: 12, marginTop: 3 },
  routeTime: { alignItems: 'flex-end', minWidth: 44 }, routeMinutes: { fontSize: 24, fontWeight: '700', color: COLORS.ink, lineHeight: 26 },
  stats: { flexDirection: 'row', gap: 22, marginTop: 10, marginBottom: 6 },
  stat: {}, statValue: { fontSize: 18, fontWeight: '700', color: COLORS.ink },
  statLabel: { fontSize: 10, fontWeight: '600', letterSpacing: 1.5, textTransform: 'uppercase', color: COLORS.muted, marginTop: 1 },
  steps: { maxHeight: 280, marginTop: 6, borderTopWidth: 1, borderTopColor: COLORS.rule },
  step: { flexDirection: 'row', alignItems: 'center', paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: COLORS.rule },
  stepIcon: { width: 26, fontSize: 16, color: COLORS.ink }, stepText: { flex: 1, color: COLORS.ink, fontSize: 14 },
  eyebrowRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  chevron: { fontSize: 20, color: COLORS.ink, paddingHorizontal: 6, lineHeight: 22 },
  compactBar: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 2 },
  compactText: { fontSize: 17, fontWeight: '700', color: COLORS.ink },
  shadeChip: { width: 12, height: 12, borderRadius: 2 },
  walkSteps: { maxHeight: 220, marginTop: 4, borderTopWidth: 1, borderTopColor: COLORS.rule },
  stepDone: { color: COLORS.muted, opacity: 0.6 }, stepNext: { fontWeight: '700' },
  stepDistance: { color: COLORS.muted, fontSize: 12, marginLeft: 12 },
  nextRow: { flexDirection: 'row', alignItems: 'center', marginTop: 8, marginBottom: 4 }, nextIcon: { fontSize: 30, color: COLORS.ink, width: 40 }, nextText: { fontSize: 19, fontWeight: '700', color: COLORS.ink },
  link: { alignSelf: 'center', padding: 8, marginTop: 2 }, linkText: { color: COLORS.ink, fontSize: 13, fontWeight: '600', textDecorationLine: 'underline' },
  previewNote: { color: COLORS.muted, fontSize: 12, textAlign: 'center', marginTop: 10 },
  error: { color: COLORS.error, fontSize: 12, marginTop: 9 },
  legend: { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 14 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 }, swatch: { width: 14, height: 4, borderRadius: 1 },
  legendText: { color: COLORS.muted, fontSize: 10, letterSpacing: 1, textTransform: 'uppercase' },
});
