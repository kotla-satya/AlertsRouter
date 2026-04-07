from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, RoutingConfig, RouteSuppression


async def reset_all(db: AsyncSession) -> dict:
    async with db.begin():
        await db.execute(
            text("LOCK TABLE route_suppressions, alerts, routing_configs IN EXCLUSIVE MODE")
        )
        await db.execute(delete(RouteSuppression))
        await db.execute(delete(Alert))
        await db.execute(delete(RoutingConfig))
    return {"status": "ok"}
