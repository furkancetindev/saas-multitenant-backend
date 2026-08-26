from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from database import SessionLocal
from models.domain import User
from core.config import settings

# --- Servis Importları ---
from services.task_service import TaskService
from services.tenant_service import TenantService
from services.user_service import UserService


# 1. Veritabanı Oturumu
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 2. Kimlik Doğrulama Ayarları
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik doğrulanmadı, lütfen tekrar giriş yapınız!",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Kiracı filtresi olmayan iki sorgudan biri — bilinçli.
    # Kiracı kimliği bu satırın çıktısından doğar (user.tenant_id); token onu taşımaz.
    # Bu noktadan SONRA yapılan her sorgu tenant_id ile filtrelenir.
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    # Kullanıcı pasife alınmış mı?
    # (is_active artık NOT NULL + server_default true — getattr korumasına gerek yok.)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hesabınız askıya alınmıştır. Lütfen yöneticiyle iletişime geçin."
        )

    return user


def require_role(*allowed_roles: str):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için yetkiniz bulunmuyor."
            )
        return current_user

    return role_checker


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    return TaskService(db)


def get_tenant_service(db: Session = Depends(get_db)) -> TenantService:
    return TenantService(db)


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)