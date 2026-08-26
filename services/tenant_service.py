from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from repositories.tenant_repository import TenantRepository
from repositories.user_repository import UserRepository
from schemas.tenant import CompanyRegister
from models.domain import Tenant, User
from core.security import get_password_hash


class TenantService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = TenantRepository(db)
        self.user_repository = UserRepository(db)

    def register_company(self, data: CompanyRegister):
        if len(data.company_name) < 3:
            raise ValueError("Şirket adı en az 3 karakter olmalıdır!")

        try:
            # 1. Tenant oluştur (Sadece Session'a ekliyoruz, commit yok)
            yeni_sirket = Tenant(name=data.company_name)
            self.db.add(yeni_sirket)
            self.db.flush()  # ID'nin oluşması için flush yapıyoruz

            # 2. Admin kullanıcı oluştur (Email'i küçük harfe çevirerek kaydediyoruz)
            hashed_pw = get_password_hash(data.admin_password)
            admin_user = User(
                tenant_id=yeni_sirket.id,
                full_name=data.admin_full_name,
                email=data.admin_email.lower(),
                hashed_password=hashed_pw,
                role="admin"
            )
            self.db.add(admin_user)

            # 3. Her iki işlem de başarılıysa kalıcı hale getir
            self.db.commit()
            self.db.refresh(yeni_sirket)
            return yeni_sirket

        except IntegrityError:
            self.db.rollback()  # Hata çıkarsa tüm işlemleri geri al
            raise ValueError("Bu e-posta adresi zaten kullanılıyor.")
        except Exception as e:
            self.db.rollback()
            raise ValueError("Kayıt işlemi sırasında beklenmeyen bir hata oluştu.")

    def get_tenant_by_id(self, tenant_id):
        return self.repository.get_tenant_by_id(tenant_id)