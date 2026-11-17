"""Demo seed data. Used ONLY at startup (never by API endpoints): new teams created via the API start empty.

The restaurant list mirrors frontend/src/lib/seed-restaurants.ts (Berlin Friedrichstrasse).
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from . import scheduling
from .auth import Passwords
from .store import BallotRec, Membership, PollRec, Store, TeamRec, UserRec

DEMO_PASSWORD = "password123"

DEMO_USERS = [
    ("anna@example.com", "Anna"),
    ("ben@example.com", "Ben"),
    ("carla@example.com", "Carla"),
    ("dmitri@example.com", "Dmitri"),
    ("eva@example.com", "Eva"),
]

FRIEDRICHSTRASSE_SEED = [
    ("Ständige Vertretung", "German / Rhenish", "Schiffbauerdamm 8, 10117 Berlin"),
    ("Maximilians", "German / Bavarian", "Friedrichstraße 185-190, 10117 Berlin"),
    ("Grill Royal", "Steakhouse", "Friedrichstraße 105b, 10117 Berlin"),
    ("Borchardt", "German / French", "Französische Straße 47, 10117 Berlin"),
    ("Augustiner am Gendarmenmarkt", "German / Bavarian", "Charlottenstraße 55, 10117 Berlin"),
    ("Cadadia", "Quiche & salads", "Charlottenstraße 63, 10117 Berlin"),
    ("Little Green Rabbit", "Salads & soups", "Jägerstraße 27, 10117 Berlin"),
    ("Otito", "Asian", "Leipziger Straße 30, 10117 Berlin"),
]


def map_url(name: str, address: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name}, {address}")


def _add_ballot(p: PollRec, user: UserRec, choices: list, at: datetime) -> None:
    p.ballots[user.id] = BallotRec(user.id, list(choices), at)


def _seed_restaurants(store: Store, team: TeamRec, creators: list[UserRec], now: datetime, only: list[int] | None = None):
    out = []
    for i, (name, cuisine, address) in enumerate(FRIEDRICHSTRASSE_SEED):
        if only is not None and i not in only:
            continue
        creator = creators[i % len(creators)] if i % 4 else None  # a few have no creator (dev seed data)
        r = store.add_restaurant(team, creator.id if creator else None, team.created_at, name=name, cuisine=cuisine,
                                 address=address, map_url=map_url(name, address), emit=False)
        out.append(r)
    return out


def _history(store: Store, team: TeamRec, users: list[UserRec], rests: list, now: datetime, days: int, rng: random.Random):
    d = scheduling.local_date(now, team.timezone)
    past = []
    while len(past) < days:
        d -= timedelta(days=1)
        if scheduling.is_poll_day(d):
            past.append(d)
    for idx, day in enumerate(reversed(past)):
        p = store.ensure_poll(team, day, now)
        ids = [r.id for r in rests]
        a, b, c = ids[0], ids[1], ids[2]
        if idx == 2:  # complete tie -> seeded random draw
            scenario = [(users[0], [a, b]), (users[1], [b, a])]
        elif idx == 4:  # same points, decided by first-place votes
            scenario = [(users[0], [a, b]), (users[1], [c, b, a])]
        elif idx == 6:  # nobody voted
            scenario = []
        else:
            scenario = []
            for u in users:
                if rng.random() < 0.85:
                    scenario.append((u, rng.sample(ids, k=rng.choice([1, 2, 3, 3]))))
        for j, (u, choices) in enumerate(scenario):
            _add_ballot(p, u, choices, p.opens_at + timedelta(minutes=7 + 23 * j))
        p.opened_emitted = True
        store.finalize(team, p, p.closes_at + timedelta(seconds=2))


def _stable_id(kind: str, key: str) -> uuid.UUID:
    """Demo users/teams keep the same ids across restarts, so bookmarked URLs survive a reseed."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"wswe-demo/{kind}/{key}")


def seed(store: Store, passwords: Passwords, now: datetime) -> dict:
    users: dict[str, UserRec] = {}
    for n, (email, name) in enumerate(DEMO_USERS):
        users[email] = store.add_user(email, passwords.hasher.hash(DEMO_PASSWORD), now - timedelta(days=40 - n), display_name=name, user_id=_stable_id("user", email))
    anna, ben, carla, dmitri, eva = (users[e] for e, _ in DEMO_USERS)
    created = now - timedelta(days=30)

    # Team 1: Design crew (Anna admin; Ben admin too; Carla, Dmitri members)
    t1 = store.create_team(anna, "Design crew", "Europe/Berlin", "Berlin Mitte", "08:00", "11:30", created, team_id=_stable_id("team", "design-crew"))
    t1.invite_token = "demo-design-crew-invite"
    for u, role, days in ((ben, "admin", 29), (carla, "member", 28), (dmitri, "member", 20)):
        t1.members[u.id] = Membership(u.id, role, now - timedelta(days=days))
    rests1 = _seed_restaurants(store, t1, [anna, ben, carla], now)
    rests1[3].archived_at = now - timedelta(days=3)  # one archived restaurant to show the archived view
    rests1[3].updated_at = rests1[3].archived_at
    active1 = [r for r in rests1 if r.archived_at is None]

    # Team 2: Platform team (Eva admin, Anna member), smaller list
    t2 = store.create_team(eva, "Platform team", "Europe/Berlin", "Berlin Friedrichstraße", "08:30", "11:00", created, team_id=_stable_id("team", "platform-team"))
    t2.invite_token = "demo-platform-team-invite"
    t2.members[anna.id] = Membership(anna.id, "member", now - timedelta(days=10))
    rests2 = _seed_restaurants(store, t2, [eva, anna], now, only=[0, 1, 2, 5, 6, 7])

    rng = random.Random(2026)
    _history(store, t1, [anna, ben, carla, dmitri], active1[:3] + active1[3:], now, 8, rng)
    _history(store, t2, [eva, anna], rests2, now, 4, rng)

    # Today's poll for team 1: live ballots if it is open right now (they would be finalized if already closed).
    d = scheduling.local_date(now, t1.timezone)
    if scheduling.is_poll_day(d):
        p = store.ensure_poll(t1, d, now)
        if now >= p.opens_at:
            ids = [r.id for r in active1]
            picks = [(anna, [ids[0], ids[2], ids[1]]), (ben, [ids[2], ids[0]]), (carla, [ids[0], ids[4]])]
            for j, (u, ch) in enumerate(picks):
                _add_ballot(p, u, ch, min(now, p.opens_at + timedelta(minutes=12 + 31 * j)))
    store.tick(now)
    return {"users": users, "teams": [t1, t2]}
