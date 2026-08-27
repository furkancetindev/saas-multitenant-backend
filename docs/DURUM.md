# DURUM — saas_backend

Son güncelleme: **26 Ağustos 2026**
Tamamlanan: **Faz 0 · Faz 1 · Faz 2 · Faz 3**

---

## Faz 3 — Row-Level Security (bu oturumda bitti)

### Alınan iki karar
1. **İki veritabanı rolü.** Uygulama `saas_app` ile bağlanır: superuser değil,
   tabloların sahibi değil, DDL yetkisi yok. Migration'lar `postgres` ile koşar.
2. **RLS kapsamı: sadece `tasks`.** `users` elle filtrede kalıyor — sebebi aşağıda.

### Neden ayrı rol zorunluydu — ölçüm

| Kim bağlanıyor | `app.tenant_id` | Sonuç |
|---|---|---|
| `postgres` (superuser + sahip), `FORCE` açık | Kuzey | **iki kiracının satırı da geldi** |
| `saas_app` (superuser değil, sahip değil) | Kuzey | sadece Kuzey'in satırı |
| `saas_app` | set edilmedi | **0 satır** (fail-closed) |
| `saas_app`, başka kiracı adına INSERT | Kuzey | politika reddetti |

Master prompt "sahip olacaksa `FORCE` zorunlu" diyordu. Ölçüm daha sert: superuser'ı
`FORCE` de durdurmuyor. `postgres` ile bağlanmaya devam etseydik politika yazılır,
testler yeşil kalır ve README yalan söylerdi.

### Eklenen / değişen
```
alembic/versions/3831f9c1e1fb_enable_rls_on_tasks.py   ENABLE + FORCE + USING + WITH CHECK
scripts/setup_db_role.py                               kısıtlı rolü kurar, yetki verir, doğrular
.env.example                                           iki URL, neden iki tane olduğu yazılı
core/config.py                                         migration_database_url eklendi
database.py                                            after_begin dinleyicisi
core/dependencies.py                                   get_tenant_db
alembic/env.py                                         migration URL'ini tercih eder
api/user_router.py, api/tenant_router.py               kiracı bağlamlı oturuma geçti
tests/conftest.py                                      admin + app rolü ayrı, rol kurulumu otomatik
tests/test_tenant_isolation.py                         4 → 6 test
```

### Yol boyunca çıkan gerçek bir hata
İlk politika `current_setting('app.tenant_id', true)::uuid` kullanıyordu.
`set_config(..., true)` bir kez çalıştırılmış bir **bağlantıda** transaction bitince
değer NULL'a değil **boş dizgeye** dönüyor ve `''::uuid` hata fırlatıyor. Havuzlanmış
bir uygulamada bu, her bağlantının ikinci isteğinden sonra başına gelir; fail-closed
"0 satır" yerine "500" olurdu. Politika `NULLIF(current_setting(...), '')` ile düzeltildi.
Migration'ın docstring'inde yazılı.

---

## Doğrulama

`pytest`: **6 passed** — Python 3.11 / 3.13 / 3.14.4, PostgreSQL 16.

Üç mutasyon deneyi (testlerin bir şey kanıtladığının kanıtı):

| Deney | Faz 2'de | Faz 3'te |
|---|---|---|
| `task_repository`'deki elle `tenant_id` filtrelerini kaldır | `2 failed` | **`6 passed`** — veritabanı tek başına koruyor |
| `set_config(..., true)` → `false` (yani `SET` davranışı) | — | `2 failed` — havuz sızıntısı yakalanıyor |
| Uygulama superuser ile bağlanırsa | — | `test_row_level_security_is_actually_enforced` kırmızı |

Canlı uygulama da RLS altında uçtan uca çalışıyor: 17 adımlık akış (iki şirket kaydı →
giriş → çalışan → görev → çapraz erişim denemeleri → şifre değişimi) tamamı geçti,
`/healthz` ok.

---

## Bilinen sınırlar

1. **RLS yalnızca `tasks` tablosunda.** `users` elle filtrede. Sebep: `/login`
   e-postayı kiracılar arası aramak zorunda ve `get_current_user` kiracıyı henüz
   bilmeden kullanıcıyı çekiyor. İkisi de RLS'i deler; çözümü her istekte ikinci bir
   ayrıcalıklı oturum açmak — havuz baskısını iki katına çıkarır. README'ye böyle yazılacak.
2. **`git init` yapıldı, ilk commit atıldı** (34 dosya, `.env` geçmişte yok).
   Ama **`C:\Users\furkan` bir git deposu** — `rev-parse --is-inside-work-tree` `true` döndü.
   Desktop altındaki her şey onun kapsamında olabilir. Kontrol edilmeli:
   ```powershell
   git -C C:\Users\furkan remote -v
   git -C C:\Users\furkan ls-files --error-unmatch Desktop/saas_backend/.env
   ```
3. `TaskUpdateDetail` içinde `assigned_to` yok → `update_task_detail`'deki
   `_validate_assignee` dalı ölü kod.
4. Token'da `tenant_id` yok, `jti`/iptal yok, refresh token yok. `users.email` global UNIQUE.
5. `gen_random_uuid()` PostgreSQL 13+ ister.
6. `pytest` çıktısında kalan uyarılar kütüphanelerden (starlette httpx, slowapi
   `asyncio.iscoroutinefunction`). Kendi kodumuzdakiler temizlendi.

---

## Sıradaki adım — Faz 4 (paketleme)

`requirements.txt` ve `.env.example` hazır. Kalanlar:

1. `scripts/seed_demo.py` — iki kiracı, gözle ayırt edilir veri.
   **Dikkat:** RLS artık aktif. Seed script'i `tasks`'e yazacaksa ya her kiracı için
   `app.tenant_id` set etmeli ya da `MIGRATION_DATABASE_URL` ile bağlanmalı.
2. `README.md` — şartname. "Kendin dene" bölümü + izolasyon modeli + yukarıdaki
   mutasyon tablosu + bilinen sınırlar.

### Faz 3'ü kendi makinende kurmak
```powershell
# .env'e ikinci URL'i ekle ve DATABASE_URL'i kısıtlı role çevir (bkz. .env.example)
#   DATABASE_URL=postgresql://saas_app:<parola-sec>@localhost:5432/saas_project
#   MIGRATION_DATABASE_URL=postgresql://postgres:12345@localhost:5432/saas_project

.\.venv\Scripts\Activate.ps1
alembic upgrade head
python scripts\setup_db_role.py
pytest -v
```
