import asyncio
from app.database import AsyncSessionLocal
from app.models.agent import AgentRun, AgentLog
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as db:
        runs = (await db.execute(select(AgentRun).order_by(AgentRun.id.desc()).limit(5))).scalars().all()
        print(f"--- LATEST AGENT RUNS ---")
        for r in runs:
            out_cnt = r.output_data.get('count') if r.output_data else None
            print(f"Run {r.id}: {r.agent_name} -> status={r.status}, output_count={out_cnt}, progress={r.progress_percent}%, msg={r.progress_message}")
            if r.error_message:
                print(f"  Error: {r.error_message}")
            
            # Print logs for this run
            logs = (await db.execute(select(AgentLog).where(AgentLog.agent_run_id == r.id).order_by(AgentLog.id.asc()))).scalars().all()
            print(f"  Logs ({len(logs)}):")
            for l in logs:
                print(f"    [{l.level}] {l.step}: {l.message}")

if __name__ == '__main__':
    asyncio.run(inspect())
