import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        print(f"Total users in DB: {len(users)}")
        for u in users:
            print(f"  User {u.id}: email={u.email}, role={u.role}")

if __name__ == '__main__':
    asyncio.run(inspect())
