"""In-process pub/sub for team change events, with a 10 minute replay buffer (SSE ids monotonic per team)."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Callable
from uuid import UUID

from .models import fmt_ts

RETENTION = timedelta(minutes=10)


class EventBus:
    def __init__(self) -> None:
        self._counters: dict[UUID, int] = defaultdict(int)
        self._buffers: dict[UUID, deque] = defaultdict(deque)  # (id, datetime, event dict)
        self._subs: dict[UUID, set[asyncio.Queue]] = defaultdict(set)

    def publish(self, team_id: UUID, etype: str, now: datetime, poll_id: UUID | None = None,
                data: dict[str, Any] | None = None) -> dict:
        self._counters[team_id] += 1
        eid = self._counters[team_id]
        event = {"id": str(eid), "type": etype, "team_id": str(team_id), "occurred_at": fmt_ts(now),
                 "poll_id": str(poll_id) if poll_id else None, "data": data or {}}
        buf = self._buffers[team_id]
        buf.append((eid, now, event))
        while buf and now - buf[0][1] > RETENTION:
            buf.popleft()
        for q in list(self._subs[team_id]):
            q.put_nowait(event)
        return event

    def last_id(self, team_id: UUID) -> int:
        return self._counters[team_id]

    def replay_after(self, team_id: UUID, last_id: int) -> list[dict] | None:
        """Events after last_id, or None if they can't be replayed (-> resync)."""
        buf = self._buffers[team_id]
        current = self._counters[team_id]
        if last_id > current:
            return None
        if last_id == current:
            return []
        if not buf or buf[0][0] > last_id + 1:
            return None
        return [e for (i, _, e) in buf if i > last_id]

    def subscribe(self, team_id: UUID) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[team_id].add(q)
        return q

    def unsubscribe(self, team_id: UUID, q: asyncio.Queue) -> None:
        self._subs[team_id].discard(q)


def frame(event: dict) -> str:
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


async def event_stream(bus: EventBus, team_id: UUID, user_id: UUID, last_event_id: str | None,
                       is_member: Callable[[], bool], now: Callable[[], datetime],
                       keepalive_seconds: float = 25.0) -> AsyncIterator[str]:
    """Yield SSE frames. Ends when the user is no longer a member of the team."""
    q = bus.subscribe(team_id)  # subscribe first so nothing is missed between replay and live
    try:
        if last_event_id is not None:
            try:
                replay = bus.replay_after(team_id, int(last_event_id))
            except ValueError:
                replay = None
            if replay is None:
                yield frame({"id": str(bus.last_id(team_id)), "type": "resync", "team_id": str(team_id),
                             "occurred_at": fmt_ts(now()), "poll_id": None, "data": {}})
            else:
                seen = {e["id"] for e in replay}
                for e in replay:
                    yield frame(e)
                # drop queued duplicates already replayed
                pending = []
                while not q.empty():
                    e = q.get_nowait()
                    if e["id"] not in seen:
                        pending.append(e)
                for e in pending:
                    yield frame(e)
        else:
            while not q.empty():  # nothing to replay for a fresh connection
                q.get_nowait()
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=keepalive_seconds)
            except asyncio.TimeoutError:
                if not is_member():
                    return
                yield ": keep-alive\n\n"
                continue
            if event["type"] in ("member.left", "member.removed") and event["data"].get("user_id") == str(user_id):
                if not is_member():
                    yield frame(event)
                    return
            if not is_member():
                return
            yield frame(event)
    finally:
        bus.unsubscribe(team_id, q)
