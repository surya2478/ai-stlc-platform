import asyncio
from app.database import AsyncSessionLocal
from app.models.requirement import Requirement
from app.services.project_application_service import resolve_application_context

async def main():
    async with AsyncSessionLocal() as db:
        # Case 1: requirement WITH real scraped source_url (rankix.ai, project 4)
        req = await db.get(Requirement, 31)
        ctx = await resolve_application_context(db, project_id=4, requirement=req)
        print("Case 1 (real scraped URL):", ctx["url"], "| source:", ctx["source"], "| has ui_analysis:", bool(ctx["ui_analysis"]))
        assert ctx["url"] == "https://rankix.ai/", f"expected rankix.ai, got {ctx['url']}"
        assert ctx["source"] == "requirement"
        assert ctx["ui_analysis"] is not None

        # Case 2: no requirement, no project-default application configured (project 999 = nonexistent/no apps)
        ctx2 = await resolve_application_context(db, project_id=999999, requirement=None)
        print("Case 2 (nothing configured):", ctx2)
        assert ctx2["url"] is None
        assert ctx2["source"] is None

        # Case 3: project 3 has a default ProjectApplication configured (from earlier session verification)
        ctx3 = await resolve_application_context(db, project_id=3, requirement=None)
        print("Case 3 (project default application, project 3):", ctx3["url"], "| source:", ctx3["source"])

        print("ALL_ASSERTIONS_PASSED")

asyncio.run(main())
