import asyncio
from app.database import AsyncSessionLocal
from app.models.automation_script import AutomationScript
from app.services import automation_service

async def main():
    async with AsyncSessionLocal() as db:
        script = await automation_service.get_script(db, 15)
        print("Before regenerate: status=", script.status, "code head:", (script.code or "")[:80].replace("\n", " "))
        script = await automation_service.regenerate_script(db, script, user_id=2)
        print("After regenerate: status=", script.status)
        print("--- regenerated code ---")
        print(script.code)
        await db.commit()

asyncio.run(main())
