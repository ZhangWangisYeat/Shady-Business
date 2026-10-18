import * as Location from 'expo-location';

jest.mock('expo-location', () => ({
  getForegroundPermissionsAsync: jest.fn(), requestForegroundPermissionsAsync: jest.fn(),
  getLastKnownPositionAsync: jest.fn(), getCurrentPositionAsync: jest.fn(), Accuracy: { High: 4 },
}));

const ROYCE = { coords: { longitude: -118.4422, latitude: 34.0728 } };
// the module keeps the fix that's on its way, so each test gets a fresh copy
const load = () => { let mod!: typeof import('../src/location/currentLocation'); jest.isolateModules(() => { mod = require('../src/location/currentLocation'); }); return mod; };

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(Location.getForegroundPermissionsAsync).mockResolvedValue({ granted: true } as any);
  jest.mocked(Location.requestForegroundPermissionsAsync).mockResolvedValue({ granted: true } as any);
  jest.mocked(Location.getLastKnownPositionAsync).mockResolvedValue(null);
});

test('opening search starts the fix that the route request then uses', async () => {
  let land!: (fix: unknown) => void;
  jest.mocked(Location.getCurrentPositionAsync).mockReturnValue(new Promise(resolve => { land = resolve; }) as any);
  const { warmUpLocation, currentCoordinate } = load();
  await warmUpLocation();
  const asked = currentCoordinate();
  land(ROYCE);
  await expect(asked).resolves.toEqual([-118.4422, 34.0728]);
  // one gps request, not one for the warm-up and another for the route
  expect(Location.getCurrentPositionAsync).toHaveBeenCalledTimes(1);
});

test('the warm-up never asks for permission', async () => {
  jest.mocked(Location.getForegroundPermissionsAsync).mockResolvedValue({ granted: false } as any);
  const { warmUpLocation } = load();
  await warmUpLocation();
  expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  expect(Location.getCurrentPositionAsync).not.toHaveBeenCalled();
});

test('a failed fix is not kept, so the next try asks again', async () => {
  jest.mocked(Location.getCurrentPositionAsync).mockRejectedValueOnce(new Error('no fix')).mockResolvedValueOnce(ROYCE as any);
  const { currentCoordinate } = load();
  await expect(currentCoordinate()).rejects.toThrow('no fix');
  await expect(currentCoordinate()).resolves.toEqual([-118.4422, 34.0728]);
});
