from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from uuid import UUID
from datetime import datetime

# user.py içindeki şifre kuralı fonksiyonumuzu buraya da dahil ediyoruz
from schemas.user import validate_password

class TenantBase(BaseModel):
    name: str

class TenantCreate(TenantBase):
    pass

class TenantResponse(TenantBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CompanyRegister(BaseModel):
    company_name: str
    admin_full_name: str
    admin_email: EmailStr
    admin_password: str

    # Pydantic v2 validator'ı ile admin şifresini güvenlik testinden geçiriyoruz
    @field_validator('admin_password')
    @classmethod
    def check_admin_password(cls, v):
        return validate_password(v)