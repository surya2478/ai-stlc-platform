import asyncio
from app.database import AsyncSessionLocal
from app.models.execution import ExecutionRun
from app.services.display_id_service import temporary_id

async def main():
    async with AsyncSessionLocal() as db:
        run = ExecutionRun(
            project_id=3,
            created_by=2,
            execution_id=temporary_id("ER"),
            suite_name="Automation: AS-0015 (verify-fix, will rollback)",
            environment="QA-Staging",
            status="queued",
            execution_type="automation",
            source_type="automation_local",
            total_tests=1,
            passed=0,
            failed=0,
            skipped=0,
            execution_logs=[],
            metadata_={"source_type": "automation_local", "verify_fix": True},
        )
        db.add(run)
        await db.flush()
        print("INSERT OK, run.id =", run.id, "execution_type =", run.execution_type, "source_type =", run.source_type)
        await db.rollback()
        print("Rolled back, no data persisted.")

asyncio.run(main())
