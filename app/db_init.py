"""
Ensure database tables exist.

Temporary fallback until Alembic migrations are added (issue #9). The container
entrypoint runs this when no ``alembic.ini`` is present; once Alembic is
configured, the entrypoint runs ``alembic upgrade head`` instead.
"""
import asyncio

from app.core.database import engine
from app.models.models import Base


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("[db_init] tables ensured")


if __name__ == "__main__":
    asyncio.run(init_models())
