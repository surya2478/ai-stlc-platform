import asyncio
from app.database import AsyncSessionLocal
from app.models.requirement import Requirement
from app.models.test_scenario import TestScenario
from app.models.test_case import TestCase
from app.models.test_plan import TestPlan
from app.models.execution import ExecutionRun, ExecutionResult
from app.models.automation_script import AutomationScript
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        print("--- PROJECT 13 TEST PLANS ---")
        plans = (await db.execute(select(TestPlan).where(TestPlan.project_id == 13))).scalars().all()
        print(f"Total plans: {len(plans)}")
        for p in plans:
            title_safe = str(p.title).encode('ascii', 'replace').decode('ascii')
            print(f"  Plan {p.id}: {p.test_plan_id} -> title={title_safe}, status={p.status}")
            
        print("\n--- PROJECT 13 EXECUTION RUNS ---")
        runs = (await db.execute(select(ExecutionRun).where(ExecutionRun.project_id == 13))).scalars().all()
        print(f"Total execution runs: {len(runs)}")
        for r in runs:
            print(f"  Run {r.id}: {r.execution_id} -> status={r.status}, passed={r.passed}, failed={r.failed}, source_type={r.source_type}")
            
        print("\n--- PROJECT 13 AUTOMATION SCRIPTS ---")
        scripts = (await db.execute(select(AutomationScript).where(AutomationScript.project_id == 13))).scalars().all()
        print(f"Total automation scripts: {len(scripts)}")
        for s in scripts:
            print(f"  Script {s.id}: file_path={s.file_path}, framework={s.framework}")

if __name__ == '__main__':
    asyncio.run(inspect())
