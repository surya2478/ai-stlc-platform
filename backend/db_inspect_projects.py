import asyncio
from app.database import AsyncSessionLocal
from app.models.project import Project
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        projects = (await db.execute(select(Project))).scalars().all()
        print(f"Total projects in DB: {len(projects)}")
        for p in projects:
            print(f"  Project {p.id}: {p.name} -> desc={p.description}")

if __name__ == '__main__':
    asyncio.run(inspect())
