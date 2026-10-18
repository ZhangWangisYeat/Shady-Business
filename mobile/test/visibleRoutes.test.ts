import type { Route } from '../src/api/types';
import { cardLabel, defaultMode, visibleRoutes } from '../src/plan/visibleRoutes';
import { result } from './fixtures';

// sun null means the whole walk is unknown
const route = (mode: Route['mode'], same_as: string | null, duration_s = 300, sun_seconds: number | null = null, path?: [number, number][]): Route => ({
  ...result.routes[0], id: `${mode}-01`, mode, same_as, duration_s, sun_seconds, unknown_seconds: sun_seconds === null ? duration_s : 0,
  ...(path ? { geometry: { type: 'LineString' as const, coordinates: path } } : {}),
});
const labels = (routes: Route[]) => { const cards = visibleRoutes(routes); return cards.map(c => cardLabel(c, cards)); };

// two ~250 m walks between the same corners of a block: one goes east then
// north, the other north then east, so they share almost nothing
const EAST_THEN_NORTH: [number, number][] = [[-118.4460, 34.0700], [-118.4433, 34.0700], [-118.4433, 34.0720]];
const NORTH_THEN_EAST: [number, number][] = [[-118.4460, 34.0700], [-118.4460, 34.0720], [-118.4433, 34.0720]];
const EAST_THEN_NORTH_NUDGED: [number, number][] = [[-118.4460, 34.07003], [-118.4433, 34.07003], [-118.4433, 34.0720]];

test('all three the same path collapse into one fastest route', () => {
  const routes = [route('fastest', null, 300, 100), route('recommended', 'fastest-01', 300, 100), route('maximum_shade', 'fastest-01', 300, 100)];
  expect(labels(routes)).toEqual(['Fastest']);
  expect(defaultMode(routes)).toBe('fastest');
});

test('mostly unknown shade just shows the fastest route', () => {
  const routes = [route('fastest', null, 300), route('recommended', null, 400), route('maximum_shade', null, 500)];
  expect(labels(routes)).toEqual(['Fastest']);
});

test('shadiest repeating recommended is hidden', () => {
  const routes = [route('fastest', null, 300, 200), route('recommended', null, 500, 120), route('maximum_shade', 'recommended-01', 500, 120)];
  expect(labels(routes)).toEqual(['Recommended', 'Fastest']);
  expect(defaultMode(routes)).toBe('recommended');
});

test('three different walks far apart in time all stay', () => {
  const routes = [route('fastest', null, 300, 200), route('recommended', null, 420, 120), route('maximum_shade', null, 540, 60)];
  expect(labels(routes)).toEqual(['Recommended', 'Fastest', 'Shadiest']);
});

test('the same time and about the same sun merge into the quicker one', () => {
  const routes = [route('fastest', null, 300, 71), route('recommended', null, 301, 71), route('maximum_shade', null, 375, 44)];
  expect(labels(routes)).toEqual(['Recommended and fastest', 'Shadiest']);
  expect(defaultMode(routes)).toBe('fastest');
});

test('all three as quick and as shady become one fastest and shadiest route', () => {
  const routes = [route('fastest', null, 300, 60), route('recommended', null, 320, 58), route('maximum_shade', null, 340, 55)];
  expect(labels(routes)).toEqual(['Fastest and shadiest']);
});

test('shadiest as quick as the others becomes the only route', () => {
  const routes = [route('fastest', null, 300, 200), route('recommended', null, 300, 150), route('maximum_shade', null, 300, 60)];
  expect(labels(routes)).toEqual(['Fastest and shadiest']);
  expect(defaultMode(routes)).toBe('maximum_shade');
});

test('fastest within a minute of a shadier route is absorbed into it', () => {
  const routes = [route('fastest', null, 300, 200), route('recommended', null, 350, 120), route('maximum_shade', null, 600, 30)];
  expect(labels(routes)).toEqual(['Recommended and fastest', 'Shadiest']);
  expect(defaultMode(routes)).toBe('recommended');
});

test('more than a minute slower stays separate', () => {
  const routes = [route('fastest', null, 300, 200), route('recommended', null, 362, 120), route('maximum_shade', null, 600, 30)];
  expect(labels(routes)).toEqual(['Recommended', 'Fastest', 'Shadiest']);
});

test('a mostly unknown route is not merged when others are known', () => {
  const routes = [route('fastest', null, 300, 200), route('recommended', null, 310), route('maximum_shade', null, 600, 30)];
  expect(labels(routes)).toEqual(['Recommended', 'Fastest', 'Shadiest']);
});

test('a tie that takes a different way stays as an alternate route', () => {
  const routes = [route('fastest', null, 300, 60, EAST_THEN_NORTH), route('recommended', null, 310, 58, NORTH_THEN_EAST), route('maximum_shade', null, 320, 55, EAST_THEN_NORTH)];
  expect(labels(routes)).toEqual(['Fastest and shadiest', 'Alternate route']);
});

test('a tie on nearly the same path is not an alternate', () => {
  const routes = [route('fastest', null, 300, 60, EAST_THEN_NORTH), route('recommended', null, 310, 58, EAST_THEN_NORTH_NUDGED), route('maximum_shade', null, 320, 55, EAST_THEN_NORTH)];
  expect(labels(routes)).toEqual(['Fastest and shadiest']);
});
