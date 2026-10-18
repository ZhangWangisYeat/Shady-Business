import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as api from '../src/api/client';
import * as Location from 'expo-location';
import { RecentRoutes } from '../src/components/RecentRoutes';
import { ShadyMap } from '../src/map/ShadyMap';
import App from '../App';
import { places, result, saved } from './fixtures';

jest.mock('../src/api/client', () => ({
  getPlaces: jest.fn(), getRouteHistory: jest.fn(), getRoutes: jest.fn(),
  ApiError: class extends Error {},
}));
jest.mock('../src/map/ShadyMap', () => ({ ShadyMap: jest.fn(() => null) }));
jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(api.getPlaces).mockResolvedValue({ places });
  jest.mocked(api.getRouteHistory).mockResolvedValue({ items: [saved] });
  jest.mocked(api.getRoutes).mockResolvedValue(result);
});

test('dropdown starts collapsed and displays no more than five saved routes', async () => {
  jest.mocked(api.getRouteHistory).mockResolvedValue({
    items: Array.from({ length: 6 }, (_, i) => ({ ...saved, id: `saved-${i}` })),
  });
  await render(<RecentRoutes places={places} onSelect={jest.fn()} />);
  await screen.findByText('Recent routes · 5');
  expect(screen.queryByText('Royce Hall → Powell Library')).toBeNull();
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  expect(screen.getAllByRole('button', { name: /View saved route:/ })).toHaveLength(5);
  expect(screen.getAllByText(/77°F/)).toHaveLength(5);
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  expect(screen.queryByText('Royce Hall → Powell Library')).toBeNull();
});

test('selecting history previews its saved geometry without calculation or GPS', async () => {
  await render(<App />);
  await screen.findByText('Recent routes · 1');
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  await fireEvent.press(screen.getByRole('button', { name: /View saved route:/ }));
  expect(screen.getByText('Choose your walk')).toBeTruthy();
  expect(screen.getByText(/Historical shade estimate/)).toBeTruthy();
  expect(screen.getByText(/Saved route · .*77°F/)).toBeTruthy();
  expect(screen.queryByText('Start guided walk')).toBeNull();
  expect(api.getRoutes).not.toHaveBeenCalled();
  expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  expect(jest.mocked(ShadyMap).mock.lastCall?.[0].route).toEqual(result.routes[1]);

  await fireEvent.press(screen.getByText('Update for guided walk'));
  await screen.findByText('Start guided walk');
  expect(api.getRoutes).toHaveBeenCalledWith('royce-hall', 'powell-library', 84.2);
  expect(screen.queryByText(/Historical shade estimate/)).toBeNull();
  expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  await fireEvent.press(screen.getByText('Change destination'));
  await screen.findByText('Recent routes · 1');
  expect(api.getRouteHistory).toHaveBeenCalledTimes(2);
});

test('a calculation already in flight cannot replace a selected historical preview', async () => {
  let finish!: (value: typeof result) => void;
  jest.mocked(api.getRoutes).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  await render(<App />);
  await screen.findByText('Recent routes · 1');
  await fireEvent.press(screen.getByText('Find walking routes'));
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  await fireEvent.press(screen.getByRole('button', { name: /View saved route:/ }));
  await act(async () => { finish(result); });
  expect(screen.getByText(/Historical shade estimate/)).toBeTruthy();
  expect(screen.queryByText('Start guided walk')).toBeNull();
});

test('history failure offers a local retry and does not block ordinary search', async () => {
  jest.mocked(api.getRouteHistory).mockRejectedValueOnce(new Error('Offline'));
  await render(<App />);
  await waitFor(() => expect(api.getRouteHistory).toHaveBeenCalledTimes(1));
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  await screen.findByText('Couldn’t load recent routes.');
  expect(screen.getByText('Find walking routes')).toBeTruthy();
  await fireEvent.press(screen.getByRole('button', { name: 'Retry' }));
  await screen.findByText('Royce Hall → Powell Library');
});

test('starting a saved-route demo cancels an in-flight update and keeps its preview', async () => {
  let finish!: (value: typeof result) => void;
  jest.mocked(api.getRoutes).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  await render(<App />);
  await screen.findByText('Recent routes · 1');
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  await fireEvent.press(screen.getByRole('button', { name: /View saved route:/ }));
  await fireEvent.press(screen.getByText('Update for guided walk'));
  await fireEvent.press(screen.getByText('Demo walk (no GPS)'));
  await act(async () => { finish(result); });
  expect(screen.getByText('Demo navigation')).toBeTruthy();
  expect(screen.queryByText('Choose your walk')).toBeNull();
  await fireEvent.press(screen.getByText('End navigation'));
  expect(screen.getByText(/Historical shade estimate/)).toBeTruthy();
});

test('empty and loading states stay inside the dropdown', async () => {
  let finish!: (value: { items: [] }) => void;
  jest.mocked(api.getRouteHistory).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  await render(<RecentRoutes places={places} onSelect={jest.fn()} />);
  await fireEvent.press(screen.getByRole('button', { name: 'Recent routes' }));
  expect(screen.getByText('Loading recent routes…')).toBeTruthy();
  await act(async () => { finish({ items: [] }); });
  expect(screen.getByText('Your last 5 routes will appear here after a search.')).toBeTruthy();
});
