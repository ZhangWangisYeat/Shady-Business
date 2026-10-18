jest.mock('../src/api/historyKey', () => ({ getHistoryKey: jest.fn() }));

beforeEach(() => {
  jest.resetModules();
  process.env.EXPO_PUBLIC_API_URL = 'http://route-service.test';
  globalThis.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) });
});

test('history and route calculations use the same device key and keep the Celsius contract', async () => {
  const { getHistoryKey } = require('../src/api/historyKey');
  getHistoryKey.mockResolvedValue('device-key');
  const { getRouteHistory, getRoutes, searchPlaces } = require('../src/api/client');
  await getRouteHistory();
  await getRoutes({ place_id: 'royce-hall' }, { place_id: 'ackerman-union' }, 77);
  await searchPlaces('royce');
  const calls = jest.mocked(fetch).mock.calls;
  expect(calls[0][0]).toBe('http://route-service.test/api/routes/history');
  expect(calls[0][1]?.headers).toMatchObject({ 'X-Route-History-Key': 'device-key' });
  expect(calls[1][1]?.headers).toMatchObject({ 'X-Route-History-Key': 'device-key' });
  expect(JSON.parse(calls[1][1]?.body as string).temperature_c).toBe(25);
  expect(calls[2][1]?.headers).not.toHaveProperty('X-Route-History-Key');
});

test('storage failure leaves new searches working without a history header', async () => {
  const { getHistoryKey } = require('../src/api/historyKey');
  getHistoryKey.mockRejectedValue(new Error('Storage unavailable'));
  const { getRouteHistory, getRoutes } = require('../src/api/client');
  await getRoutes({ place_id: 'royce-hall' }, { place_id: 'ackerman-union' }, 77);
  expect(jest.mocked(fetch).mock.calls[0][1]?.headers).not.toHaveProperty('X-Route-History-Key');
  await expect(getRouteHistory()).rejects.toThrow('Storage unavailable');
});
