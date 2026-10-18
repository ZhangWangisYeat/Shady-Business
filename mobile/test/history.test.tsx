import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as api from '../src/api/client';
import * as Location from 'expo-location';
import { ShadyMap } from '../src/map/ShadyMap';
import { currentCoordinate } from '../src/location/currentLocation';
import App from '../App';
import type { SavedRoute } from '../src/api/types';
import { places, result, saved } from './fixtures';

jest.mock('../src/api/client', () => ({
  searchPlaces: jest.fn(), getRouteHistory: jest.fn(), getRoutes: jest.fn(), getCurrentTemperature: jest.fn(),
  ApiError: class extends Error {},
}));
// the real map needs mapbox; this stand-in just says "finished drawing" whenever
// it gets routes, which is when the app shows the route cards
jest.mock('../src/map/ShadyMap', () => ({
  ShadyMap: jest.fn((props: { routes: unknown[]; onDrawn?: () => void }) => {
    require('react').useEffect(() => { if (props.routes.length) props.onDrawn?.(); }, [props.routes]);
    return null;
  }),
}));
jest.mock('../src/location/heading', () => ({ useHeading: () => null }));
jest.mock('../src/location/currentLocation', () => ({ currentCoordinate: jest.fn(), warmUpLocation: jest.fn(async () => {}) }));
jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn(), watchPositionAsync: jest.fn(), Accuracy: { BestForNavigation: 6 } }));

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(api.searchPlaces).mockImplementation(async query => ({
    places: places.filter(p => p.name.toLowerCase().includes(query.toLowerCase())), attribution: '© OpenStreetMap contributors',
  }));
  jest.mocked(api.getRouteHistory).mockResolvedValue({ items: [saved] });
  jest.mocked(api.getRoutes).mockResolvedValue(result);
  // no forecast by default, so routes ask for the 84°F starting temperature
  jest.mocked(api.getCurrentTemperature).mockRejectedValue(new Error('Offline'));
  jest.mocked(currentCoordinate).mockResolvedValue(places[0].coordinate);
});

type Forecast = Awaited<ReturnType<typeof api.getCurrentTemperature>>;
const forecastOf = (temperature_f: number): Forecast => ({
  temperature_f, temperature_c: (temperature_f - 32) / 1.8, valid_from: '', valid_to: '', source: 'US National Weather Service hourly forecast',
});
const slowForecast = () => {
  let finish!: (value: Forecast) => void;
  jest.mocked(api.getCurrentTemperature).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  return (temperature_f: number) => act(async () => { finish(forecastOf(temperature_f)); });
};

// recents show in the search dropdown as soon as a box is focused, before you type
const openSearch = async (box = 'Choose destination') => { await fireEvent(screen.getByPlaceholderText(box), 'focus'); };
const openRecent = async (name: string) => {
  await openSearch();
  await fireEvent.press(await screen.findByLabelText(`Recent place: ${name}`));
};
const SPOT: [number, number] = [-118.443, 34.0725];
// a saved walk to place_id (null: back to your location), from a place or (null) from your location
const going = (place_id: string | null, id: string, from: string | null = 'royce-hall'): SavedRoute => ({
  ...saved, id, request: {
    ...saved.request,
    origin: from ? { place_id: from, coordinate: null } : { place_id: null, coordinate: SPOT },
    destination: place_id ? { place_id, coordinate: null } : { place_id: null, coordinate: SPOT },
  },
});

test('recents are just the places you walked to, each once, newest first', async () => {
  jest.mocked(api.getRouteHistory).mockResolvedValue({ items: [
    going('powell-library', 'a'),
    going('powell-library', 'b', null), // same place from your location: shown once
    going('ackerman-union', 'c'),
    going(null, 'd'), // a walk back to your location has no place to offer
  ] });
  await render(<App />);
  await openSearch();
  await screen.findByText('Recent');
  await waitFor(() => expect(screen.getAllByLabelText(/Recent place:/).map(row => row.props.accessibilityLabel))
    .toEqual(['Recent place: Powell Library', 'Recent place: Ackerman Union']));
  // where you started from is never shown
  expect(screen.queryByText(/→/)).toBeNull();
  expect(screen.queryByText('Try like Powell or Bplate.')).toBeNull();

  // typing turns the dropdown into place results
  await fireEvent.changeText(screen.getByPlaceholderText('Choose destination'), 'royce');
  await screen.findByText('Royce Hall');
  expect(screen.queryAllByLabelText(/Recent place:/)).toHaveLength(0);
});

test('picking a recent plans a fresh route to it from where you are now', async () => {
  await render(<App />);
  await openRecent('Powell Library');
  await waitFor(() => expect(api.getRoutes).toHaveBeenCalledWith({ coordinate: places[0].coordinate }, { place_id: 'powell-library' }, 84));
  await screen.findByText('Walking to');
  expect(screen.getByText('Start')).toBeTruthy();
});

test('a recent fills the start box when that is the box you are in', async () => {
  await render(<App />);
  await openSearch('Choose starting point');
  await fireEvent.press(await screen.findByLabelText('Recent place: Powell Library'));
  expect(screen.getByDisplayValue('Powell Library')).toBeTruthy();
});

test('recents use the real place names, not the slug', async () => {
  const rubios = { id: 'rubio-s', name: 'Rubio’s', coordinate: places[1].coordinate, category: 'Restaurant', address: null };
  jest.mocked(api.searchPlaces).mockImplementation(async query => ({
    places: query === 'rubio s' ? [rubios] : places.filter(p => p.name.toLowerCase().includes(query.toLowerCase())), attribution: '',
  }));
  jest.mocked(api.getRouteHistory).mockResolvedValue({ items: [going('rubio-s', 'a')] });
  await render(<App />);
  await openSearch();
  await screen.findByLabelText('Recent place: Rubio’s');
});

test('the list is read again every time search opens, so a route you just calculated shows up', async () => {
  await render(<App />);
  const box = screen.getByPlaceholderText('Choose destination');
  await openSearch();
  await fireEvent(box, 'blur');
  await openSearch();
  await waitFor(() => expect(api.getRouteHistory).toHaveBeenCalledTimes(2));
});

test('pressing Start leaves the dot where it is until you actually walk', async () => {
  jest.mocked(Location.requestForegroundPermissionsAsync).mockResolvedValue({ granted: true } as any);
  let send!: (sample: unknown) => void;
  jest.mocked(Location.watchPositionAsync).mockImplementation(async (_options, callback) => { send = callback as any; return { remove: jest.fn() } as any; });
  await render(<App />);
  await openRecent('Powell Library');
  await fireEvent.press(await screen.findByText('Start'));
  await screen.findByText('End walk');
  const fix = (lon: number, lat: number) => act(async () => { send({ coords: { longitude: lon, latitude: lat, accuracy: 5 } }); });
  const position = () => jest.mocked(ShadyMap).mock.lastCall?.[0].position;
  const [lon, lat] = places[0].coordinate;

  await fix(lon, lat);
  await fix(lon + 0.00003, lat); // about 3 m: gps wander while you stand there
  expect(position()).toBeNull();

  await fix(lon - 0.00015, lat - 0.0002); // about 25 m down the route
  expect(position()).not.toBeNull();
});

test('tapping the logo goes back to Where to? from a route', async () => {
  await render(<App />);
  await openRecent('Powell Library');
  await screen.findByText('Walking to');
  await fireEvent.press(screen.getByLabelText('Shady Business, back to Where to?'));
  await screen.findByText('Where to?');
  expect(screen.queryByText('Walking to')).toBeNull();
  expect(screen.getByDisplayValue('Your location')).toBeTruthy();
});

test('a history failure just leaves recents out and search still works', async () => {
  jest.mocked(api.getRouteHistory).mockRejectedValueOnce(new Error('Offline'));
  await render(<App />);
  await openSearch();
  await waitFor(() => expect(api.getRouteHistory).toHaveBeenCalledTimes(1));
  expect(screen.queryByText('Recent')).toBeNull();
  expect(screen.getByText('Try like Powell or Bplate.')).toBeTruthy();
  await fireEvent.changeText(screen.getByPlaceholderText('Choose destination'), 'royce');
  await screen.findByText('Royce Hall');
});

// a new temperature re-routes, so an answer that shows up after you've moved
// on would throw away the route you're looking at or the one you're walking
test('a late forecast never replaces your route or a walk you started', async () => {
  const forecastLands = slowForecast();
  await render(<App />);
  await openRecent('Powell Library');
  await screen.findByText('Start');
  await forecastLands(91);
  expect(screen.getByText('Forecast is 91°F')).toBeTruthy();
  expect(api.getRoutes).toHaveBeenCalledTimes(1);
  expect(api.getRoutes).toHaveBeenCalledWith({ coordinate: places[0].coordinate }, { place_id: 'powell-library' }, 84);

  jest.mocked(Location.requestForegroundPermissionsAsync).mockResolvedValue({ granted: true } as any);
  jest.mocked(Location.watchPositionAsync).mockResolvedValue({ remove: jest.fn() } as any);
  const secondLands = slowForecast();
  await fireEvent.press(screen.getByText('Use forecast'));
  await fireEvent.press(screen.getByText('Start'));
  await screen.findByText('End walk');
  await secondLands(93);
  expect(screen.getByText('End walk')).toBeTruthy();
  expect(api.getRoutes).toHaveBeenCalledTimes(1);

  await fireEvent.press(screen.getByText('End walk'));
  expect(screen.getByText('Walking to')).toBeTruthy();
  expect(screen.getByText('Forecast is 93°F')).toBeTruthy();
});
