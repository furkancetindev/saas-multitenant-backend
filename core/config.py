from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Uygulamanın bağlandığı rol. Superuser OLMAMALI: superuser Row-Level
    # Security'yi FORCE açıkken bile baypas eder, politikalar sessizce etkisiz kalır.
    database_url: str

    # Alembic'in kullandığı, şema değiştirme yetkisi olan rol (tabloların sahibi).
    # Ayrı tutulmasının sebebi: uygulama rolü DDL çalıştıramasın.
    # Verilmezse database_url'e düşer — tek rollü basit kurulumlar için.
    migration_database_url: str | None = None

    # Tarayıcıdan istek atmasına izin verilen kaynaklar, virgülle ayrılmış.
    # Varsayılan yerel geliştirme içindir; prod'da frontend'in domaini verilir.
    # Joker (*) kullanma: allow_credentials açıkken tarayıcılar zaten reddeder.
    cors_origins: str = (
        "http://localhost:3000,http://localhost:5173,"
        "http://127.0.0.1:3000,http://127.0.0.1:5173"
    )

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()