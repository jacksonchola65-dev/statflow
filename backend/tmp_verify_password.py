import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.user import User
from app.core.security import verify_password

async def main():
    engine = create_async_engine(settings.DATABASE_URL, future=True, pool_pre_ping=True)
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with async_session() as session:
        result = await session.execute(select(User.email, User.hashed_password))
        for email, hashed in result.fetchall():
            ok = verify_password('ChangeMe123!', hashed)
            print(email, ok)
    await engine.dispose()

asyncio.run(main())
