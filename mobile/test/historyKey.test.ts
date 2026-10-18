jest.mock('expo-crypto', () => ({ randomUUID: jest.fn() }));
jest.mock('expo-secure-store', () => ({ getItemAsync: jest.fn(), setItemAsync: jest.fn() }));

beforeEach(() => { jest.resetModules(); });

test('parallel requests create and persist only one private installation UUID', async () => {
  const storage = require('expo-secure-store');
  const crypto = require('expo-crypto');
  storage.getItemAsync.mockResolvedValue(null);
  storage.setItemAsync.mockResolvedValue(undefined);
  crypto.randomUUID.mockReturnValue('bfb77111-84f0-4011-a111-2d1941527611');
  const { getHistoryKey } = require('../src/api/historyKey');
  const keys = await Promise.all([getHistoryKey(), getHistoryKey(), getHistoryKey()]);
  expect(new Set(keys).size).toBe(1);
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
  expect(storage.setItemAsync).toHaveBeenCalledWith('shady-business.route-history-key', keys[0]);
});

test('app restart reuses the stored key and a failed storage read can be retried', async () => {
  const storage = require('expo-secure-store');
  const crypto = require('expo-crypto');
  storage.getItemAsync.mockRejectedValueOnce(new Error('Temporarily unavailable')).mockResolvedValue('existing-key');
  const { getHistoryKey } = require('../src/api/historyKey');
  await expect(getHistoryKey()).rejects.toThrow('Temporarily unavailable');
  expect(await getHistoryKey()).toBe('existing-key');
  expect(crypto.randomUUID).not.toHaveBeenCalled();
  expect(storage.setItemAsync).not.toHaveBeenCalled();
});
