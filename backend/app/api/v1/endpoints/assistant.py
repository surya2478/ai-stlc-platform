from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api.deps import CurrentUser, DBSession, require_project_access
from app.config import get_settings
from app.agents.assistant.assistant_agent import PlatformAssistantAgent
from app.models.assistant import (
    AssistantConversation,
    AssistantMessage,
    AssistantFeedback,
)
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantConversationOut,
    AssistantMessageOut,
    AssistantFeedbackRequest,
)

router = APIRouter()
settings = get_settings()


@router.post("/chat", response_model=AssistantChatResponse)
async def chat_with_assistant(
    payload: AssistantChatRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    if not settings.assistant_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform Assistant is currently disabled."
        )

    # 1. Enforce RBAC & role check
    allowed_roles = [r.strip().lower() for r in settings.assistant_allowed_roles.split(",") if r.strip()]
    if current_user.role.lower() not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role is not authorized to use the Assistant."
        )

    # 2. Server-side validate user has access to project
    await require_project_access(payload.project_id, current_user, db)

    # 3. Resolve user's organization
    organization_id = getattr(current_user, "organization_id", None)

    # 4. Invoke the LangGraph agent
    agent = PlatformAssistantAgent()
    input_data = {
        "db": db,
        "user_id": current_user.id,
        "user_role": current_user.role,
        "project_id": payload.project_id,
        "organization_id": organization_id,
        "current_route": payload.current_route,
        "message": payload.message,
        "conversation_id": payload.conversation_id
    }
    
    result = await agent.run(input_data)
    
    # Check if failed
    if result.status == "failed" or not result.output:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error or "Assistant execution failed."
        )

    out = result.output
    return AssistantChatResponse(
        conversation_id=out["conversation_id"],
        answer=out["answer"],
        scope=out["scope"],
        sources=out["sources"],
        suggested_questions=out["suggested_questions"],
        confidence=out["confidence"]
    )


@router.get("/conversations", response_model=List[AssistantConversationOut])
async def list_conversations(
    db: DBSession,
    current_user: CurrentUser,
    project_id: int = Query(..., description="Scope history to active project"),
):
    # Server-side validate project access
    await require_project_access(project_id, current_user, db)

    stmt = select(AssistantConversation).where(
        and_(
            AssistantConversation.user_id == current_user.id,
            AssistantConversation.project_id == project_id,
            AssistantConversation.is_active == True
        )
    ).order_by(AssistantConversation.updated_at.desc())
    
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/conversations/{id}", response_model=List[AssistantMessageOut])
async def get_conversation_messages(
    id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    # Fetch conversation and verify ownership
    conv_stmt = select(AssistantConversation).where(
        AssistantConversation.id == id,
        AssistantConversation.is_active == True
    )
    conv_res = await db.execute(conv_stmt)
    conv = conv_res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Fetch messages
    msg_stmt = select(AssistantMessage).where(
        AssistantMessage.conversation_id == id
    ).order_by(AssistantMessage.created_at.asc())
    
    res = await db.execute(msg_stmt)
    return res.scalars().all()


@router.delete("/conversations/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    # Fetch conversation and verify ownership
    conv_stmt = select(AssistantConversation).where(
        AssistantConversation.id == id,
        AssistantConversation.is_active == True
    )
    conv_res = await db.execute(conv_stmt)
    conv = conv_res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    conv.is_active = False
    await db.commit()


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: AssistantFeedbackRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    # Verify message ownership
    conv_stmt = select(AssistantConversation).where(
        AssistantConversation.id == payload.conversation_id
    )
    conv = (await db.execute(conv_stmt)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    feedback = AssistantFeedback(
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        user_id=current_user.id,
        feedback_type=payload.feedback_type,
        comment=payload.comment
    )
    db.add(feedback)
    await db.commit()
    return {"status": "success"}


@router.get("/suggestions", response_model=List[str])
async def get_page_suggestions(
    current_user: CurrentUser,
    current_route: str = Query(..., description="Active page route path")
):
    return PlatformAssistantAgent.get_suggestions_for_route(current_route)
