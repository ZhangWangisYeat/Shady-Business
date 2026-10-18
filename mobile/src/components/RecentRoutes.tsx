import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { getRouteHistory } from '../api/client';
import type { Place, SavedRoute } from '../api/types';

export function savedConditions(item: SavedRoute): string {
  const departure = new Date(item.request.departure_time);
  const date = departure.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const time = departure.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  return `${date}, ${time} · ${Math.round(item.request.temperature_c * 9 / 5 + 32)}°F`;
}

export function RecentRoutes({ places, onSelect }: {
  places: Place[];
  onSelect: (item: SavedRoute) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<SavedRoute[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setFailed(false);
    getRouteHistory().then(response => {
      if (current) setItems(response.items.slice(0, 5));
    }).catch(() => {
      if (current) setFailed(true);
    }).finally(() => {
      if (current) setLoading(false);
    });
    return () => { current = false; };
  }, [attempt]);

  const placeName = (id: string) => places.find(place => place.id === id)?.name ?? id.replace(/-/g, ' ');

  return <View style={styles.container}>
    <TouchableOpacity accessibilityRole="button" accessibilityLabel="Recent routes"
      accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)} style={styles.toggle}>
      <Text style={styles.title}>Recent routes{items.length > 0 ? ` · ${items.length}` : ''}</Text>
      <View style={[styles.chevron, expanded && styles.chevronUp]} />
    </TouchableOpacity>
    {expanded && <View>
      {loading ? <View accessibilityLiveRegion="polite" style={styles.messageRow}>
        <ActivityIndicator size="small" color="#17785D" /><Text style={styles.message}>Loading recent routes…</Text>
      </View> : failed ? <View accessibilityLiveRegion="polite" style={styles.messageRow}>
        <Text style={[styles.message, styles.flex]}>Couldn’t load recent routes.</Text>
        <TouchableOpacity accessibilityRole="button" onPress={() => setAttempt(value => value + 1)} style={styles.retry}>
          <Text style={styles.title}>Retry</Text>
        </TouchableOpacity>
      </View> : items.length === 0 ? <Text style={styles.empty}>Your last 5 routes will appear here after a search.</Text> :
        <ScrollView nestedScrollEnabled style={styles.list} keyboardShouldPersistTaps="handled">
          {items.map(item => {
            const title = `${placeName(item.request.origin.place_id)} → ${placeName(item.request.destination.place_id)}`;
            return <TouchableOpacity key={item.id} accessibilityRole="button"
              accessibilityLabel={`View saved route: ${title}`} accessibilityHint="Opens the saved route and its original shade estimate."
              onPress={() => onSelect(item)} style={styles.row}>
              <Text style={styles.routeName} numberOfLines={2}>{title}</Text>
              <Text style={styles.metadata}>{savedConditions(item)}</Text>
            </TouchableOpacity>;
          })}
        </ScrollView>}
    </View>}
  </View>;
}

const styles = StyleSheet.create({
  container: { marginTop: 8, borderRadius: 13, backgroundColor: '#F2F6F2', overflow: 'hidden' },
  toggle: { minHeight: 44, paddingHorizontal: 13, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { color: '#17785D', fontSize: 12, fontWeight: '700' },
  chevron: { width: 7, height: 7, borderRightWidth: 1.5, borderBottomWidth: 1.5, borderColor: '#17785D', transform: [{ rotate: '45deg' }], marginRight: 3, marginTop: -3 },
  chevronUp: { transform: [{ rotate: '225deg' }], marginTop: 3 },
  list: { maxHeight: 224, flexGrow: 0 },
  row: { minHeight: 60, paddingHorizontal: 13, paddingVertical: 11, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#DDE7DF' },
  routeName: { color: '#203329', fontSize: 12, fontWeight: '600', lineHeight: 18 },
  metadata: { color: '#60736C', fontSize: 11, lineHeight: 17, marginTop: 2 },
  messageRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingLeft: 13, paddingRight: 8, minHeight: 48 },
  message: { color: '#60736C', fontSize: 12, lineHeight: 18 },
  flex: { flex: 1 },
  retry: { minHeight: 44, minWidth: 44, alignItems: 'center', justifyContent: 'center' },
  empty: { color: '#60736C', fontSize: 12, lineHeight: 18, paddingHorizontal: 13, paddingBottom: 13 },
});
