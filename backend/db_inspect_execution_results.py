import asyncio
from app.database import AsyncSessionLocal
from app.models.execution import ExecutionResult
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        results = (await db.execute(select(ExecutionResult))).scalars().all()
        print(f"Total execution results in DB: {len(results)}")
        statuses = set(r.status for r in results)
        print(f"Unique statuses: {statuses}")
        for r in results[:10]:
            print(f"  Result {r.id}: status={r.status}, test_name={r.test_name}")

if __name__ == '__main__':
    asyncio.run(inspect())
