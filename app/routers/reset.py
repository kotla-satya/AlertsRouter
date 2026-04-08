from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import reset_service

router = APIRouter(prefix="/reset", tags=["reset"])


@router.post("", status_code=200)
async def reset(db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Delete all data from the database — alerts, routing configs, and suppression records.

    Intended for testing and development. Returns `{"status": "ok"}` on success.
    """
    return await reset_service.reset_all(db)
