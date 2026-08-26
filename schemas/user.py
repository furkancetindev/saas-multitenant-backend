from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional
from enum import Enum
import re # Şifre Harf/Rakam kontrolü için Regex eklendi

# Rolleri Enum ile kısıtlıyoruz
class UserRole(str, Enum):
    admin = "admin"
    developer = "developer"
    user = "user" # Frontend ile uyumlu olması için 'employee' yerine 'user' yapıldı

class UserBase(BaseModel):
    full_name: str
    email: EmailStr
    role: UserRole = UserRole.user

def validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError('Şifre en az 8 karakter uzunluğunda olmalıdır!')
    if len(v) > 72:
        raise ValueError('Şifre en fazla 72 karakter uzunluğunda olabilir!')
    if not re.search(r'[A-Za-z]', v) or not re.search(r'\d', v):
        raise ValueError('Şifre en az bir harf ve bir rakam içermelidir!')
    return v

class UserCreate(UserBase):
    password: str

    # Pydantic v2 için field_validator kullanıyoruz
    @field_validator('password')
    @classmethod
    def check_password(cls, v):
        return validate_password(v)

class UserResponse(UserBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None

class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def check_new_password(cls, v):
        return validate_password(v)