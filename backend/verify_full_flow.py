import asyncio
from app.database import AsyncSessionLocal
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.models.automation_script import AutomationScript
from app.services import automation_service
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        # 1. Create a ProjectApplication for project 3 with a real QA-Staging URL
        app = ProjectApplication(
            project_id=3,
            key="web-app",
            name="Web App",
            is_default=True,
            environment_urls={"QA-Staging": "https://staging.rankix-testing.internal"},
            created_by=2,
        )
        db.add(app)
        await db.flush()
        print("Created ProjectApplication id=", app.id, "environment_urls=", app.environment_urls)

        # 2. Tag TC-0055 (test_case.id == 55) to this application
        tc = await db.get(TestCase, 55)
        tc.application_id = app.id
        await db.flush()
        print("Tagged TestCase id=", tc.id, "application_id=", tc.application_id)

        await db.commit()

asyncio.run(main())
