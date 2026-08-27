from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from core.config import settings
from database import SessionLocal
from slowapi.middleware import SlowAPIMiddleware
from core.limiter import limiter

from api import tenant_router, auth_router, user_router, task_router

app = FastAPI(title="SaaS B2B Platform API", version="1.0.0")

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# YENİ: Kendi özel (Türkçe) Hız Sınırı hata yakalayıcımız
def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Çok fazla giriş denemesi yaptınız. Lütfen 1 dakika bekleyip tekrar deneyin."},
    )

app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)

# CORS kaynakları ortamdan gelir (CORS_ORIGINS), böylece canlıya çıkarken
# kod değil yapılandırma değişir. Bkz. core/config.py ve .env.example.
origins = [k.strip() for k in settings.cors_origins.split(",") if k.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# API Versiyonlama (v1)
api_v1 = APIRouter(prefix="/api/v1")

api_v1.include_router(tenant_router.router)
api_v1.include_router(user_router.router)
api_v1.include_router(task_router.router)
api_v1.include_router(auth_router.router)

# V1 router'ı ana uygulamaya dahil et
app.include_router(api_v1)

@app.get("/")
def read_root():
    return {
        "mesaj": "SaaS Backend API Başarıyla Çalışıyor!",
        "versiyon": "v1",
        "durum": "Aktif"
    }

logging.basicConfig(level=logging.ERROR) # Sadece hataları logla
logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Kritik Sistem Hatası: {request.url}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Sunucu tarafında beklenmeyen bir hata oluştu. Teknik ekip bilgilendirildi."},
    )

@app.get("/healthz", tags=["Sistem"])
def health_check():
    try:
        # Veritabanına basit bir ping atıyoruz
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "ok", "database": "healthy"}
    except Exception:
        logger.exception("Sağlık kontrolü başarısız")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "Database connection failed"}
        )
