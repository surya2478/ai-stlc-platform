import asyncio
from app.database import AsyncSessionLocal
from app.models.test_case import TestCase
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        cases = (await db.execute(select(TestCase))).scalars().all()
        print(f"Total test cases in DB: {len(cases)}")
        regression_cases = [c for c in cases if c.test_phase == 'Regression' or (c.test_type and 'regression' in c.test_type.lower())]
        print(f"Total regression cases in DB: {len(regression_cases)}")
        for c in regression_cases:
            print(f"  Project {c.project_id} | TestCase {c.id}: {c.test_case_id} -> title={c.title}, status={c.status}, test_phase={c.test_phase}, test_type={c.test_type}, suite_id={c.suite_id}")

if __name__ == '__main__':
    asyncio.run(inspect())
