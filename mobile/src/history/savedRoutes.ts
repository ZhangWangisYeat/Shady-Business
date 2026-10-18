import type { SavedRoute } from '../api/types';

// history only keeps place ids, which are slugs of the names, so searching the
// slug with spaces finds the place again ("rubio s" finds Rubio's)
export const slugQuery = (id: string) => id.replace(/-\d+$/, '').replace(/-/g, ' ');

// recents are just places you went to. the start isn't kept: where you were
// last time usually isn't where you are now, so a saved "from" only misleads.
// a place you walked to from two different starts shows up once, newest first,
// and a walk back to your own location has no place to offer, so it's skipped.
export function recentDestinations(items: SavedRoute[], limit = 5): string[] {
  const ids: string[] = [];
  for (const item of items) {
    const id = item.request.destination.place_id;
    if (id && !ids.includes(id)) ids.push(id);
    if (ids.length === limit) break;
  }
  return ids;
}
