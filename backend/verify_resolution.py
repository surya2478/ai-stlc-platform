import asyncio
from app.database import AsyncSessionLocal
from app.models.automation_script import AutomationScript
from app.worker.tasks.automation_tasks import _resolve_playwright_base_url

async def main():
    async with AsyncSessionLocal() as db:
        script = await db.get(AutomationScript, 15)
        for env in ("QA-Staging", "SIT", "Production"):
            url = await _resolve_playwright_base_url(db, script, env)
            print(f"environment={env!r} -> resolved base_url={url!r}")

asyncio.run(main())
