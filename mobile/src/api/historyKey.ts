import { randomUUID } from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

const STORAGE_KEY = 'shady-business.route-history-key';
let pendingKey: Promise<string> | undefined;

// One private installation key, shared by simultaneous history/read requests.
export function getHistoryKey(): Promise<string> {
  if (!pendingKey) {
    pendingKey = (async () => {
      const stored = await SecureStore.getItemAsync(STORAGE_KEY);
      if (stored) return stored;
      const created = randomUUID();
      await SecureStore.setItemAsync(STORAGE_KEY, created);
      return created;
    })().catch(error => {
      pendingKey = undefined;
      throw error;
    });
  }
  return pendingKey;
}
