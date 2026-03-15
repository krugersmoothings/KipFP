from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Import all models so Base.metadata knows about them.
from app.db.models import (  # noqa: E402, F401
    account,
    budget,
    consolidation,
    credential,
    debt,
    entity,
    location,
    period,
    pet_days,
    sync,
    user,
    wc,
)
