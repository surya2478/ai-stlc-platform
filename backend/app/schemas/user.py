from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TokenProjectMembership(BaseModel):
    project_id: int
    role: str
    permissions: list[str]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8, max_length=72)
    role: str = "qa_engineer"
    is_superuser: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class UserRead(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    is_superuser: bool

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    global_role: str | None = None
    project_memberships: list[TokenProjectMembership] = []


class TokenData(BaseModel):
    user_id: int | None = None
