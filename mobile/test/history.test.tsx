import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as api from '../src/api/client';
import * as Location from 'expo-location';
import { RecentRoutes } from '../src/components/RecentRoutes';
import { ShadyMap } from '../src/map/ShadyMap';
import App from '../App';
import { places, result, saved } from './fixtures';

jest.mock('../src/api/client', () => ({
  searchPlaces: jest.fn(), getRouteHistory: jest.fn(), getRoutes: jest.fn(),
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
jest.mock('../src/location/heading', () => ({ useHeading: () => null, bearing: () => 0 }));
jest.mock('../src/location/currentLocation', () => ({ currentCoordinate: jest.fn() }));
jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn(), watchPositionAsync: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(api.searchPlaces).mockImplementation(async query => ({
    places: places.filter(p => p.name.toLowerCase().includes(query.toLowerCase())), attribution: '© OpenStreetMap contributors',
  }));
  jest.mocked(api.getRouteHistory).mockResolvedValue({ items: [saved] });
  jest.mocked(api.getRoutes).mockResolvedValue(result);
});

test('recent routes start collapsed on the where-to sheet and list at most five', async () => {
  jest.mocked(api.getRouteHistory).mockResolvedValue({
    items: Array.from({ length: 6 }, (_, i) => ({ ...saved, id: `saved-${i}` })),
  });
  await render(<App />);
  await screen.findByText('Recent routes · 5');
  expect(screen.queryByText('Royce Hall → Powell Library')).toBeNull();
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  expect(screen.getAllByRole('button', { name: /View saved route:/ })).toHaveLength(5);
  expect(screen.getAllByText(/77°F/)).toHaveLength(5);
});

test('opening a saved route shows its snapshot without calculating or asking for GPS', async () => {
  await render(<App />);
  await screen.findByText('Recent routes · 1');
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  await fireEvent.press(screen.getByRole('button', { name: /View saved route:/ }));
  await screen.findByText('Saved route');
  expect(screen.getByText(/Calculated .*77°F\. Shade is as it was then/)).toBeTruthy();
  expect(screen.queryByText('Start')).toBeNull();
  expect(api.getRoutes).not.toHaveBeenCalled();
  expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  expect(jest.mocked(ShadyMap).mock.lastCall?.[0].routes).toEqual(result.routes);

  await fireEvent.press(screen.getByText('Update for current conditions'));
  await waitFor(() => expect(api.getRoutes).toHaveBeenCalledWith({ place_id: 'royce-hall' }, { place_id: 'powell-library' }, 84));
  await waitFor(() => expect(screen.queryByText(/Shade is as it was then/)).toBeNull());
  expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
});

test('a history failure offers a retry and leaves search usable', async () => {
  jest.mocked(api.getRouteHistory).mockRejectedValueOnce(new Error('Offline'));
  await render(<App />);
  await waitFor(() => expect(api.getRouteHistory).toHaveBeenCalledTimes(1));
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  await screen.findByText('Couldn’t load recent routes.');
  expect(screen.getByText('Where to?')).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Retry' }));
  await screen.findByText('Royce Hall → Powell Library');
});

test('empty and loading states stay inside the dropdown', async () => {
  let finish!: (value: { items: [] }) => void;
  jest.mocked(api.getRouteHistory).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  await render(<RecentRoutes onSelect={jest.fn()} />);
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  expect(screen.getByText('Loading recent routes…')).toBeTruthy();
  await act(async () => { finish({ items: [] }); });
  expect(screen.getByText(/Walks from your location are never saved/)).toBeTruthy();
});
