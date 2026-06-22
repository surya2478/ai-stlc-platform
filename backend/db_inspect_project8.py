import asyncio
from app.database import AsyncSessionLocal
from app.models.requirement import Requirement
from app.models.test_scenario import TestScenario
from app.models.test_case import TestCase
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        print("--- PROJECT 8 REQUIREMENTS ---")
        reqs = (await db.execute(select(Requirement).where(Requirement.project_id == 8))).scalars().all()
        print(f"Total requirements: {len(reqs)}")
        for r in reqs[:10]:
            print(f"  Req {r.id}: {r.requirement_id} -> title={r.title}, status={r.status}, quality_score={r.quality_score}, quality_verdict={r.quality_verdict}")
        
        print("\n--- PROJECT 8 TEST SCENARIOS ---")
        scenarios = (await db.execute(select(TestScenario).where(TestScenario.project_id == 8))).scalars().all()
        print(f"Total scenarios: {len(scenarios)}")
        for s in scenarios[:10]:
            print(f"  Scenario {s.id}: {s.scenario_id} -> title={s.title}, status={s.status}, req_id={s.requirement_id}")
            
        print("\n--- PROJECT 8 TEST CASES ---")
        cases = (await db.execute(select(TestCase).where(TestCase.project_id == 8))).scalars().all()
        print(f"Total test cases: {len(cases)}")
        for c in cases[:10]:
            print(f"  TestCase {c.id}: {c.test_case_id} -> title={c.title}, status={c.status}, sc_id={c.scenario_id}")

if __name__ == '__main__':
    asyncio.run(inspect())
