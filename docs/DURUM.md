# DURUM — saas_backend

Son güncelleme: **26 Ağustos 2026**
Tamamlanan: **Faz 0 · 1 · 2 · 3** — ve **Faz 4'ün README + seed kısmı**

---

## Durum özeti

`pytest` → **6 passed**, hem bulut ortamında hem Furkan'ın makinesinde
(Windows, Python 3.14.4, PostgreSQL, parola doğrulamalı).

| Faz | Durum |
|---|---|
| 0 — Git hijyeni | Bitti. `git init` + ilk commit atıldı, `.env` geçmişte yok, `SECRET_KEY` yenilendi |
| 1 — A1/A3/A4/A5 | Bitti |
| 2 — Testler | Bitti. 6 test |
| 3 — Row-Level Security | Bitti. `tasks` tablosunda, iki DB rolü ile |
| 4 — Paketleme | `requirements.txt`, `.env.example`, `scripts/seed_demo.py`, `README.md` hazır |
| 5 — Canlıya alma | Başlanmadı |
| 6 — Demo videosu | Başlanmadı |

---

## Faz 4'te yapılanlar

### `scripts/seed_demo.py`
İki kiracı, **sabit UUID'lerle**. Sebep: README'nin "kendin dene" bölümü okura
yapıştırabileceği bir görev kimliği vermeli; rastgele UUID olsaydı README ancak
demoyu tarif edebilirdi, veremezdi.

- Kuzey Lojistik — `admin@kuzey.example.com`, `calisan@kuzey.example.com`, 5 nakliye görevi
- Ay Yapı — `admin@ayyapi.example.com`, 4 şantiye görevi
- Şifre: `Parola123`
- README'nin alıntıladığı görev: `aaaa0000-0000-0000-0000-000000000001`

Seed, **uygulama rolüyle ve RLS altında** yazıyor — `app.tenant_id` bağlamını
tıpkı bir istek gibi kuruyor. Doğrulandı: `_set_tenant` çağrısı kaldırıldığında
INSERT'ler `new row violates row-level security policy` ile reddediliyor.
`--reset` adımı yönetici rolüyle koşar (uygulama rolünde TRUNCATE yetkisi yok
ve olmamalı).

### `README.md`
Şartname olarak yazıldı, portföy metni olarak değil. Merkezinde mutasyon tablosu var:

| Şunu boz | Suite ne diyor |
|---|---|
| `task_repository.py`'deki bütün `tenant_id` filtrelerini sil | `6 passed` |
| `set_config(..., true)` → `false` | `2 failed` |
| `DATABASE_URL`'i superuser'a çevir | suite başlamayı reddediyor |

README'deki her `curl` komutu birebir çalıştırılarak doğrulandı. İki 404
gövdesinin (başka kiracının kaydı / hiç var olmamış kayıt) **bayt bayt aynı**
olduğu ölçüldü.

---

## Bu turda bulunan gerçek hata — `str(URL)`

Testler dört tur boyunca Furkan'ın makinesinde "password authentication failed"
veriyordu, `.env`'deki parola doğru olmasına rağmen.

Sebep: SQLAlchemy'de **`str(URL)` parolayı `***` ile değiştirir.**
`conftest.py`'deki `_with_test_database` test URL'lerini `str()` ile üretiyordu,
yani testler `postgres` kullanıcısına gerçek parolayla değil `***` dizgesiyle
bağlanmaya çalışıyordu. Hata mesajı doğru kimlik bilgilerini suçluyordu.

`check_db_setup.py` "her şey yolunda" diyordu çünkü o, `create_engine`'e URL
**nesnesi** veriyor — nesne gerçek parolayı taşır.

**Neden bu kadar geç bulundu:** bulut doğrulama ortamındaki PostgreSQL `trust`
kimlik doğrulamasıyla kuruluydu; orada hiçbir parola kontrol edilmiyor. Yani
bozuk parolayla altı test yeşil dönüyordu. Ortam `scram-sha-256`'ya çevrildi,
hata birebir yeniden üretildi, düzeltildi, ve bu oturumdaki **bütün**
doğrulamalar parola zorunlu ortamda tekrarlandı.

Kalıcı önlemler: `render_as_string(hide_password=False)` kullanılıyor; parolası
`***` olan bir test URL'si suite'i açık mesajla durduruyor; `CLAUDE.md`'ye
"Tuzaklar" bölümü eklendi; README'nin "Tests" bölümü bu hikâyeyi anlatıyor.

---

## Sıradaki adım — Faz 5 (canlıya alma)

1. **README'de tek TODO var:** "Live demo" satırı. Deploy sonrası gerçek URL ile
   değiştirilecek (`<!-- FAZ 5: ... -->` yorumuyla işaretli).
2. Backend: Railway / Render / Fly · Veritabanı: Neon veya Supabase.
3. Prod'da **iki rol** kurulacak: `alembic upgrade head` yönetici bağlantısıyla,
   sonra `python scripts/setup_db_role.py`, sonra `seed_demo.py`.
   Ortam değişkenleri: `DATABASE_URL` (kısıtlı rol), `MIGRATION_DATABASE_URL`,
   `SECRET_KEY` (yeni), `ACCESS_TOKEN_EXPIRE_MINUTES`.
4. `main.py` içindeki `origins` listesine prod frontend domaini eklenecek.
5. `python scripts/check_db_setup.py` prod'a karşı koşturulacak — deploy sonrası
   ilk kontrol o olmalı.

## Bilinen sınırlar
README'nin "Known limits" bölümünde: RLS yalnızca `tasks`'te · `users.email`
global UNIQUE · token iptali yok · hız sınırı süreç belleğinde · migration'lar
RLS'i baypas eder. Ayrıca `TaskUpdateDetail` içinde `assigned_to` alanı yok,
bu yüzden `update_task_detail`'deki `_validate_assignee` dalı ölü kod.
