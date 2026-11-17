"""Pure scoring / tie-break logic (specs.md section 7). No I/O, no clock."""
from __future__ import annotations

import random
from dataclasses import dataclass
from uuid import UUID


@dataclass
class Tally:
    restaurant_id: UUID
    name: str
    first: int = 0
    second: int = 0
    third: int = 0

    @property
    def score(self) -> int:
        return 3 * self.first + 2 * self.second + self.third


@dataclass
class Result:
    ordered: list[Tally]  # display/final order; position 1 is the winner when final
    winner_id: UUID | None
    no_winner: bool
    tie_break: str | None  # first_place_votes | second_place_votes | random_draw | None


def tally(candidates: dict[UUID, str], ballots: list[list[UUID]]) -> dict[UUID, Tally]:
    """candidates: id -> name. ballots: ranked choice lists. Unknown IDs are ignored."""
    t = {cid: Tally(cid, name) for cid, name in candidates.items()}
    for choices in ballots:
        for rank, rid in enumerate(choices[:3]):
            if rid not in t:
                continue
            if rank == 0:
                t[rid].first += 1
            elif rank == 1:
                t[rid].second += 1
            else:
                t[rid].third += 1
    return t


def display_key(t: Tally):
    return (-t.score, -t.first, -t.second, t.name.casefold(), str(t.restaurant_id))


def display_order(tallies: dict[UUID, Tally]) -> list[Tally]:
    return sorted(tallies.values(), key=display_key)


def draw(seed: str, tied_ids: list[UUID]) -> UUID:
    """Reproducible seeded pick over sorted tied IDs; same inputs always give the same winner."""
    ordered = sorted(str(i) for i in tied_ids)
    return UUID(random.Random(seed).choice(ordered))


def finalize(tallies: dict[UUID, Tally], ballot_count: int, seed: str) -> Result:
    ordered = display_order(tallies)
    if ballot_count == 0 or not ordered:
        return Result(ordered, None, True, None)
    top = [t for t in ordered if t.score == ordered[0].score]
    tie_break = None
    if len(top) > 1:
        best = max(t.first for t in top)
        by_first = [t for t in top if t.first == best]
        if len(by_first) == 1:
            top, tie_break = by_first, "first_place_votes"
        else:
            best2 = max(t.second for t in by_first)
            by_second = [t for t in by_first if t.second == best2]
            if len(by_second) == 1:
                top, tie_break = by_second, "second_place_votes"
            else:
                wid = draw(seed, [t.restaurant_id for t in by_second])
                top, tie_break = [tallies[wid]], "random_draw"
    winner = top[0]
    final_order = [winner] + [t for t in ordered if t.restaurant_id != winner.restaurant_id]
    return Result(final_order, winner.restaurant_id, False, tie_break)
