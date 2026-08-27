from uuid import UUID # YENİ EKLENDİ
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.dependencies import get_tenant_db, get_current_user, require_role, get_user_service
from schemas.user import UserCreate, UserResponse, UserUpdate, UserPasswordUpdate
from services.user_service import UserService
from core.limiter import limiter
from models.domain import User

router = APIRouter(prefix="/users", tags=["Çalışanlar (Users)"])

@router.post("/", response_model=UserResponse)
@limiter.limit("60/minute")  # Anahtar kimlik bazlı: bkz. core/limiter.py
def create_user(
    request: Request,  # slowapi dekoratörünün zorunlu kıldığı parametre
    user: UserCreate,
    current_user: User = Depends(require_role("admin")), # Sadece admin çalışan ekleyebilir
    db: Session = Depends(get_tenant_db),
):
    try:
        service = UserService(db)
        return service.create_user(user, tenant_id=current_user.tenant_id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bu e-posta adresi zaten kayıtlı.")

@router.get("/", response_model=list[UserResponse])
def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    service = UserService(db)
    return service.get_users_by_tenant(current_user.tenant_id, skip=skip, limit=limit)

@router.put("/{user_id}", response_model=UserResponse)
def update_user(
        user_id: UUID, # str yerine UUID yapıldı
        user_update: UserUpdate,
        current_user: User = Depends(require_role("admin")),
        user_service: UserService = Depends(get_user_service)
):
        # Servise gönderirken str() ile çeviriyoruz
        updated = user_service.update_user(str(user_id), current_user.tenant_id, user_update)
        if not updated:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı!")
        return updated

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
        user_id: UUID, # str yerine UUID yapıldı
        current_user: User = Depends(require_role("admin")),
        user_service: UserService = Depends(get_user_service)
):
    # Tip güvenliği için her ikisini de string olarak karşılaştırıyoruz
    if str(current_user.id) == str(user_id):
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz!")

    # Servise gönderirken str() ile çeviriyoruz
    success = user_service.delete_user(str(user_id), current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadi!!")
    return None

@router.patch("/me/password")
def change_my_password(
    data: UserPasswordUpdate,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    try:
        user_service.change_password(
            str(current_user.id),
            current_user.tenant_id,
            data.current_password,
            data.new_password,
        )
        return {"detail": "Şifreniz başarıyla güncellendi."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))