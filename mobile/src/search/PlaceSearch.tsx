import React, { useEffect, useRef, useState } from 'react';
import { Image, Keyboard, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { searchPlaces } from '../api/client';
import type { Place } from '../api/types';
import { COLORS } from '../theme';
import { VoiceInput } from './VoiceInput';
import { parseVoiceQuery } from './voiceQuery';

const LOGO = require('../brand/logo.png');

export type Field = 'origin' | 'destination';
// 'current' means "start from wherever my phone is", which usually isn't any
// named place (you might be halfway down Bruin Walk), so it isn't a Place.
export type StartPoint = Place | 'current' | null;
type Props = {
  origin: StartPoint;
  destination: StartPoint;
  onSelect: (field: Field, value: StartPoint) => void;
  onSwap: () => void;
  // the logo is the way home: back to "Where to?" from wherever you are
  onHome?: () => void;
  onFocusChange: (focused: boolean) => void;
  // places you've walked to lately, offered before you type
  recent?: Place[];
};

const PLACEHOLDER: Record<Field, string> = { origin: 'Choose starting point', destination: 'Choose destination' };
const CURRENT_LABEL = 'Your location';
const label = (value: StartPoint) => value === 'current' ? CURRENT_LABEL : value?.name ?? '';
const keyOf = (value: StartPoint) => value === 'current' ? 'current' : value?.id ?? '';
const meta = (place: Place) => (place.address ? `${place.category} @ ${place.address}` : place.category);

export function PlaceSearch({ origin, destination, onSelect, onSwap, onFocusChange, recent = [], onHome }: Props) {
  const [text, setText] = useState<Record<Field, string>>({ origin: label(origin), destination: label(destination) });
  const [focus, setFocus] = useState<Field | null>(null);
  const [results, setResults] = useState<Place[]>([]);
  const [attribution, setAttribution] = useState('');
  const [searchError, setSearchError] = useState('');
  const [voiceMatch, setVoiceMatch] = useState<{ origin: StartPoint; destination: Place } | null>(null);
  const [voiceError, setVoiceError] = useState('');
  const latest = useRef(0);
  const inputs = { origin: useRef<TextInput>(null), destination: useRef<TextInput>(null) };
  // blur events land after the parent re-renders (or sometimes before), so the
  // handlers read these refs instead of whatever props were captured back then.
  const selected = useRef<Record<Field, StartPoint>>({ origin, destination });
  selected.current = { origin, destination };
  const focusRef = useRef<Field | null>(null);

  // the parent changes the selection on swap and reset, so the boxes follow it.
  // typing never changes the ids, so this doesn't stomp on what you're typing.
  useEffect(() => { setText({ origin: label(origin), destination: label(destination) }); }, [keyOf(origin), keyOf(destination)]);

  // a freshly focused box still holds the selected name ("Your location", "Royce
  // Hall"), and searching for that would just show "no matches" or itself.
  const typed = focus ? text[focus].trim() : '';
  const query = focus && typed === label(selected.current[focus]) ? '' : typed;
  useEffect(() => {
    if (!focus || !query) { setResults([]); setSearchError(''); return; }
    // responses can come back out of order on a slow connection, so only the
    // newest request is allowed to fill the dropdown.
    const id = ++latest.current;
    const timer = setTimeout(() => {
      searchPlaces(query, 8)
        .then(res => { if (id === latest.current) { setResults(res.places); setAttribution(res.attribution); setSearchError(''); } })
        .catch(e => { if (id === latest.current) setSearchError(e instanceof Error ? e.message : 'Search failed'); });
    }, 150);
    return () => clearTimeout(timer);
  }, [focus, query]);

  // a place already in one of the boxes would only route to itself
  const recents = recent.filter(place => place.id !== keyOf(origin) && place.id !== keyOf(destination));
  const focusField = (field: Field | null) => { focusRef.current = field; setFocus(field); onFocusChange(field !== null); };
  const blur = (field: Field) => {
    // if you wander off without picking anything, put back what was selected
    // rather than leaving half-typed text that doesn't match the route.
    setText(t => ({ ...t, [field]: label(selected.current[field]) }));
    // when focus hops from start to destination the new field may already own
    // focus by now, and then this blur shouldn't close the dropdown.
    if (focusRef.current === field) focusField(null);
  };
  const choose = (place: Place | 'current') => {
    if (!focus) return;
    const field = focus;
    onSelect(field, place);
    setText(t => ({ ...t, [field]: label(place) }));
    setResults([]);
    if (field === 'origin' && !destination) inputs.destination.current?.focus();
    else { Keyboard.dismiss(); inputs[field].current?.blur(); focusField(null); }
  };
  // close any open box first, otherwise its blur would put the old text back
  // and the dropdown would stay open over the home screen
  const goHome = () => {
    Keyboard.dismiss();
    if (focus) inputs[focus].current?.blur();
    focusField(null);
    onHome?.();
  };
  const clear = (field: Field) => {
    onSelect(field, null);
    setText(t => ({ ...t, [field]: '' }));
    inputs[field].current?.focus();
  };
  const heard = async (transcript: string) => {
    setVoiceMatch(null); setVoiceError('');
    const spoken = parseVoiceQuery(transcript);
    if (!spoken) { setVoiceError('No destination heard. Please try again.'); return; }
    try {
      const fromHere = spoken.origin && /^(?:my location|current location|here|我现在的位置|当前位置)$/i.test(spoken.origin);
      const [start, end] = await Promise.all([
        spoken.origin && !fromHere ? searchPlaces(spoken.origin, 3) : null,
        searchPlaces(spoken.destination, 3),
      ]);
      const origin = fromHere ? 'current' : spoken.origin ? start?.places[0] ?? null : selected.current.origin;
      const destination = end.places[0];
      if (!origin || !destination || (origin !== 'current' && origin.id === destination.id)) {
        setVoiceError('Could not match both places. Try speaking their UCLA names or type them.'); return;
      }
      setVoiceMatch({ origin, destination });
    } catch { setVoiceError('Place search failed. Please try again.'); }
  };

  const row = (field: Field) => (
    <View style={styles.row}>
      <View style={[styles.marker, field === 'destination' && styles.markerEnd, (field === 'origin' ? origin : destination) === 'current' && styles.markerHere]} />
      <TextInput
        ref={inputs[field]} style={styles.input} value={text[field]} placeholder={PLACEHOLDER[field]}
        placeholderTextColor={COLORS.muted} selectTextOnFocus autoCorrect={false} returnKeyType="search"
        onFocus={() => focusField(field)} onBlur={() => blur(field)}
        onChangeText={value => setText(t => ({ ...t, [field]: value }))}
        onSubmitEditing={() => { if (results[0]) choose(results[0]); }}
      />
      {field === 'destination' && <VoiceInput onTranscript={heard} />}
      {!!text[field] && focus === field && (
        <TouchableOpacity hitSlop={10} onPress={() => clear(field)}><Text style={styles.clear}>✕</Text></TouchableOpacity>
      )}
    </View>
  );

  return (
    <View style={styles.card}>
      <View style={styles.fields}>
        <View style={{ flex: 1 }}>
          {row('origin')}
          <View style={styles.rule} />
          {row('destination')}
        </View>
        {/* the logo lives in the card's top right, level with the start row, so
            branding doesn't cost a row of map. swap sits by the destination row. */}
        <View style={styles.side}>
          <TouchableOpacity style={styles.slot} onPress={goHome} accessibilityRole="button" accessibilityLabel="Shady Business, back to Where to?">
            <Image source={LOGO} style={styles.logo} />
          </TouchableOpacity>
          <View style={styles.slot}>
            <TouchableOpacity style={styles.swap} onPress={onSwap} accessibilityLabel="Swap start and destination">
              <Text style={styles.swapText}>⇅</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
      {voiceMatch && <View style={styles.voiceConfirm}>
        <Text style={styles.resultName}>From {label(voiceMatch.origin)} to {voiceMatch.destination.name}?</Text>
        <Text style={styles.resultMeta}>Confirm these UCLA places before finding a route.</Text>
        <TouchableOpacity accessibilityRole="button" accessibilityLabel="Confirm spoken route" onPress={() => {
          onSelect('origin', voiceMatch.origin); onSelect('destination', voiceMatch.destination); setVoiceMatch(null); focusField(null); Keyboard.dismiss();
        }}><Text style={styles.voiceAction}>Confirm route</Text></TouchableOpacity>
        <TouchableOpacity accessibilityRole="button" accessibilityLabel="Cancel spoken route" onPress={() => setVoiceMatch(null)}><Text style={styles.resultMeta}>Cancel</Text></TouchableOpacity>
      </View>}
      {!!voiceError && <Text style={styles.error}>{voiceError}</Text>}
      {focus && (
        <View style={styles.dropdown}>
          {focus === 'origin' && origin !== 'current' && destination !== 'current' && (
            <TouchableOpacity style={[styles.result, styles.hereRow]} onPress={() => choose('current')}>
              <View style={[styles.marker, styles.markerHere]} />
              <View><Text style={styles.resultName}>{CURRENT_LABEL}</Text><Text style={styles.resultMeta}>Walk from where you are now</Text></View>
            </TouchableOpacity>
          )}
          {!query && !recents.length && <Text style={styles.hint}>Try like Powell or Bplate.</Text>}
          {!!query && !results.length && !searchError && <Text style={styles.hint}>No UCLA places match “{query}”.</Text>}
          {!!searchError && <Text style={styles.error}>{searchError}</Text>}
          <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 300 }}>
            {!query && recents.length > 0 && <Text style={styles.section}>Recent</Text>}
            {/* a recent is just a place, so it fills whichever box you're in,
                the same as picking it from search */}
            {!query && recents.map(place => (
              <TouchableOpacity key={place.id} style={[styles.result, styles.recentRow]} onPress={() => choose(place)} accessibilityLabel={`Recent place: ${place.name}`}>
                <View style={styles.clock}><View style={styles.clockHour} /><View style={styles.clockMinute} /></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.resultName} numberOfLines={1}>{place.name}</Text>
                  <Text style={[styles.resultMeta, styles.metaLine]} numberOfLines={1}>{meta(place)}</Text>
                </View>
              </TouchableOpacity>
            ))}
            {results.map(place => (
              <TouchableOpacity key={place.id} style={styles.result} onPress={() => choose(place)}>
                <Text style={styles.resultName} numberOfLines={1}>{place.name}</Text>
                <Text style={[styles.resultMeta, styles.metaLine]} numberOfLines={1}>{meta(place)}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          {!!results.length && !!attribution && <Text style={styles.attribution}>Places {attribution}</Text>}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { marginHorizontal: 12, marginTop: 8, backgroundColor: COLORS.paper, borderRadius: 6, elevation: 8, overflow: 'hidden' },
  fields: { flexDirection: 'row', alignItems: 'center', paddingLeft: 14, paddingRight: 6, paddingVertical: 4 },
  row: { flexDirection: 'row', alignItems: 'center', height: 46 },
  marker: { width: 12, height: 12, borderRadius: 6, borderWidth: 2.5, borderColor: COLORS.ink, marginRight: 12 },
  markerEnd: { backgroundColor: COLORS.ink },
  markerHere: { backgroundColor: COLORS.here, borderColor: COLORS.here },
  hereRow: { flexDirection: 'row', alignItems: 'center' },
  input: { flex: 1, fontSize: 16, color: COLORS.ink, paddingVertical: 0 },
  clear: { fontSize: 15, color: COLORS.muted, paddingHorizontal: 8 },
  rule: { height: 1, backgroundColor: COLORS.rule, marginLeft: 24 },
  side: { marginLeft: 4, justifyContent: 'space-between' },
  slot: { height: 46, width: 44, alignItems: 'center', justifyContent: 'center' },
  logo: { width: 34, height: 34, borderRadius: 17 },
  swap: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  swapText: { fontSize: 22, color: COLORS.ink },
  dropdown: { borderTopWidth: 1, borderTopColor: COLORS.rule, paddingVertical: 4 },
  recentRow: { flexDirection: 'row', alignItems: 'center' },
  // a small clock made of views (no icon font in the app), muted so the place
  // name stays the thing you read
  clock: { width: 16, height: 16, borderRadius: 8, borderWidth: 1.5, borderColor: COLORS.muted, marginRight: 14 },
  clockHour: { position: 'absolute', left: 5.75, top: 2.5, width: 1.5, height: 5, borderRadius: 1, backgroundColor: COLORS.muted },
  clockMinute: { position: 'absolute', left: 6.5, top: 6, width: 4, height: 1.5, borderRadius: 1, backgroundColor: COLORS.muted },
  section: { color: COLORS.muted, fontSize: 11, fontWeight: '600', letterSpacing: 2, textTransform: 'uppercase', paddingHorizontal: 16, paddingTop: 4, paddingBottom: 2 },
  hint: { color: COLORS.muted, fontSize: 13, paddingHorizontal: 16, paddingVertical: 12 },
  error: { color: COLORS.error, fontSize: 13, paddingHorizontal: 16, paddingVertical: 12 },
  result: { paddingHorizontal: 16, paddingVertical: 10 },
  resultName: { fontSize: 15, fontWeight: '600', color: COLORS.ink },
  resultMeta: { fontSize: 12, color: COLORS.muted },
  metaLine: { marginTop: 2 },
  attribution: { fontSize: 10, color: COLORS.muted, paddingHorizontal: 16, paddingVertical: 6, textAlign: 'right' },
  voiceConfirm: { borderTopWidth: 1, borderColor: COLORS.rule, paddingHorizontal: 16, paddingVertical: 10, gap: 5 },
  voiceAction: { color: COLORS.ink, fontSize: 14, fontWeight: '700', paddingVertical: 5 },
});
