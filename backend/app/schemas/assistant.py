from pydantic import BaseModel, ConfigDict
from typing import Any, Literal
from datetime import datetime


class AssistantChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    current_route: str | None = None
    project_id: int


class AssistantChatResponse(BaseModel):
    conversation_id: int
    answer: str
    scope: str
    sources: list[dict[str, Any]]
    suggested_questions: list[str]
    confidence: str


class AssistantConversationOut(BaseModel):
    id: int
    title: str | None
    project_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssistantMessageOut(BaseModel):
    id: int
    role: str
    content: str
    scope_classification: str | None
    confidence: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssistantFeedbackRequest(BaseModel):
    conversation_id: int
    message_id: int
    feedback_type: Literal["helpful", "unhelpful"]
    comment: str | None = None
