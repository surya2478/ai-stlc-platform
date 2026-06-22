import asyncio
from app.database import AsyncSessionLocal
from app.models.requirement import Requirement
from app.models.test_scenario import TestScenario
from app.models.test_case import TestCase
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        print("--- PROJECT 13 REQUIREMENTS ---")
        reqs = (await db.execute(select(Requirement).where(Requirement.project_id == 13))).scalars().all()
        print(f"Total requirements: {len(reqs)}")
        for r in reqs:
            title_safe = str(r.title).encode('ascii', 'replace').decode('ascii')
            print(f"  Req {r.id}: {r.requirement_id} -> title={title_safe}, status={r.status}, test_phase={r.test_phase}")
        
        print("\n--- PROJECT 13 TEST SCENARIOS ---")
        scenarios = (await db.execute(select(TestScenario).where(TestScenario.project_id == 13))).scalars().all()
        print(f"Total scenarios: {len(scenarios)}")
        for s in scenarios:
            title_safe = str(s.title).encode('ascii', 'replace').decode('ascii')
            print(f"  Scenario {s.id}: {s.scenario_id} -> title={title_safe}, status={s.status}, req_id={s.requirement_id}")
            
        print("\n--- PROJECT 13 TEST CASES ---")
        cases = (await db.execute(select(TestCase).where(TestCase.project_id == 13))).scalars().all()
        print(f"Total test cases: {len(cases)}")
        for c in cases:
            title_safe = str(c.title).encode('ascii', 'replace').decode('ascii')
            print(f"  TestCase {c.id}: {c.test_case_id} -> title={title_safe}, status={c.status}, sc_id={c.scenario_id}, priority={c.priority}, test_phase={c.test_phase}, execution_mode={c.execution_mode}, suite_id={c.suite_id}")

if __name__ == '__main__':
    asyncio.run(inspect())
