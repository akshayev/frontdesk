"""Request/response models for agent and lead APIs. Implements: UI-2, UI-3, UI-4, CLM-3, RPT-1,
SECURITY §6."""

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import AgentRole


class LoginIn(BaseModel):
    """POST /api/auth/login body. Password length capped to bound hashing work."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class AgentOut(BaseModel):
    """Public view of an agent. Deliberately has no password_hash / lock fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: AgentRole
