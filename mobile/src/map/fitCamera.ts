import type { Coordinate } from '../api/types';

export type Insets = { paddingTop: number; paddingBottom: number; paddingLeft: number; paddingRight: number };

// mapbox renders the whole world 512 points wide at zoom 0
const WORLD_POINTS = 512;
const MAX_ZOOM = 18;

const mercX = (lon: number) => (lon + 180) / 360;
const mercY = (lat: number) => {
  const s = Math.sin(lat * Math.PI / 180);
  return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
};
const lonFrom = (x: number) => x * 360 - 180;
const latFrom = (y: number) => (360 / Math.PI) * Math.atan(Math.exp((0.5 - y) * 2 * Math.PI)) - 90;

// i do the bounds fit by hand because rnmapbox 10.3's bounds stop insets the
// box by the map's current padding *and* the padding you pass, so after the
// first fit every route landed zoomed in and hidden behind the sheet. with a
// plain center + zoom the padding is only applied once, by mapbox itself.
export function fitCamera(points: Coordinate[], size: { width: number; height: number }, insets: Insets): { centerCoordinate: Coordinate; zoomLevel: number } {
  const xs = points.map(p => mercX(p[0])), ys = points.map(p => mercY(p[1]));
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const width = Math.max(1, size.width - insets.paddingLeft - insets.paddingRight);
  const height = Math.max(1, size.height - insets.paddingTop - insets.paddingBottom);
  const spanX = Math.max(maxX - minX, 1e-9), spanY = Math.max(maxY - minY, 1e-9);
  const zoom = Math.log2(Math.min(width / (spanX * WORLD_POINTS), height / (spanY * WORLD_POINTS)));
  return { centerCoordinate: [lonFrom((minX + maxX) / 2), latFrom((minY + maxY) / 2)], zoomLevel: Math.min(MAX_ZOOM, zoom) };
}
