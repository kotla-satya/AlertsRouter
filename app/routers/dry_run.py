from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.alert import AlertCreate, AlertRoutingResponse
from ..services import alerts_service

router = APIRouter(prefix="/test", tags=["test"])


@router.post("", status_code=200, response_model=AlertRoutingResponse)
async def dry_run_alert(
    body: AlertCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await alerts_service.dry_run_route_alert(db, body)
