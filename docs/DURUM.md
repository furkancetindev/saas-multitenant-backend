# DURUM — saas_backend

Son güncelleme: **26 Ağustos 2026**
Bu oturumda tamamlanan: **Faz 0 + Faz 1 + Faz 2**

---

## Bitti

### Faz 0 — Git hijyeni
- `.gitignore`'a `.idea/` ve `.pytest_cache/` eklendi.
- `SECRET_KEY` **yenilendi** (26 Ağu, PowerShell ile, 64 karakter). Eski token'lar
  geçersiz — frontend'de yeniden giriş gerekir.
- **Sende kalan:** `git init` + ilk commit + `git log --all --full-history -- .env`
  doğrulaması. Komut bloğu en altta.

### Faz 1 — Dört düzeltme
| Kod | Konu | Durum |
|---|---|---|
| A1 | Üç ayrı `Limiter` nesnesi | Kapandı — tek merkez `core/limiter.py` |
| A3 | `get_all_tenants()` filtresiz listeleme | Kapandı — silindi, gerekçe docstring'e yazıldı |
| A4 | `change_password` kiracı filtresiz | Kapandı — `tenant_id` imzaya ve filtreye girdi |
| A5 | Rate limit IP bazlı | Kapandı — kimlik bazlı `key_func` + iki yazma endpoint'inde limit |

**A1 hakkında düzeltme:** master prompt "limitler beklendiği gibi uygulanmıyor" diyordu;
ölçüm bunu doğrulamadı. Düzeltme öncesi kodda `/login` 5 istekten sonra 429 veriyordu.
slowapi'de `@limiter.limit` dekoratörü limiti kendi Limiter nesnesi üzerinden uyguluyor;
middleware'in `app.state.limiter`'ı bu rotaları hiç tanımıyordu. A1 bir bug düzeltmesi
değil, **A5'in ön koşulu**: yerel limiter'lar `key_func` değişikliğinden etkilenmeyecekti.

### Faz 1 sonrası alınan dört karar
1. Demo e-postaları `@kuzey.example.com` / `@ayyapi.example.com` (RFC 2606).
   `.test` uzantısı `email-validator` tarafından reddediliyordu — kayıt 422 dönüyordu.
2. `requirements.txt`'te `bcrypt==4.0.1` pinlendi. `passlib 1.7.4` + `bcrypt 5.x`
   temiz venv'de her şifre işleminde patlıyor.
3. A5 gerçekten devreye alındı: `POST /tasks/` ve `POST /users/` 60/dakika limitli.
4. `is_active` NULL tuzağı yeni migration ile kapatıldı (`8676506d8095`).

### Faz 2 — Testler
- `GET /tasks/{task_id}` eklendi (repository → service → router), çapraz kiracıda 404.
- `tests/conftest.py`: ayrı test veritabanı, her koşuda `DROP SCHEMA` + **Alembic ile**
  şema kurulumu. `create_all()` değil — RLS politikaları migration'da yaşayacak,
  modelden kurulan şema onları sessizce atlar ve izolasyon kanıtı boşa çıkardı.
- `tests/test_tenant_isolation.py`: 4 test (spec'te 3 vardı; dördüncüsü hata
  sözleşmesini eşitlik olarak ifade ediyor — başka kiracının kaydı ile hiç var olmamış
  kayıt aynı gövdeyi döndürmeli).

---

## Doğrulama — bulut ortamında gerçek PostgreSQL 16

Üç Python sürümünde, `requirements.txt`'ten temiz kurulumla:

| Python | Sonuç |
|---|---|
| 3.11.15 | `4 passed, 2 warnings` |
| 3.13.13 | `4 passed, 1 warning` |
| **3.14.4** (Furkan'ın venv'i) | `4 passed, 5 warnings` |

`bcrypt==4.0.1` üçünde de kuruluyor: paket `cp36-abi3` etiketli wheel yayınlıyor,
yani 3.6+ her CPython'da çalışıyor — 2022'den kalma olması kurulumu engellemiyor.

> Not: 3.14.0**rc2** üzerinde `import fastapi` pydantic içinde `AssertionError` ile
> patlıyordu. Final 3.14.4'te sorun yok — o bulgu release candidate'a özgüymüş.

Ayrıca ölçülenler:

- **Testlerin dişi var.** `task_repository.py`'deki kiracı filtrelerini geçici olarak
  kaldırdım → `2 failed, 2 passed`. Ay Yapı, Kuzey'in görevini listede gördü ve
  GET ile 200 aldı. Faz 3'ün kabul kanıtı aynı deney: RLS eklenince bu deney
  **4 passed** vermeli. Şu anki hâli "önce" fotoğrafı.
- **A5 davranışsal olarak doğrulandı.** Kuzey `POST /tasks/`'a 60 istek geçirdi,
  61.'de 429 aldı. Tam o sırada Ay aynı endpoint'e vurdu → **200**. Kovalar ayrı.
- **`is_active` düzeltmesi doğrulandı.** Migration öncesi düz SQL INSERT → NULL →
  kullanıcı kalıcı 403. Migration sonrası aynı INSERT → `true`. Downgrade/upgrade
  gidiş-dönüşü temiz.
- `alembic upgrade head` üç migration'ı da temiz geçiyor.

---

## Bilinen sınırlar / açık konular

1. **`git init` + ilk commit + `SECRET_KEY` rotasyonu** — sende.
   `saas_backend`'de `.git` yok, yani `.env` bu repo geçmişinde olamaz. Ama
   `C:\Users\furkan\.git` mevcut; ev dizini bir depo ise Desktop altındaki her şey
   onun kapsamında olabilir. Önce bunu kontrol et.
2. **`TaskUpdateDetail` içinde `assigned_to` yok.** Bu yüzden `update_task_detail`
   içindeki `_validate_assignee` dalı ölü kod. Çapraz kiracı atama koruması sadece
   `POST /tasks/` yolunda sınanabiliyor — testler de öyle yapıyor.
3. **pytest uyarıları — kendi payımız temizlendi.** `core/config.py`,
   `schemas/user.py` ve `schemas/tenant.py` pydantic v2 `ConfigDict`/`SettingsConfigDict`
   kullanacak şekilde güncellendi (Faz 4'ten öne çekildi). Kalan uyarılar kütüphanelerden:
   starlette'in httpx uyarısı ve Python 3.14'te slowapi'nin `asyncio.iscoroutinefunction`
   uyarısı (dört limitli endpoint için dört kez). Bunlar bizim kodumuz değil, gizlemiyoruz.
4. **`gen_random_uuid()` PostgreSQL 13+ gerektirir.** Daha eskisinde `pgcrypto`
   eklentisi lazım. README'ye yazılacak.
5. Token'da `tenant_id` yok, `jti`/iptal yok, refresh token yok. `users.email`
   global UNIQUE. Hepsi README "bilinen sınırlar" bölümüne.

---

## Sıradaki adım — Faz 3 (Row-Level Security)

Master prompt'taki dört tuzak geçerli: `FORCE` şart · `SET` değil `set_config(..., true)` ·
`get_db`'de kiracı `get_current_user`'dan sonra biliniyor · `/login` ve `/tenants/register`
kiracısız çalışıyor.

Kabul kanıtı hazır: filtre kaldırma deneyi şu an **2 failed** veriyor, RLS sonrası
**4 passed** vermeli.

### Faz 0'ı kapatmak için elle çalıştırılacak komutlar
```powershell
cd C:\Users\furkan\Desktop\saas_backend

# 0) SECRET_KEY'i yenile (değer hiçbir yere gitmez, sadece .env'e yazılır)
python -c "import secrets,pathlib,re; p=pathlib.Path('.env'); t=p.read_text(encoding='utf-8'); p.write_text(re.sub(r'^SECRET_KEY=.*$','SECRET_KEY='+secrets.token_hex(32),t,flags=re.M),encoding='utf-8'); print('yenilendi')"

# 1) Ev dizini bir git deposu mu? "true" derse .env oradaki geçmişte olabilir.
git -C C:\Users\furkan rev-parse --is-inside-work-tree

# 2) Repoyu başlat
git init
git add .
git status --short          # .env burada GÖRÜNMEMELİ
git commit -m "Initial commit: multi-tenant SaaS backend (FastAPI + PostgreSQL)"

# 3) Çıktı BOŞ olmalı
git log --all --full-history -- .env
```

### Testleri kendi makinende koşturmak
```powershell
createdb saas_project_test          # ya da pgAdmin'den oluştur
pip install -r requirements.txt
pytest -v
```
`TEST_DATABASE_URL` verilmezse `DATABASE_URL`'in sonuna `_test` eklenir.
İkisi aynı çıkarsa suite çalışmayı reddeder — her koşu şemayı siliyor.
