import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, ScrollView, StatusBar as RNStatusBar, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as Location from 'expo-location';
import { ShadyMap } from './src/map/ShadyMap';
import { PlaceSearch, type Field } from './src/search/PlaceSearch';
import { getRoutes } from './src/api/client';
import type { Coordinate, Place, Route, RoutesResponse, ShadeState } from './src/api/types';
import { interpolateRoute, locateOnRoute, statusByTimeFraction } from './src/navigation/progress';
import { MANEUVER_ICON, formatDistance, stepProgress } from './src/navigation/steps';
import { COLORS } from './src/theme';

const routeName: Record<Route['mode'], string> = { fastest: 'Fastest', recommended: 'Recommended', maximum_shade: 'Most shade' };
const statusText: Record<ShadeState, string> = { shade: 'In shade', sun: 'In direct sun', unknown: 'Shade unknown' };
// android draws edge to edge under the status bar now. react native's SafeAreaView
// is deprecated, and the proper replacement (react-native-safe-area-context) is a
// native module that needs a rebuild, so ios gets a notch-sized guess until then.
const TOP_INSET = Platform.OS === 'android' ? (RNStatusBar.currentHeight ?? 24) : 50;
// long enough that the "searching" line on the map is actually seen, short
// enough that it doesn't feel like we're stalling a fast local backend.
const MIN_SEARCH_MS = 700;

type Stage = 'plan' | 'navigate' | 'arrived';
export default function App() {
  const [stage, setStage] = useState<Stage>('plan');
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [searchFocused, setSearchFocused] = useState(false);
  const [temp, setTemp] = useState(29);
  const [routes, setRoutes] = useState<RoutesResponse | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [chosen, setChosen] = useState<Route['mode']>('recommended');
  const [showDirections, setShowDirections] = useState(false);
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
  const stop = () => { subscription.current?.remove(); subscription.current = null; if (interval.current) clearInterval(interval.current); interval.current = null; };
  useEffect(() => () => stop(), []);

  // like google maps, picking both ends (or nudging the temperature) kicks off
  // the route search by itself instead of waiting for a "find routes" tap.
  useEffect(() => {
    setRoutes(null); setShowDirections(false); setError('');
    const id = ++requestId.current;
    if (!origin || !destination) { setCalculating(false); return; }
    if (origin.id === destination.id) { setCalculating(false); setError('Pick a different destination.'); return; }
    setCalculating(true);
    // the short delay means tapping the temperature a few times sends one request, not five
    const timer = setTimeout(() => {
      Promise.all([getRoutes(origin.id, destination.id, temp), new Promise(r => setTimeout(r, MIN_SEARCH_MS))])
        .then(([response]) => { if (id === requestId.current) { setRoutes(response); setChosen('recommended'); } })
        .catch(e => { if (id === requestId.current) setError(e instanceof Error ? e.message : 'Could not calculate route.'); })
        .finally(() => { if (id === requestId.current) setCalculating(false); });
    }, 250);
    return () => clearTimeout(timer);
  }, [origin?.id, destination?.id, temp]);

  const select = (field: Field, place: Place | null) => (field === 'origin' ? setOrigin : setDestination)(place);
  const swap = () => { setOrigin(destination); setDestination(origin); };
  const pick = (mode: Route['mode']) => { setChosen(mode); setPosition(null); setProgress(0); };
  const complete = () => { stop(); setStage('arrived'); };
  const startDemo = () => {
    if (!active) return; stop(); setError(''); setDemo(true); setStage('navigate'); setProgress(0); setShade(statusByTimeFraction(active, 0));
    setPosition(interpolateRoute(active, 0)); let tick = 0;
    interval.current = setInterval(() => {
      tick++; const f = Math.min(1, tick / 75); setProgress(f); setPosition(interpolateRoute(active, f)); setShade(statusByTimeFraction(active, f));
      if (f >= 1) { clearInterval(interval.current!); interval.current = null; setStage('arrived'); }
    }, 650);
  };
  const startGps = async () => {
    if (!active) return; stop(); setError('');
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
  const endNavigation = () => { stop(); setStage('plan'); setPosition(null); setProgress(0); };
  const reset = () => { stop(); setStage('plan'); setOrigin(null); setDestination(null); setPosition(null); setProgress(0); setShade('unknown'); setError(''); };

  const Button = ({ text, onPress, primary = true, style }: { text: string, onPress: () => void, primary?: boolean, style?: object }) =>
    <TouchableOpacity onPress={onPress} style={[styles.button, !primary && styles.outline, style]}>
      <Text style={[styles.buttonText, !primary && styles.outlineText]}>{text}</Text>
    </TouchableOpacity>;
  const arriveText = `Arrive at ${destination?.name ?? 'your destination'}`;
  const tempRow = <View style={styles.tempRow}><Text style={styles.label}>Temperature</Text><View style={styles.tempControls}>
    <TouchableOpacity style={styles.tempButton} onPress={() => setTemp(v => Math.max(-5, v - 2))}><Text style={styles.tempLabel}>−</Text></TouchableOpacity>
    <Text style={styles.tempValue}>{Math.round(temp * 9 / 5 + 32)}°F</Text>
    <TouchableOpacity style={styles.tempButton} onPress={() => setTemp(v => Math.min(55, v + 2))}><Text style={styles.tempLabel}>+</Text></TouchableOpacity>
  </View></View>;

  const plan = () => {
    if (!origin || !destination) return <>
      <Text style={styles.heading}>Where to?</Text>
      <Text style={styles.muted}>Search any UCLA building, library, café or landmark above.</Text>
      {tempRow}
    </>;
    if (calculating || (!routes && !error)) return <>
      <Text style={styles.heading}>Finding walking routes…</Text>
      <View style={styles.loadingRow}><ActivityIndicator color={COLORS.ink} /><Text style={[styles.muted, { marginLeft: 10, flex: 1 }]} numberOfLines={1}>{origin.name} → {destination.name}</Text></View>
    </>;
    if (!routes || !active) return null;
    if (showDirections) return <>
      <Text style={styles.heading}>Directions</Text>
      <Text style={styles.muted}>{routeName[active.mode]} · {Math.ceil(active.duration_s / 60)} min · {formatDistance(active.distance_m)}</Text>
      <ScrollView style={styles.steps}>
        {active.steps.map((step, i) => <View key={i} style={styles.step}>
          <Text style={styles.stepIcon}>{MANEUVER_ICON[step.maneuver]}</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.stepText}>{step.maneuver === 'arrive' ? arriveText : step.instruction}</Text>
            {step.distance_m > 0 && <Text style={styles.muted}>{formatDistance(step.distance_m)}</Text>}
          </View>
        </View>)}
      </ScrollView>
      <Button text="Start" onPress={() => void startGps()} />
      <TouchableOpacity style={styles.link} onPress={() => setShowDirections(false)}><Text style={styles.linkText}>Back to routes</Text></TouchableOpacity>
    </>;
    return <>
      <Text style={styles.heading}>Choose your walk</Text>
      <Text style={styles.muted}>{routes.conditions.shade_model === 'unavailable' ? 'Shade data unavailable, so routes may be identical.' : 'Modeled sunlight, not guaranteed real-time shade.'}</Text>
      {routes.routes.map(route => <TouchableOpacity key={route.mode} onPress={() => pick(route.mode)} style={[styles.routeRow, chosen === route.mode && styles.selected]}>
        <View style={{ flex: 1 }}><Text style={styles.routeName}>{routeName[route.mode]}{route.same_as ? ' · same path' : ''}</Text>
          <Text style={styles.muted}>{formatDistance(route.distance_m)} · {route.sun_seconds === null ? 'Sun exposure unknown' : `${Math.round(route.sun_seconds / 60)} min modeled sun`}</Text></View>
        <Text style={styles.routeTime}>{Math.ceil(route.duration_s / 60)} min</Text></TouchableOpacity>)}
      {tempRow}
      <Button text="Start" onPress={() => void startGps()} />
      <View style={styles.buttonRow}>
        <Button text="Directions" primary={false} style={{ flex: 1 }} onPress={() => setShowDirections(true)} />
        <Button text="Demo walk" primary={false} style={{ flex: 1 }} onPress={startDemo} />
      </View>
    </>;
  };

  const navigate = () => {
    const at = active ? stepProgress(active.steps, progress * active.distance_m) : null;
    return <>
      <Text style={styles.eyebrow}>{demo ? 'Demo navigation' : 'Walking navigation'}</Text>
      {at?.next && <View style={styles.nextRow}>
        <Text style={styles.nextIcon}>{MANEUVER_ICON[at.next.maneuver]}</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.nextText}>{at.next.maneuver === 'arrive' ? arriveText : at.next.instruction}</Text>
          <Text style={styles.muted}>in {formatDistance(at.toNextM)}</Text>
        </View>
      </View>}
      <Text style={styles.bigStatus}>{statusText[shade]}</Text>
      <Text style={styles.muted}>{Math.floor(progress * 100)}% of route · {Math.max(0, Math.ceil((active?.duration_s ?? 0) * (1 - progress) / 60))} min remaining</Text>
      {shade === 'unknown' && <Text style={styles.muted}>Shade estimate unavailable or position uncertain.</Text>}
      <Button text="End navigation" primary={false} onPress={endNavigation} />
    </>;
  };

  return <View style={styles.root}><StatusBar style="dark" />
    <ShadyMap routes={routes?.routes ?? []} activeMode={active ? chosen : null} origin={origin} destination={destination}
      position={position} navigating={stage === 'navigate'} calculating={calculating}
      insets={{ top: stage === 'plan' ? TOP_INSET + cardHeight : TOP_INSET, bottom: sheetHeight }} />
    <View style={[styles.safe, { paddingTop: TOP_INSET }]} pointerEvents="box-none">
      {stage === 'plan' && <View onLayout={e => setCardHeight(e.nativeEvent.layout.height + 8)}>
        <PlaceSearch origin={origin} destination={destination} onSelect={select} onSwap={swap} onFocusChange={setSearchFocused} />
      </View>}
      <View style={styles.spacer} pointerEvents="none" />
      {!searchFocused && <View style={styles.panel} onLayout={e => setSheetHeight(e.nativeEvent.layout.height)}>
        {stage === 'plan' && plan()}
        {stage === 'navigate' && navigate()}
        {stage === 'arrived' && <><Text style={styles.heading}>You've arrived ✓</Text><Text style={styles.muted}>{demo ? 'Demonstration completed.' : `${destination?.name ?? 'Destination'} reached.`}</Text><Button text="Plan another walk" onPress={reset} /></>}
        {!!error && <Text style={styles.error}>{error}</Text>}
        <Text style={styles.footer}>🟩 shade   🟧 sun   ⬛ unknown · Estimates only</Text>
      </View>}
    </View>
  </View>;
}
const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.fill }, safe: { flex: 1 }, spacer: { flex: 1 },
  panel: { backgroundColor: COLORS.paper, paddingHorizontal: 20, paddingTop: 18, paddingBottom: 24, borderTopLeftRadius: 28, borderTopRightRadius: 28, elevation: 12 },
  heading: { fontSize: 21, fontWeight: '800', color: COLORS.ink, marginBottom: 6 }, label: { fontWeight: '700', color: COLORS.ink },
  eyebrow: { fontSize: 11, fontWeight: '600', letterSpacing: 2.5, textTransform: 'uppercase', color: COLORS.muted, marginBottom: 8 },
  tempRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, marginBottom: 6 },
  tempControls: { flexDirection: 'row', alignItems: 'center', gap: 10 }, tempButton: { width: 30, height: 30, borderRadius: 15, backgroundColor: COLORS.fill, alignItems: 'center', justifyContent: 'center' }, tempLabel: { fontSize: 21, color: COLORS.ink }, tempValue: { fontSize: 16, fontWeight: '700', color: COLORS.ink },
  loadingRow: { flexDirection: 'row', alignItems: 'center', marginVertical: 10 },
  button: { backgroundColor: COLORS.ink, paddingVertical: 13, borderRadius: 13, alignItems: 'center', marginTop: 8 }, buttonText: { color: COLORS.paper, fontSize: 15, fontWeight: '700' },
  buttonRow: { flexDirection: 'row', gap: 8 },
  outline: { backgroundColor: COLORS.paper, borderWidth: 1.5, borderColor: COLORS.ink }, outlineText: { color: COLORS.ink },
  muted: { color: COLORS.muted, fontSize: 12, lineHeight: 18 }, routeRow: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: COLORS.rule, borderRadius: 13, padding: 11, marginTop: 8 },
  selected: { borderColor: COLORS.ink, borderWidth: 1.5, backgroundColor: COLORS.fill }, routeName: { color: COLORS.ink, fontWeight: '700' }, routeTime: { fontSize: 17, fontWeight: '800', color: COLORS.ink },
  steps: { maxHeight: 280, marginTop: 8 }, step: { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: COLORS.rule },
  stepIcon: { width: 30, fontSize: 18, color: COLORS.ink, textAlign: 'center', marginRight: 8 }, stepText: { color: COLORS.ink, fontSize: 14, fontWeight: '600' },
  nextRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 }, nextIcon: { fontSize: 34, color: COLORS.ink, width: 44 }, nextText: { fontSize: 18, fontWeight: '800', color: COLORS.ink },
  link: { alignSelf: 'center', padding: 8 }, linkText: { color: COLORS.ink, fontWeight: '600', textDecorationLine: 'underline' }, bigStatus: { fontSize: 24, fontWeight: '800', color: COLORS.ink, marginVertical: 8 },
  error: { color: COLORS.error, fontSize: 12, marginTop: 9 }, footer: { color: COLORS.muted, fontSize: 10, marginTop: 10, textAlign: 'center' }
});
