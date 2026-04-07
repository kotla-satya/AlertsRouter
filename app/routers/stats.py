from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.stats import StatsResponse
from ..services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", status_code=200, response_model=StatsResponse)
async def get_stats(db: Annotated[AsyncSession, Depends(get_db)]):
    return await stats_service.get_stats(db)
