import type { Coordinate, Place, RoutesResponse, SavedRoute } from './types';
import { getHistoryKey } from './historyKey';
const BASE = process.env.EXPO_PUBLIC_API_URL;

type ApiErrorDetail = { code?: unknown; message?: unknown; retryable?: unknown; field?: unknown };

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    message: string,
    public readonly retryable = false,
    public readonly field?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function detailFrom(value: unknown): ApiErrorDetail {
  if (!value || typeof value !== 'object') return {};
  const detail = (value as { detail?: unknown }).detail;
  return detail && typeof detail === 'object' ? detail as ApiErrorDetail : {};
}

async function json<T>(path: string, init?: RequestInit, timeoutMs=9000): Promise<T> {
  if (!BASE) throw new ApiError('API_NOT_CONFIGURED',0,'The route service is not configured on this device.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const result = await fetch(`${BASE.replace(/\/$/, '')}${path}`, {
      ...init, signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
    if (!result.ok) {
      let info: unknown;
      try { info = await result.json(); } catch { /* non-JSON server error */ }
      const detail=detailFrom(info);
      throw new ApiError(
        typeof detail.code === 'string' ? detail.code : 'API_ERROR',
        result.status,
        typeof detail.message === 'string' ? detail.message : 'The route service could not complete this request.',
        detail.retryable === true || result.status >= 500,
        typeof detail.field === 'string' ? detail.field : undefined,
      );
    }
    try { return await result.json() as T; }
    catch { throw new ApiError('INVALID_RESPONSE',result.status,'The route service returned an invalid response.',true); }
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.name === 'AbortError') {
      throw new ApiError('REQUEST_TIMEOUT',0,'Route calculation took too long. Please try again.',true);
    }
    throw new ApiError('NETWORK_ERROR',0,'Cannot reach the route service. Check your connection and try again.',true);
  } finally { clearTimeout(timer); }
}
export const getPlaces = () => json<{ places: Place[] }>('/api/places',undefined,5000);
export const getRouteHistory = async () => json<{ items: SavedRoute[] }>('/api/routes/history', {
  headers: { 'X-Route-History-Key': await getHistoryKey() },
});

export const getRoutes = async (origin: string, destination: string, temperatureF: number) => {
  let historyKey: string | undefined;
  try { historyKey = await getHistoryKey(); } catch { /* A storage error must not block a new walk. */ }
  return json<RoutesResponse>('/api/routes', {
    method: 'POST',
    headers: historyKey ? { 'X-Route-History-Key': historyKey } : {},
    body: JSON.stringify({
      origin: { place_id: origin }, destination: { place_id: destination },
      departure_time: new Date().toISOString(), temperature_c: (temperatureF - 32) * 5 / 9,
    }),
  }, 20000);
};
