from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


@event.listens_for(SessionLocal, "after_begin")
def kiraci_baglamini_uygula(session, transaction, connection):
    """
    Her yeni transaction'da kiracıyı veritabanına bildirir.
    PostgreSQL Row-Level Security politikaları bu `app.tenant_id` ayarını okur.

    Neden transaction başında, istek başında değil: bir oturum ömrü boyunca
    birden fazla transaction açar — her `commit()` mevcut olanı kapatır, bir
    sonraki sorgu yenisini başlatır. Ayarı yalnızca istek başında bir kez
    yapsaydık, ilk commit'ten sonraki her sorgu ayarsız kalırdı ve RLS
    (doğru şekilde) sıfır satır döndürürdü.

    Neden `set_config(..., true)`, `SET` değil: üçüncü argüman `true` ayarı
    transaction'a bağlar. `SET` kullansaydık ayar bağlantı havuzunda kalır ve
    o bağlantıyı sonra alan istekte — muhtemelen başka bir kiracıda —
    geçerli olmaya devam ederdi. Çözmeye çalıştığımız sızıntının aynısını
    kendi elimizle üretirdik.

    Kiracı bilgisi `session.info` üzerinden gelir; oraya `get_tenant_db`
    bağımlılığı yazar (bkz. core/dependencies.py).
    """
    tenant_id = session.info.get("tenant_id")
    if tenant_id is not None:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
