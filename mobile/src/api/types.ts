export type Coordinate = [number, number]; // WGS84 [longitude, latitude]
export type LineString = { type: 'LineString'; coordinates: Coordinate[] };
export type Place = { id: string; name: string; coordinate: Coordinate };
export type ShadeState = 'shade' | 'sun' | 'unknown';
export type RouteSegment = {
  shade_state: ShadeState;
  duration_s: number;
  sun_seconds: number | null;
  unknown_seconds: number;
  geometry: LineString;
};
export type Route = {
  id: string;
  mode: 'fastest' | 'recommended' | 'maximum_shade';
  same_as: string | null;
  duration_s: number;
  distance_m: number;
  sun_seconds: number | null;
  unknown_seconds: number;
  optimization_quality: 'shortest_time' | 'candidate_search' | 'unavailable';
  geometry: LineString;
  segments: RouteSegment[];
};
export type RoutesResponse = {
  conditions: {
    temperature_c: number;
    temperature_source: 'user';
    shade_model: 'unavailable' | 'geometry_estimate';
    data_as_of: string | null;
    model_limitations: string[];
  };
  routes: Route[];
};
