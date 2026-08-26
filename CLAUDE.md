# CLAUDE.md — saas_backend proje bağlamı

Bu dosya her yeni oturumda otomatik okunur. Sohbet hafızası kaybolur, bu dosya kalır.
**Kalıcı olmasını istediğin her karar buraya yazılır.**

---

## Proje nedir

Çok kiracılı (multi-tenant) B2B SaaS backend'i: FastAPI + PostgreSQL.
Bir müşteriye teslim edilmiyor — **satış kanıtı** olarak var. Hedef okuyucu, yurt dışındaki
3–15 kişilik yazılım ajanslarının kurucusu/CTO'su. Repoyu açıp `tests/test_tenant_isolation.py`
dosyasına bakacak ve 20 saniyede ne sattığımızı anlayacak.

Bundan çıkan kural: **okunabilirlik ve kanıtlanabilirlik > özellik sayısı.**

## Yığın

Python 3 · FastAPI · SQLAlchemy 2.x · PostgreSQL · Alembic · python-jose (JWT) ·
passlib[bcrypt] · pydantic v2 + pydantic-settings · slowapi · pytest + httpx

**`bcrypt==4.0.1` pinini kaldırma.** `passlib 1.7.4`, `bcrypt 4.1+`'ta kaldırılan
iç API'leri okuyor; `bcrypt 5.x` ile her hash/verify çağrısı
`ValueError: password cannot be longer than 72 bytes` ile patlıyor. Temiz bir venv'de
`pip install -r requirements.txt` sonrası uygulamanın ayağa kalkması bu pine bağlı.
`gen_random_uuid()` PostgreSQL 13+ gerektirir; daha eskisinde `pgcrypto` lazım.

Frontend ayrı repo: `saas-frontend` — React + Vite (JS, TS değil), React Router, axios,
JWT `localStorage`'da.

**Eklenmeyecek:** Docker, Redis, Celery, yeni ORM/framework.

## Geliştirme ortamı (doğrulandı, 26 Ağu 2026)

Furkan: Windows, **proje içi venv** → `.venv\Scripts\python.exe`, **Python 3.14.4**.
`python` komutu PATH'te yok — Microsoft Store'un sahte kısayolu araya giriyor.
Komut önerirken ya venv'i aktive ettir (`.\.venv\Scripts\Activate.ps1`) ya da tam yol kullan.
Python gerektirmeyen bir yol varsa (ör. PowerShell'in kendi araçları) onu tercih et.

`pytest` üç sürümde de yeşil: 3.11.15, 3.13.13 ve 3.14.4 (Furkan'ın makinesinde de,
Windows üzerinde: `4 passed, 5 warnings`). Kalan uyarılar kütüphanelerden —
starlette'in httpx uyarısı ve slowapi'nin `asyncio.iscoroutinefunction` uyarısı.

## Mimari kuralı

Katmanlar: `api/` → `services/` → `repositories/` → `models/`
Yeni kod da bu katmanlara uyacak. Router'da doğrudan sorgu yazma; repository'yi atlama.

## Kiracı izolasyonu — projenin özü

- Paylaşılan şema, her tablo `tenant_id` taşır (`tenants.id`'ye FK, ON DELETE CASCADE).
- Kiracı, JWT'deki `sub` (user id) → `get_current_user` → `user.tenant_id` zincirinden gelir.
  Token'da `tenant_id` **yok**.
- Her repository sorgusunda `tenant_id` filtresi **zorunlu**. İstisna kabul edilmez.
- Ek olarak PostgreSQL Row-Level Security. Kritik detaylar:
  - `FORCE ROW LEVEL SECURITY` şart — sahibi/superuser aksi hâlde bypass eder.
  - Bağlantı havuzlu: **`SET LOCAL` / `set_config(..., true)` kullan, `SET` kullanma.**
    `SET` bir sonraki isteğe sızar ve çözmeye çalıştığın sızıntıyı yaratır.
  - `/login` ve `/tenants/register` kiracı bilinmeden çalışır; RLS kapsamına alınırken
    ayrı bir DB rolü gerekir.
- **Hata sözleşmesi:** çapraz kiracı erişiminde daima `404`, asla `403`.
  Kaydın varlığını bile sızdırmıyoruz.

## Şema özeti

`tenants(id UUID PK, name, created_at)`
`users(id UUID PK, tenant_id FK CASCADE, full_name, email UNIQUE, hashed_password, role, is_active, created_at)`
`tasks(id UUID PK, tenant_id FK CASCADE, title, description, status, assigned_to FK users SET NULL, created_at)`

Roller: `admin` · `developer` · `user`
UUID'ler Postgres `gen_random_uuid()` ile üretilir — **SQLite ile çalışmaz**, testler de Postgres ister.

**Bilinçli sadeleştirme:** `users.email` global UNIQUE, `UNIQUE(tenant_id, email)` değil.
Yani aynı e-posta iki kiracıda kullanıcı olamaz. README'de belgelenmiştir; değiştirmeden önce sor.

## API

Tüm yollar `/api/v1` önekiyle.
Açık: `POST /tenants/register` (3/dk), `POST /login` (5/dk, `username` alanı e-posta).
Auth: `GET /me`, `GET /tenants/me`, `/users/*`, `/tasks/*`.
Admin gerektirenler: `POST /users/`, `PUT /users/{id}`, `DELETE /users/{id}`.
Liste endpoint'lerinde `skip` + `limit ≤ 100`.

## Demo verisi

İki kiracı: **Kuzey Lojistik** (`admin@kuzey.example.com`, `calisan@kuzey.example.com`) ve
**Ay Yapı** (`admin@ayyapi.example.com`). Şifre: `Parola123`.
`scripts/seed_demo.py` ile yüklenir. README'deki "kendin dene" bölümü bu verilere dayanır.

**`.test` KULLANMA.** `pydantic`'in `EmailStr`'ı arkasındaki `email-validator`,
RFC 6761 ayrılmış alan adlarını (`.test`, `.invalid`, `.localhost`) reddediyor —
`admin@kuzey.test` ile kayıt **422** döner. `example.com` alt alan adları RFC 2606
gereği asla gerçek bir adrese denk gelmez ve doğrulamadan geçer.

## Testler

- Testler **gerçek PostgreSQL** ister. SQLite yok: UUID sütunları, `gen_random_uuid()`
  ve Faz 3'te gelecek RLS politikaları Postgres'e bağımlı.
- `tests/conftest.py` şemayı **Alembic migration'larıyla** kurar,
  `Base.metadata.create_all()` ile değil. Sebep: RLS politikaları migration'da yaşar,
  modelde değil. Modelden kurulan şema onları sessizce atlar ve izolasyon testi
  kanıtlamak istediği şeyin olmadığı bir veritabanında koşar.
- `TEST_DATABASE_URL` verilmezse `DATABASE_URL`'e `_test` eklenir. İkisi aynı çıkarsa
  suite çalışmayı reddeder — her koşu `DROP SCHEMA public CASCADE` yapıyor.
- Testlerde `limiter.enabled = False`. Hız sınırı izolasyondan bağımsız ve TestClient
  hep aynı IP'yi gösterdiği için açık bırakılırsa testler 429'la kırılır.
- **Testlerin dişi olduğu doğrulandı:** `task_repository.py`'deki `tenant_id`
  filtreleri kaldırıldığında suite kırmızıya döner. Faz 3'ün kabul kanıtı bu deneyin
  RLS ile yeşil kalması.

## Dil

Kod yorumları ve API hata mesajları **Türkçe** (mevcut hâli koru).
README, testler ve commit mesajları **İngilizce** — hedef kitle yabancı.

## Asla

- `.env` commit etme. Değişiklik sonrası `git log --all --full-history -- .env` ile doğrula.
- `.venv/`, `__pycache__/`, `node_modules/` okuma / listeleme / stage etme.
- Router'da doğrudan veritabanı sorgusu yazma.
- `tenant_id` filtresi olmayan sorgu yazma.
- Sorulmadan yeni özellik, yeni kütüphane veya yeni klasör ekleme.

## Oturum sonu ritüeli

1. Commit at.
2. `docs/DURUM.md`'i güncelle: ne bitti, ne yarım kaldı, sıradaki adım ne.
3. Kalıcı bir karar aldıysan bu dosyaya (CLAUDE.md) yaz.

## Güncel durum

`docs/DURUM.md` dosyasına bak. Yoksa proje henüz Faz 0'da demektir.

26 Ağu 2026 itibarıyla: Faz 0 (git kısmı hariç), Faz 1 ve Faz 2 bitti. Sırada Faz 3 (RLS).
