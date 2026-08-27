from fastapi import APIRouter, Depends, HTTPException, Request # Request eklendi
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from core.dependencies import get_db, get_tenant_db, get_current_user
from core.limiter import limiter  # Merkezi limiter — sayaç tek yerde tutulur
from schemas.tenant import CompanyRegister, TenantResponse
from services.tenant_service import TenantService
from models.domain import User

router = APIRouter(prefix="/tenants", tags=["Şirketler (Tenants)"])

@router.post("/register", response_model=TenantResponse)
@limiter.limit("3/minute") # Dakikada maksimum 3 kayıt denemesi yapılabilir
def register_company(request: Request, data: CompanyRegister, db: Session = Depends(get_db)):
    # Ham get_db kullanan iki yoldan biri (diğeri /login). Kiracı bu isteğin
    # SONUCUNDA doğuyor; başında set edilecek bir tenant_id yok.
    # tasks tablosuna dokunmadığı için RLS politikası da devreye girmiyor.
    try:
        service = TenantService(db)
        return service.register_company(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bu e-posta adresi zaten kullanılıyor.")

@router.get("/me", response_model=TenantResponse)
def get_my_tenant(current_user: User = Depends(get_current_user), db: Session = Depends(get_tenant_db)):
    service = TenantService(db)
    tenant = service.get_tenant_by_id(current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Şirket bulunamadı.")
    return tenant