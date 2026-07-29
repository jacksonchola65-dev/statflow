import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.user import User

async def main():
    engine = create_async_engine(settings.DATABASE_URL, future=True, pool_pre_ping=True)
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with async_session() as session:
        result = await session.execute(select(User.email, User.role, User.is_active, User.created_at).order_by(User.created_at))
        for row in result.fetchall():
            print(row)
    await engine.dispose()

asyncio.run(main())
