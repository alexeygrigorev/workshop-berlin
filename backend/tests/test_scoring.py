"""Pure unit tests for scoring and tie-breaks (specs.md section 7 / 16)."""
from uuid import UUID

from app import scoring

A, B, C, D = (UUID(int=i) for i in (1, 2, 3, 4))
CANDS = {A: "Alpha", B: "Bravo", C: "Charlie", D: "Delta"}


def run(ballots, seed="seed-1"):
    t = scoring.tally(CANDS, ballots)
    return t, scoring.finalize(t, len(ballots), seed)


def test_3_2_1_points():
    t, _ = run([[A, B, C]])
    assert (t[A].score, t[B].score, t[C].score, t[D].score) == (3, 2, 1, 0)


def test_replacement_semantics_only_latest_ballot_counts():
    t, _ = run([[C, A]])  # A voted [A,B,C] then re-voted [C,A]: only the latest ballot is in the list
    assert (t[A].score, t[B].score, t[C].score) == (2, 0, 3)


def test_clear_winner():
    t, r = run([[A, B], [A, C], [B, A]])
    assert r.winner_id == A and r.tie_break is None and not r.no_winner
    assert r.ordered[0].restaurant_id == A


def test_tie_resolved_by_first_place_votes():
    # A: 3+1 = 4 (one 1st), B: 2+2 = 4 (none)
    _, r = run([[A, B], [C, B, A]])
    assert r.winner_id == A and r.tie_break == "first_place_votes"


def test_first_place_tie_break_with_three_voters():
    # A: 3+2+1 = 6 (one 1st), B: 3+3 = 6 (two 1st) -> B wins on first-place votes
    t, r = run([[A, C], [B, A], [B, C, A]])
    assert (t[A].score, t[B].score) == (6, 6)
    assert r.winner_id == B and r.tie_break == "first_place_votes"


def test_second_place_tiebreak_clean_case():
    # Craft: A and B tie on score and 1st-place counts; B has more 2nd-place votes.
    # A: 1st, 1st, 3rd? -> pick A: f=1,s=0,t=2 => 3+2 = 5 ; B: f=1,s=1,t=0 => 3+2 = 5
    t = {A: scoring.Tally(A, "Alpha", 1, 0, 2), B: scoring.Tally(B, "Bravo", 1, 1, 0),
         C: scoring.Tally(C, "Charlie", 0, 0, 0), D: scoring.Tally(D, "Delta", 0, 0, 0)}
    assert t[A].score == t[B].score == 5
    r = scoring.finalize(t, 3, "s")
    assert r.winner_id == B and r.tie_break == "second_place_votes"
    assert [x.restaurant_id for x in r.ordered][:2] == [B, A]


def test_full_tie_uses_seeded_deterministic_draw():
    ballots = [[A, B], [B, A]]
    results = {run(ballots, "same-seed")[1].winner_id for _ in range(5)}
    assert len(results) == 1  # same seed -> same winner on every retry
    r = run(ballots, "same-seed")[1]
    assert r.tie_break == "random_draw" and r.winner_id in (A, B) and r.ordered[0].restaurant_id == r.winner_id
    # different seeds can pick either; both outcomes occur across seeds
    winners = {run(ballots, f"seed-{i}")[1].winner_id for i in range(40)}
    assert winners == {A, B}
    # the draw depends only on the sorted tied ids, not on input order
    assert scoring.draw("x", [B, A]) == scoring.draw("x", [A, B])


def test_all_candidates_tied():
    # 4 candidates, each 1st once among 4 ballots with identical shape -> all tie on every criterion
    t, r = run([[A], [B], [C], [D]])
    assert r.tie_break == "random_draw" and r.winner_id in (A, B, C, D)


def test_no_ballots_no_winner():
    t, r = run([])
    assert r.no_winner and r.winner_id is None and r.tie_break is None
    assert [x.name for x in r.ordered] == ["Alpha", "Bravo", "Charlie", "Delta"]  # zero rows kept, alphabetical


def test_single_voted_restaurant_wins_and_zero_vote_candidates_remain():
    t, r = run([[C]])
    assert r.winner_id == C and len(r.ordered) == 4 and t[D].score == 0


def test_display_order_score_first_second_name():
    t, _ = run([[B, A], [A, B], [C]])
    # A 5 (f1 s1), B 5 (f1 s1), C 3 -> tie on all, name decides display order
    assert [x.name for x in scoring.display_order(t)] == ["Alpha", "Bravo", "Charlie", "Delta"]
