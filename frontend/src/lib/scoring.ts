export const RANK_POINTS = [3, 2, 1] as const;

export type Candidate = { id: string; name: string };
export type BallotLike = { choices: string[] };
export type Standing = {
  restaurant_id: string;
  name: string;
  score: number;
  first: number;
  second: number;
  third: number;
};

/** Positional ranked points (3/2/1). Sorted for display: score, 1st, 2nd, then name. */
export function tally(candidates: Candidate[], ballots: BallotLike[]): Standing[] {
  const map = new Map<string, Standing>();
  for (const c of candidates)
    map.set(c.id, { restaurant_id: c.id, name: c.name, score: 0, first: 0, second: 0, third: 0 });
  for (const b of ballots) {
    b.choices.slice(0, 3).forEach((id, i) => {
      const row = map.get(id);
      if (!row) return;
      row.score += RANK_POINTS[i];
      if (i === 0) row.first++;
      else if (i === 1) row.second++;
      else row.third++;
    });
  }
  return [...map.values()].sort(
    (a, b) =>
      b.score - a.score ||
      b.first - a.first ||
      b.second - a.second ||
      a.name.localeCompare(b.name),
  );
}

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
  [next[index], next[j]] = [next[j], next[index]];
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
  return { next: next.slice(0, max), dropped: next.length > max ? next[max] : null };
}

export const TIE_BREAK_LABEL: Record<string, string> = {
  first_place_votes: "Tie on points — decided by most 1st-place votes.",
  second_place_votes: "Tie on points and 1st-place votes — decided by most 2nd-place votes.",
  random_draw: "Complete tie — decided by a fair, reproducible random draw.",
};
