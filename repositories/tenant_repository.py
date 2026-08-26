from sqlalchemy.orm import Session
from models.domain import Tenant
from schemas.tenant import TenantCreate

class TenantRepository:
    """
    Kiracı (tenant) kayıtlarına erişim.

    Bilinçli olarak "tüm kiracıları listele" metodu yoktur: böyle bir metot bir gün
    bir endpoint'e bağlanırsa her müşteri diğerlerinin listesini görür. Platform
    yönetimi için gerekirse, kiracı içi `role` alanından **bağımsız** ayrı bir
    sistem-yöneticisi kontrolünün arkasına alınmalıdır.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_tenant_by_id(self, tenant_id: str):
        return self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

    def create_tenant(self, tenant_data: TenantCreate):
        yeni_sirket = Tenant(name=tenant_data.name)
        self.db.add(yeni_sirket)
        self.db.commit()
        self.db.refresh(yeni_sirket)
        return yeni_sirket




