from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_users(self, skip: int = 0, limit: int = 100, search: str | None = None) -> list[User]:
        stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                func.lower(User.email).like(pattern)
                | func.lower(User.full_name).like(pattern)
                | func.lower(User.role).like(pattern)
            )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
