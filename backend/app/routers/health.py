from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request

from .. import models as m
from ..auth import get_now

router = APIRouter(prefix="/v1", tags=["Meta"])


@router.get("/health", operation_id="getHealth", response_model=m.Health)
async def get_health(request: Request, now: datetime = Depends(get_now)):
    return m.Health(version=request.app.state.settings.version, server_time=now)
