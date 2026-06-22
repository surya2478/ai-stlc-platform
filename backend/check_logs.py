import asyncio
import json
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.document import UploadedDocument
from app.llm.provider import get_llm
from app.agents.requirement.intake_agent import INTAKE_SYSTEM, _chunk_text, IntakeState

def repair_truncated_json_array(text: str) -> list[dict]:
    start_idx = text.find('[')
    if start_idx == -1:
        raise ValueError("No JSON array found in text")
    
    array_text = text[start_idx:].strip()
    
    try:
        return json.loads(array_text)
    except json.JSONDecodeError:
        pass

    idx = array_text.rfind('}')
    while idx != -1:
        candidate = array_text[:idx+1].strip() + ']'
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            idx = array_text.rfind('}', 0, idx)
            
    idx = array_text.rfind(']')
    while idx != -1:
        candidate = array_text[:idx+1].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            idx = array_text.rfind(']', 0, idx)

    raise ValueError("Could not repair truncated JSON array")

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(UploadedDocument).where(UploadedDocument.project_id == 9).order_by(UploadedDocument.id.desc()))
        doc = result.scalars().first()
        if not doc:
            print("No document found for project 9")
            return
        
        state: IntakeState = {
            "document_text": doc.extracted_text,
            "project_id": 9,
            "chunks": [],
            "requirements": [],
            "errors": [],
        }
        state = _chunk_text(state)
        
        from app.config import get_settings
        settings = get_settings()
        llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
        
        chunk = state['chunks'][0]
        prompt = f"Document excerpt (chunk 1/{len(state['chunks'])}):\n\n{chunk}\n\nExtract all requirements from this excerpt. Return a JSON array."
        
        try:
            response = await llm.generate(
                system=INTAKE_SYSTEM,
                user=prompt,
                temperature=0.1,
                max_tokens=4000,
            )
            print("Successfully called LLM. Repairing and parsing...")
            reqs = repair_truncated_json_array(response)
            print(f"Successfully extracted {len(reqs)} requirements!")
            for idx, r in enumerate(reqs[:3]):
                print(f"Req {idx+1}: {r.get('title')}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
