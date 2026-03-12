"""Create an initial admin user for development.

Usage:
    python -m app.scripts.seed_admin
"""

import asyncio

from sqlalchemy import select

from app.core.auth import hash_password
from app.db.base import async_session_factory
from app.db.models.user import User, UserRole

ADMIN_EMAIL = "admin@kipgroup.com.au"
ADMIN_PASSWORD = "changeme123"


async def main() -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == ADMIN_EMAIL)
        )
        if result.scalar_one_or_none():
            print(f"Admin user {ADMIN_EMAIL} already exists.")
            return

        user = User(
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            role=UserRole.admin,
        )
        session.add(user)
        await session.commit()
        print(f"Created admin user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
