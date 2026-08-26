from sqlalchemy.orm import Session
from uuid import UUID
from models.domain import User
from schemas.user import UserCreate
from core.security import get_password_hash

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, user_data: UserCreate, tenant_id: UUID):
        user_dict = user_data.model_dump()
        acik_sifre = user_dict.pop("password")
        kriptolu_sifre = get_password_hash(acik_sifre)

        yeni_kullanici = User(**user_dict, tenant_id=tenant_id, hashed_password=kriptolu_sifre)
        self.db.add(yeni_kullanici)
        self.db.commit()
        self.db.refresh(yeni_kullanici)
        return yeni_kullanici

    def get_user_by_id(self, user_id: str, tenant_id: str):
        # Kural: kullanıcı tablosuna yapılan HER sorgu tenant_id taşır. İstisna yok.
        return (
            self.db.query(User)
            .filter(User.id == user_id, User.tenant_id == tenant_id)
            .first()
        )

    def set_password(self, user: User, hashed_password: str):
        user.hashed_password = hashed_password
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_users_by_tenant(self, tenant_id: UUID, skip: int = 0, limit: int = 100):
        return (
            self.db.query(User)
            .filter(User.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .all()
        )



    def update_user(self, user_id: str, tenant_id: str, update_data: dict):
        user = self.db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
        if user:
            for key, value in update_data.items():
                if value is not None:
                    setattr(user, key, value)
            self.db.commit()
            self.db.refresh(user)
        return user

    def delete_user(self, user_id: str, tenant_id: str) -> bool:
        user = self.db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
        if user:
            self.db.delete(user)
            self.db.commit()
            return True
        return False

