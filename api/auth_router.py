from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func  # YENİ: func eklendi

from core.dependencies import get_db, get_current_user
from models.domain import User
from core.security import verify_password, create_access_token
from core.limiter import limiter  # Merkezi limiter — sayaç tek yerde tutulur
from schemas.user import UserResponse


router = APIRouter(tags=["Kimlik Doğrulama (Auth)"])


@router.post("/login")
@limiter.limit("5/minute")  # 1 Dakika içinde aynı IP'den en fazla 5 giriş denemesi yapılabilir
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Kiracı filtresi olmayan iki sorgudan biri — bilinçli.
    # Giriş anında kiracı henüz bilinmiyor; kiracıyı zaten bu sorgunun sonucu belirliyor.
    # (users.email global UNIQUE olduğu için sonuç tekildir. Bkz. README "Bilinen sınırlar".)
    # func.lower() ile her iki tarafı küçük harfe çevirerek karşılaştırıyoruz
    user = db.query(User).filter(func.lower(User.email) == form_data.username.lower()).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="E-posta veya şifre hatalı!")

    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user