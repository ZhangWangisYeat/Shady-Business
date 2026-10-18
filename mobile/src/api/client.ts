import type { PlacesResponse, RouteEndpoint, RoutesResponse } from './types';
const BASE = process.env.EXPO_PUBLIC_API_URL;

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE) throw new Error('Set EXPO_PUBLIC_API_URL to a backend address reachable from this phone.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 9000);
  try {
    const result = await fetch(`${BASE.replace(/\/$/, '')}${path}`, {
      ...init, signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
    if (!result.ok) {
      let info: any;
      try { info = await result.json(); } catch { /* non-JSON server error */ }
      throw new Error(info?.detail?.message ?? `API error ${result.status}`);
    }
    return await result.json() as T;
  } finally { clearTimeout(timer); }
}
export const searchPlaces = (query: string, limit = 8) =>
  json<PlacesResponse>(`/api/places?q=${encodeURIComponent(query)}&limit=${limit}`);
export const getRoutes = (origin: RouteEndpoint, destination: RouteEndpoint, temperatureC: number) => json<RoutesResponse>('/api/routes', {
  method: 'POST', body: JSON.stringify({
    origin, destination,
    departure_time: new Date().toISOString(), temperature_c: temperatureC,
  })
});
