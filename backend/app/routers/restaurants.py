"""Restaurants: list/create/get/update/archive/unarchive."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response

from .. import models as m
from ..deps import TeamCtx, check_if_match, idempotency_header, if_match_header, team_access
from ..errors import forbidden, not_found
from ..db.models import Restaurant
from ..store import norm
from ..views import created, idem_replay, restaurant_etag, restaurant_view

router = APIRouter(prefix="/v1/teams/{teamId}/restaurants", tags=["Restaurants"])


def _get(ctx: TeamCtx, rid: UUID) -> Restaurant:
    r = ctx.team.restaurants.get(rid)
    if not r:
        raise not_found(f"Restaurant {rid} does not exist in this team.")
    return r


def _can_edit(ctx: TeamCtx, r: Restaurant) -> None:
    if ctx.me.role != "admin" and r.created_by != ctx.principal.user.id:
        raise forbidden("forbidden", "Only team admins or the member who added this restaurant can change it.")


@router.get("", operation_id="listRestaurants", response_model=m.Items)
async def list_restaurants(status: Literal["active", "archived", "all"] = "active",
                           q: str | None = Query(default=None, max_length=120),
                           ctx: TeamCtx = Depends(team_access("read"))):
    items = list(ctx.team.restaurants.values())
    if status == "active":
        items = [r for r in items if r.archived_at is None]
    elif status == "archived":
        items = [r for r in items if r.archived_at is not None]
    if q and q.strip():
        needle = norm(q)
        items = [r for r in items if needle in norm(f"{r.name} {r.cuisine or ''} {r.address or ''}")
                 or needle in norm(r.name) or needle in norm(r.cuisine) or needle in norm(r.address)]
    items.sort(key=lambda r: (r.name.casefold(), str(r.id)))
    return {"items": [restaurant_view(r).model_dump(mode="json") for r in items]}


@router.post("", operation_id="createRestaurant", status_code=201, response_model=m.Restaurant)
async def create_restaurant(body: m.RestaurantCreate, ctx: TeamCtx = Depends(team_access("write")),
                            key: str | None = Depends(idempotency_header)):
    uid = ctx.principal.user.id
    fp = f"createRestaurant:{ctx.team.id}:" + body.model_dump_json()
    if (hit := idem_replay(ctx.store, uid, key, fp, ctx.now)):
        return hit
    dup = ctx.store.find_duplicate(ctx.team, body.name, body.address)
    if dup:
        raise ctx.store.dup_error(dup, body.name, body.address)
    r = ctx.store.add_restaurant(ctx.team, uid, ctx.now, **body.model_dump())
    return created(ctx.store, uid, key, fp, ctx.now, restaurant_view(r),
                   {"Location": f"/v1/teams/{ctx.team.id}/restaurants/{r.id}", "ETag": restaurant_etag(r)})


@router.get("/{restaurantId}", operation_id="getRestaurant", response_model=m.Restaurant)
async def get_restaurant(response: Response, rid: UUID = Path(alias="restaurantId"),
                         ctx: TeamCtx = Depends(team_access("read"))):
    r = _get(ctx, rid)
    response.headers["ETag"] = restaurant_etag(r)
    return restaurant_view(r)


@router.patch("/{restaurantId}", operation_id="updateRestaurant", response_model=m.Restaurant)
async def update_restaurant(body: m.RestaurantUpdate, response: Response, rid: UUID = Path(alias="restaurantId"),
                            ctx: TeamCtx = Depends(team_access("write")),
                            if_match: str | None = Depends(if_match_header)):
    r = _get(ctx, rid)
    _can_edit(ctx, r)
    check_if_match(if_match, restaurant_etag(r))
    f = body.model_fields_set
    name = body.name if "name" in f else r.name
    address = body.address if "address" in f else r.address
    if r.archived_at is None:
        dup = ctx.store.find_duplicate(ctx.team, name, address, exclude=r.id)  # type: ignore[arg-type]
        if dup:
            raise ctx.store.dup_error(dup, name, address)  # type: ignore[arg-type]
    for field in f:
        setattr(r, field, getattr(body, field))
    r.updated_at = ctx.now
    r.version += 1
    ctx.store.emit(ctx.team, "restaurant.updated", ctx.now, restaurant_id=r.id)
    response.headers["ETag"] = restaurant_etag(r)
    return restaurant_view(r)


@router.post("/{restaurantId}/archive", operation_id="archiveRestaurant", response_model=m.Restaurant)
async def archive_restaurant(rid: UUID = Path(alias="restaurantId"), ctx: TeamCtx = Depends(team_access("write"))):
    r = _get(ctx, rid)
    _can_edit(ctx, r)
    ctx.store.set_archived(ctx.team, r, True, ctx.now)
    return restaurant_view(r)


@router.post("/{restaurantId}/unarchive", operation_id="unarchiveRestaurant", response_model=m.Restaurant)
async def unarchive_restaurant(rid: UUID = Path(alias="restaurantId"), ctx: TeamCtx = Depends(team_access("write"))):
    r = _get(ctx, rid)
    _can_edit(ctx, r)
    if r.archived_at is not None:
        dup = ctx.store.find_duplicate(ctx.team, r.name, r.address, exclude=r.id)
        if dup:
            raise ctx.store.dup_error(dup, r.name, r.address)
        ctx.store.set_archived(ctx.team, r, False, ctx.now)
    return restaurant_view(r)
