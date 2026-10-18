import type { Place, RoutesResponse, SavedRoute } from '../src/api/types';

// Explicit offline fixtures, not campus route or shade evidence.
export const places: Place[] = [
  { id: 'royce-hall', name: 'Royce Hall', coordinate: [-118.4422, 34.0728], category: 'Building', address: null },
  { id: 'ackerman-union', name: 'Ackerman Union', coordinate: [-118.444, 34.0703], category: 'Building', address: '308 Westwood Plaza' },
  { id: 'powell-library', name: 'Powell Library', coordinate: [-118.4418, 34.0716], category: 'Library', address: null },
];

export const result: RoutesResponse = {
  conditions: {
    temperature_c: 25, temperature_source: 'user', shade_model: 'unavailable',
    shade_coverage: 'unavailable', solar_status: 'unavailable', data_as_of: null,
    model_limitations: ['Offline test fixture'],
  },
  routes: ['fastest', 'recommended', 'maximum_shade'].map((mode, i) => ({
    id: `${mode}-01`, mode: mode as RoutesResponse['routes'][number]['mode'],
    same_as: i ? 'fastest-01' : null, duration_s: 300, distance_m: 390,
    sun_seconds: null, unknown_seconds: 300, coverage_fraction: 0,
    optimization_quality: i ? 'unavailable' : 'shortest_time',
    geometry: { type: 'LineString', coordinates: [places[0].coordinate, places[1].coordinate] },
    segments: [{ shade_state: 'unknown', duration_s: 300, sun_seconds: null, unknown_seconds: 300,
      geometry: { type: 'LineString', coordinates: [places[0].coordinate, places[1].coordinate] } }],
    steps: [{ maneuver: 'depart', instruction: 'Head south on the walkway', way_name: null, distance_m: 390 },
            { maneuver: 'arrive', instruction: 'Arrive at your destination', way_name: null, distance_m: 0 }],
  })),
};

export const saved: SavedRoute = {
  id: 'bfb77111-84f0-4011-a111-2d1941527611', saved_at: '2026-10-17T19:00:00Z',
  request: {
    origin: { place_id: 'royce-hall', coordinate: null },
    destination: { place_id: 'powell-library', coordinate: null },
    departure_time: '2026-10-17T12:00:00-07:00', temperature_c: 25,
  },
  result, is_historical: true,
};
