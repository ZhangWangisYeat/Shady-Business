import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as api from '../src/api/client';
import App from '../App';

jest.mock('../src/api/client', () => ({
  searchPlaces: jest.fn(), getRouteHistory: jest.fn(), getRoutes: jest.fn(), getCurrentTemperature: jest.fn(),
  ApiError: class extends Error {},
}));
jest.mock('../src/map/ShadyMap', () => ({ ShadyMap: () => null }));
jest.mock('../src/location/heading', () => ({ useHeading: () => null, bearing: () => 0 }));
jest.mock('../src/location/currentLocation', () => ({ currentCoordinate: jest.fn() }));
jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn(), watchPositionAsync: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(api.getRouteHistory).mockResolvedValue({ items: [] });
  jest.mocked(api.getCurrentTemperature).mockResolvedValue({
    temperature_f: 77.4, temperature_c: 25.2, valid_from: '', valid_to: '', source: 'US National Weather Service hourly forecast',
  });
});

test('the forecast fills in the temperature until you type your own', async () => {
  await render(<App />);
  await screen.findByText('77°F');
  expect(screen.getByText('Forecast from National Weather Service')).toBeTruthy();

  await fireEvent.press(screen.getByLabelText('Type a temperature'));
  const input = screen.getByDisplayValue('77');
  await fireEvent.changeText(input, '95');
  await fireEvent(input, 'submitEditing');
  await screen.findByText('95°F');
  expect(screen.queryByText('Forecast from National Weather Service')).toBeNull();

  await fireEvent.press(screen.getByText('Use forecast'));
  await screen.findByText('77°F');
  await waitFor(() => expect(api.getCurrentTemperature).toHaveBeenCalledTimes(2));
});

test('the steppers keep working while you type', async () => {
  await render(<App />);
  await screen.findByText('77°F');
  await fireEvent.press(screen.getByLabelText('Type a temperature'));
  await fireEvent.changeText(screen.getByDisplayValue('77'), '90');
  await fireEvent.press(screen.getByLabelText('Warmer'));
  expect(screen.getByDisplayValue('92')).toBeTruthy();
  await fireEvent(screen.getByDisplayValue('92'), 'submitEditing');
  await screen.findByText('92°F');
});

test('a forecast failure keeps a usable temperature and offers a retry', async () => {
  jest.mocked(api.getCurrentTemperature).mockRejectedValueOnce(new Error('offline'));
  await render(<App />);
  await screen.findByText('Couldn’t get the forecast');
  expect(screen.getByText('84°F')).toBeTruthy();
  await fireEvent.press(screen.getByText('Retry'));
  await screen.findByText('77°F');
});
