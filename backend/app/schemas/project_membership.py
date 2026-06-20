from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.services.rbac_service import ROLE_PERMISSIONS


class ProjectMembershipCreate(BaseModel):
    user_id: int
    role: str


class ProjectMembershipUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class ProjectMembershipOut(BaseModel):
    id: int
    project_id: int
    user_id: int
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectRoleOut(BaseModel):
    role: str
    permissions: list[str]


def available_project_roles() -> list[ProjectRoleOut]:
    return [
        ProjectRoleOut(role=role, permissions=sorted(permissions))
        for role, permissions in sorted(ROLE_PERMISSIONS.items())
    ]
