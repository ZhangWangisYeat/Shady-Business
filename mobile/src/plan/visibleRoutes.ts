import type { Route } from '../api/types';
import { distinctShare } from './pathDifference';

type Mode = Route['mode'];
// alternate: a walk that tied with another on time and shade but goes a
// noticeably different way, so it's offered as an option without a name
export type RouteCard = { route: Route; modes: Mode[]; alternate?: boolean };

const MODE_ORDER: Mode[] = ['recommended', 'fastest', 'maximum_shade'];
const NAMES: Record<Mode, string> = { recommended: 'Recommended', fastest: 'Fastest', maximum_shade: 'Shadiest' };
// the cards only show whole minutes, so anything inside a minute reads as the
// same walk time
const SAME_TIME_S = 60;
// two routes this close in sun feel the same to walk
const sameSunS = (a: Route, b: Route) => Math.max(15, 0.05 * Math.min(a.duration_s, b.duration_s));
// past this share of unknown time, comparing shade would just be guessing
const MOSTLY_UNKNOWN = 0.5;
// at least this much of a walk on different paths makes it a real alternative
const DIFFERENT_PATH = 0.25;
const differs = (a: Route, b: Route) =>
  distinctShare(a.geometry.coordinates, b.geometry.coordinates) >= DIFFERENT_PATH
  && distinctShare(b.geometry.coordinates, a.geometry.coordinates) >= DIFFERENT_PATH;

// same_as points a duplicate at the first mode with that exact path, so two
// routes with the same key are the same walk
const pathKey = (route: Route) => route.same_as ?? route.id;
const rank = (card: RouteCard) => Math.min(...card.modes.map(m => MODE_ORDER.indexOf(m)));
const unknownShare = (route: Route) => (route.duration_s ? route.unknown_seconds / route.duration_s : 1);
// known sun time; a route with a little unknown is still compared on what is known
const sunOf = (route: Route) => route.sun_seconds ?? route.segments.reduce((sum, s) => sum + (s.sun_seconds ?? 0), 0);

export function visibleRoutes(routes: Route[]): RouteCard[] {
  const fastest = routes.find(r => r.mode === 'fastest') ?? routes[0];
  if (!fastest) return [];
  // one path, or shade we mostly can't see: there's nothing to choose between
  if (new Set(routes.map(pathKey)).size <= 1 || routes.every(r => unknownShare(r) >= MOSTLY_UNKNOWN)) {
    return [{ route: fastest, modes: ['fastest'] }];
  }
  const recommended = routes.find(r => r.mode === 'recommended');
  let cards: RouteCard[] = routes
    .filter(r => !(r.mode === 'maximum_shade' && recommended && pathKey(r) === pathKey(recommended)))
    .map(route => ({ route, modes: [route.mode] }));

  // a route is folded into another walk within a minute of it that has either
  // more shade, or about the same shade and is quicker. the card that's left
  // carries both names, so nothing the user asked about disappears.
  const comparable = (card: RouteCard) => unknownShare(card.route) < MOSTLY_UNKNOWN;
  const tied: Route[] = [];
  for (let changed = true; changed;) {
    changed = false;
    const byTime = [...cards].sort((a, b) => a.route.duration_s - b.route.duration_s);
    for (const card of byTime) {
      if (!comparable(card)) continue;
      const near = cards.filter(o => o !== card && comparable(o) && Math.abs(o.route.duration_s - card.route.duration_s) <= SAME_TIME_S);
      const shadier = near
        .filter(o => sunOf(o.route) < sunOf(card.route) - sameSunS(o.route, card.route))
        .sort((a, b) => sunOf(a.route) - sunOf(b.route))[0];
      const twin = near.find(o => Math.abs(sunOf(o.route) - sunOf(card.route)) <= sameSunS(o.route, card.route)
        && byTime.indexOf(o) < byTime.indexOf(card));
      const into = shadier ?? twin;
      if (!into) continue;
      into.modes = [...into.modes, ...card.modes];
      cards = cards.filter(c => c !== card);
      tied.push(card.route);
      changed = true;
      break;
    }
  }
  // the names went to the winners, but a tied walk that takes a genuinely
  // different way is still worth offering, as long as it isn't a repeat of a
  // route already on the list
  const alternates: RouteCard[] = [];
  for (const route of tied.sort((a, b) => a.duration_s - b.duration_s)) {
    if ([...cards, ...alternates].every(c => differs(route, c.route))) alternates.push({ route, modes: [], alternate: true });
  }
  return [...cards.sort((a, b) => rank(a) - rank(b)), ...alternates];
}

export function cardLabel(card: RouteCard, cards?: RouteCard[]): string {
  if (card.alternate) {
    const all = (cards ?? []).filter(c => c.alternate);
    return all.length > 1 ? `Alternate route ${all.indexOf(card) + 1}` : 'Alternate route';
  }
  // one walk that's both the fastest and the shadiest is plainly the one to
  // take, so "recommended" would only make the name longer
  let modes = MODE_ORDER.filter(m => card.modes.includes(m));
  if (modes.includes('fastest') && modes.includes('maximum_shade')) modes = modes.filter(m => m !== 'recommended');
  const names = modes.map((m, i) => (i === 0 ? NAMES[m] : NAMES[m].toLowerCase()));
  return names.length <= 1 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

export function defaultMode(routes: Route[]): Mode {
  const cards = visibleRoutes(routes);
  return (cards.find(c => c.modes.includes('recommended')) ?? cards[0])?.route.mode ?? 'fastest';
}
