from sqlalchemy.orm import Session
from uuid import UUID
from repositories.user_repository import UserRepository
from schemas.user import UserCreate
from schemas.user import UserUpdate
from core.security import verify_password, get_password_hash

class UserService:
    def __init__(self, db: Session):
        self.repository = UserRepository(db)

    def create_user(self, user_data: UserCreate, tenant_id: UUID):
        return self.repository.create_user(user_data, tenant_id)

    def get_users_by_tenant(self, tenant_id: UUID, skip: int = 0, limit: int = 100):
        return self.repository.get_users_by_tenant(tenant_id, skip, limit)

    def update_user(self, user_id: str, tenant_id: str, user_update: UserUpdate):
        return self.repository.update_user(user_id, tenant_id, user_update.model_dump(exclude_unset=True))

    def delete_user(self, user_id: str, tenant_id:str):
        return self.repository.delete_user(user_id, tenant_id)

    def change_password(self, user_id: str, tenant_id: str, current_password: str, new_password: str):
        # Kullanıcıyı bul — kiracı filtresiyle.
        # Bugün bu metot yalnızca current_user.id ile çağrılıyor, yani tenant_id
        # olmadan da güvenliydi. Yine de ekliyoruz: istisnası olan bir kural
        # unutulur, istisnası olmayan kural hatırlanır.
        user = self.repository.get_user_by_id(user_id, tenant_id)
        if not user:
            raise ValueError("Kullanıcı bulunamadı.")

        # Mevcut şifreyi doğrula
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("Mevcut şifreniz hatalı!")

        # Yeni şifreyi hashleyip kaydet
        self.repository.set_password(user, get_password_hash(new_password))
        return True