"""Stats: restaurant win statistics from finalized polls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import models as m
from ..deps import TeamCtx, team_access

router = APIRouter(prefix="/v1/teams/{teamId}/stats", tags=["Stats"])


@router.get("/restaurants", operation_id="getRestaurantStats", response_model=m.RestaurantStatsList)
async def get_restaurant_stats(recent_window: int = Query(default=30, ge=1, le=365),
                               ctx: TeamCtx = Depends(team_access("read"))):
    team = ctx.team
    ctx.store.reconcile_team(team, ctx.now)
    closed = sorted((p for p in team.polls.values() if p.finalized_at is not None),
                    key=lambda p: p.poll_date, reverse=True)
    recent = {p.id for p in closed[:recent_window]}
    stats: dict = {}
    for p in closed:
        for s in p.final_scores or []:
            row = stats.setdefault(s["restaurant_id"], {"name": s["name"], "wins_total": 0, "wins_recent": 0,
                                                        "last_won_on": None, "total_points": 0})
            row["total_points"] += s["score"]
        if p.winner_id is not None:
            row = stats[p.winner_id]
            row["wins_total"] += 1
            row["wins_recent"] += p.id in recent
            if row["last_won_on"] is None or p.poll_date.isoformat() > row["last_won_on"]:
                row["last_won_on"] = p.poll_date.isoformat()
    items = []
    for rid, r in team.restaurants.items():
        row = stats.get(rid)
        if row is None and r.archived_at is not None:
            continue  # archived restaurants appear only if they have history
        row = row or {"wins_total": 0, "wins_recent": 0, "last_won_on": None, "total_points": 0}
        items.append(m.RestaurantStats(restaurant_id=rid, name=r.name, archived=r.archived_at is not None,
                                       wins_total=row["wins_total"], wins_recent=row["wins_recent"],
                                       last_won_on=row["last_won_on"], total_points=row["total_points"]))
    items.sort(key=lambda s: (-s.wins_total, s.name.casefold()))
    return m.RestaurantStatsList(recent_window=recent_window, closed_poll_count=len(closed), items=items)
