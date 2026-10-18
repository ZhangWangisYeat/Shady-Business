import React, { useEffect, useRef, useState } from 'react';
import { Image, Keyboard, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { searchPlaces } from '../api/client';
import type { Place } from '../api/types';
import { COLORS } from '../theme';

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
  onFocusChange: (focused: boolean) => void;
};

const PLACEHOLDER: Record<Field, string> = { origin: 'Choose starting point', destination: 'Choose destination' };
const CURRENT_LABEL = 'Your location';
const label = (value: StartPoint) => value === 'current' ? CURRENT_LABEL : value?.name ?? '';
const keyOf = (value: StartPoint) => value === 'current' ? 'current' : value?.id ?? '';

export function PlaceSearch({ origin, destination, onSelect, onSwap, onFocusChange }: Props) {
  const [text, setText] = useState<Record<Field, string>>({ origin: label(origin), destination: label(destination) });
  const [focus, setFocus] = useState<Field | null>(null);
  const [results, setResults] = useState<Place[]>([]);
  const [attribution, setAttribution] = useState('');
  const [searchError, setSearchError] = useState('');
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
  const clear = (field: Field) => {
    onSelect(field, null);
    setText(t => ({ ...t, [field]: '' }));
    inputs[field].current?.focus();
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
          <View style={styles.slot}><Image source={LOGO} style={styles.logo} accessibilityLabel="Shady Business" /></View>
          <View style={styles.slot}>
            <TouchableOpacity style={styles.swap} onPress={onSwap} accessibilityLabel="Swap start and destination">
              <Text style={styles.swapText}>⇅</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
      {focus && (
        <View style={styles.dropdown}>
          {focus === 'origin' && origin !== 'current' && destination !== 'current' && (
            <TouchableOpacity style={[styles.result, styles.hereRow]} onPress={() => choose('current')}>
              <View style={[styles.marker, styles.markerHere]} />
              <View><Text style={styles.resultName}>{CURRENT_LABEL}</Text><Text style={styles.resultMeta}>Walk from where you are now</Text></View>
            </TouchableOpacity>
          )}
          {!query && <Text style={styles.hint}>Try like Powell or Bplate.</Text>}
          {!!query && !results.length && !searchError && <Text style={styles.hint}>No UCLA places match “{query}”.</Text>}
          {!!searchError && <Text style={styles.error}>{searchError}</Text>}
          <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 300 }}>
            {results.map(place => (
              <TouchableOpacity key={place.id} style={styles.result} onPress={() => choose(place)}>
                <Text style={styles.resultName} numberOfLines={1}>{place.name}</Text>
                <Text style={[styles.resultMeta, styles.metaLine]} numberOfLines={1}>{place.address ? `${place.category} @ ${place.address}` : place.category}</Text>
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
  hint: { color: COLORS.muted, fontSize: 13, paddingHorizontal: 16, paddingVertical: 12 },
  error: { color: COLORS.error, fontSize: 13, paddingHorizontal: 16, paddingVertical: 12 },
  result: { paddingHorizontal: 16, paddingVertical: 10 },
  resultName: { fontSize: 15, fontWeight: '600', color: COLORS.ink },
  resultMeta: { fontSize: 12, color: COLORS.muted },
  metaLine: { marginTop: 2 },
  attribution: { fontSize: 10, color: COLORS.muted, paddingHorizontal: 16, paddingVertical: 6, textAlign: 'right' },
});
