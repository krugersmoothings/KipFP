from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_finance
from app.db.models.entity import Entity
from app.db.models.user import User
from app.schemas.entity import EntityRead

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("", response_model=list[EntityRead])
async def list_entities(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return all active entities."""
    result = await db.execute(
        select(Entity)
        .where(Entity.is_active.is_(True))
        .order_by(Entity.code)
    )
    return result.scalars().all()
