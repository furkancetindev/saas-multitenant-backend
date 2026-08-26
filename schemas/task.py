from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"

class TaskCreate(TaskBase):
    assigned_to: Optional[UUID] = None

class TaskResponse(TaskBase):
    id: UUID
    tenant_id: UUID
    assigned_to: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TaskUpdate(BaseModel):
    status:str

class TaskUpdateDetail(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


