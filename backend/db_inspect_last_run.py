import asyncio
from app.database import AsyncSessionLocal
from app.models.execution import ExecutionRun, ExecutionResult
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        run = (await db.execute(select(ExecutionRun).order_by(ExecutionRun.id.desc()).limit(1))).scalar_one()
        print(f"Run {run.id}: execution_id={run.execution_id}, status={run.status}, total={run.total_tests}, passed={run.passed}, failed={run.failed}, skipped={run.skipped}")
        
        results = (await db.execute(select(ExecutionResult).where(ExecutionResult.execution_run_id == run.id))).scalars().all()
        for r in results:
            print(f"  Result {r.id}: tc_id={r.test_case_id}, test_name={r.test_name}, status={r.status}, duration={r.duration_ms}ms")
            if r.error_message:
                print(f"    Error: {r.error_message}")

if __name__ == '__main__':
    asyncio.run(inspect())
