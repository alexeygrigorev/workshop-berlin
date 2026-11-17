// Scoring and tie-breaks are computed by the server (standings in the poll response); only ballot-editing helpers live here.

/** Tap-to-rank: tapping a picked item removes it (compacting); otherwise appends if room. */
export function toggleChoice(selected: string[], id: string, max = 3): { next: string[]; full: boolean } {
  if (selected.includes(id)) return { next: selected.filter((x) => x !== id), full: false };
  if (selected.length >= max) return { next: selected, full: true };
  return { next: [...selected, id], full: false };
}

export function moveChoice(selected: string[], index: number, dir: -1 | 1): string[] {
  const j = index + dir;
  if (j < 0 || j >= selected.length) return selected;
  const next = [...selected];
  [next[index], next[j]] = [next[j]!, next[index]!];
  return next;
}

/**
 * Put `id` at rank `index` (0-based), shifting later picks down; a pick pushed past `max` drops off.
 * Choosing the rank it already holds removes it. Ranks stay gap-free: an index past the end appends.
 */
export function placeChoice(selected: string[], id: string, index: number, max = 3): { next: string[]; dropped: string | null } {
  if (selected[index] === id) return { next: selected.filter((x) => x !== id), dropped: null };
  const rest = selected.filter((x) => x !== id);
  const next = [...rest.slice(0, index), id, ...rest.slice(index)];
  return { next: next.slice(0, max), dropped: next.length > max ? (next[max] ?? null) : null };
}

export const TIE_BREAK_LABEL: Record<string, string> = {
  first_place_votes: "Tie on points — decided by most 1st-place votes.",
  second_place_votes: "Tie on points and 1st-place votes — decided by most 2nd-place votes.",
  random_draw: "Complete tie — decided by a fair, reproducible random draw.",
};
