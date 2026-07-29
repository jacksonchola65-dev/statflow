import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.db.base import Base
from app.models.dashboard import Dashboard
from app.models.dashboard_card import DashboardCard
from app.models.user import UserRole
from app.services.auth_service import AuthService
from app.services.dashboard_service import DashboardService

async def main():
    engine = create_async_engine(settings.TEST_DATABASE_URL, echo=False, future=True, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        async with session.begin():
            auth = AuthService(session)
            user = await auth.create_user(
                email=f'debug-{uuid.uuid4().hex[:8]}@test.example',
                password='x',
                full_name='Debug User',
                role=UserRole.ADMIN,
                is_active=True,
            )
            await session.flush()
            svc = DashboardService(session)
            dashboard = await svc.create_dashboard(user.id, 'Revenue Overview', 'Saved dashboard', [
                {'id': 'card-1', 'title': 'Revenue', 'order': 0, 'visualization_type': 'bar', 'size': 'medium', 'visualization_snapshot': {'chartType': 'bar', 'rows': []}}
            ])
            print('dashboard created', dashboard.id, dashboard.owner_id)
            loaded = await svc.get_dashboard(dashboard.id)
            print('loaded owner_id', loaded.owner_id)
            print('loaded cards', [c.id for c in loaded.cards])
    await engine.dispose()

asyncio.run(main())
