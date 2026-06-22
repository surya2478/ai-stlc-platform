import asyncio
import sys
from app.database import AsyncSessionLocal
from app.models.test_case import TestCase
from app.models.execution import ExecutionRun, ExecutionResult
from app.models.project import Project
from app.agents.execution.execution_agent import TestExecutionAgent
from app.services.display_id_service import display_id, temporary_id
from app.services import traceability_service
from sqlalchemy import select

async def run_tests():
    async with AsyncSessionLocal() as db:
        # Get first 5 test cases for project 13
        stmt = select(TestCase).where(TestCase.project_id == 13).order_by(TestCase.id.asc()).limit(5)
        test_cases_objs = (await db.execute(stmt)).scalars().all()
        
        if len(test_cases_objs) < 5:
            print(f"Error: Found only {len(test_cases_objs)} test cases for project 13, expected at least 5.")
            return

        print(f"Found {len(test_cases_objs)} test cases to run.")
        test_cases = []
        for tc in test_cases_objs:
            print(f"  TC ID {tc.id}: {tc.test_case_id} -> {tc.title}")
            test_cases.append({
                "id": tc.id,
                "test_case_id": tc.test_case_id,
                "title": tc.title,
                "steps": tc.steps or [],
                "test_type": tc.test_type or "functional",
                "priority": tc.priority or "High",
            })

        # Run TestExecutionAgent
        agent = TestExecutionAgent()
        agent_result = await agent.run(
            test_cases=test_cases,
            environment="staging",
            suite_name="Regression Test Suite",
        )

        if not agent_result.success:
            print(f"Agent failed: {agent_result.error}")
            return

        summary = agent_result.data.get("summary", {})
        results = agent_result.data.get("results", [])
        print(f"Agent finished: {summary}")

        # Create ExecutionRun
        run = ExecutionRun(
            project_id=13,
            created_by=1,  # User 1 is dev@stlc.local
            execution_id=temporary_id("ER"),
            suite_name="Regression Test Suite",
            environment="staging",
            status="completed",
            total_tests=summary.get("total", len(results)),
            passed=summary.get("passed", 0),
            failed=summary.get("failed", 0),
            skipped=summary.get("skipped", 0),
            execution_logs=agent_result.logs,
        )
        db.add(run)
        await db.flush()
        
        run.execution_id = display_id("ER", run.id)
        await db.flush()

        # Link lineage
        await traceability_service.create_lineage_many(
            db,
            project_id=13,
            parents=[("test_case", tc["id"]) for tc in test_cases],
            child_type="execution_run",
            child_id=run.id,
        )

        # Map test_case_id string -> DB id
        tc_map = {tc["test_case_id"]: tc["id"] for tc in test_cases}

        for r_data in results:
            tc_id_str = r_data.get("test_case_id")
            db_tc_id = tc_map.get(tc_id_str)

            agent_status = r_data.get("status", "passed")
            status_map = {
                "passed": "pass",
                "failed": "fail",
                "skipped": "skip",
                "error": "error",
                "blocked": "blocked",
                "not_run": "not_run",
                "running": "running",
                "pending": "pending"
            }
            db_status = status_map.get(agent_status, agent_status)

            exec_result = ExecutionResult(
                execution_run_id=run.id,
                test_case_id=db_tc_id,
                project_id=13,
                test_name=r_data.get("test_name", "Unknown"),
                status=db_status,
                duration_ms=r_data.get("duration_ms"),
                error_message=r_data.get("error_message"),
                stack_trace=r_data.get("stack_trace"),
                logs=r_data.get("logs", []),
            )
            db.add(exec_result)
            await db.flush()

            parents = [("execution_run", run.id)]
            if db_tc_id is not None:
                parents.append(("test_case", db_tc_id))
                
            await traceability_service.create_lineage_many(
                db,
                project_id=13,
                parents=parents,
                child_type="execution_result",
                child_id=exec_result.id,
            )

        await db.commit()
        print(f"Successfully committed run: {run.execution_id}")

if __name__ == '__main__':
    asyncio.run(run_tests())
