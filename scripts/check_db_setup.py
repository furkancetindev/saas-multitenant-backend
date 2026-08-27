"""
Preflight check for the two-role database setup.

Run this when `pytest` fails with a connection error, or before deploying to a
new environment:

    python scripts/check_db_setup.py

It answers, in order:
  1. Are both URLs present and parseable?
  2. Does each one actually connect — and over which address family?
  3. Is the application role genuinely unprivileged? (If not, RLS is decoration.)
  4. Are the policies in place on the tables that need them?
  5. Do the test databases exist?

Nothing here changes anything. It only reports.
"""

import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from dotenv import dotenv_values  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from core.config import settings  # noqa: E402

TAMAM = "  [OK]   "
HATA = "  [FAIL] "
NOT = "  [ .. ] "


def aciklama(hata: BaseException) -> str:
    """
    Bir istisnadan tek satırlık, okunabilir bir sebep çıkarır.

    Boş mesaj gelebiliyor: bir sunucu portu dinlemiyorsa psycopg2 bazen mesajsız
    OperationalError fırlatır. `splitlines()[-1]` o durumda IndexError verir —
    ve çöken bir teşhis aracı teşhis etmez.
    """
    metin = str(getattr(hata, "__cause__", None) or hata).strip()
    if not metin:
        return f"{type(hata).__name__} (mesaj yok — sunucu o adreste dinlemiyor olabilir)"
    return metin.splitlines()[-1]


def maskele(url) -> str:
    url = make_url(str(url))
    return str(url.set(password="***")) if url.password else str(url)


def baglan(url, etiket):
    """Bağlanmayı dener; başarılıysa (True, sunucu adresi) döner."""
    try:
        motor = create_engine(url, connect_args={"connect_timeout": 5})
        with motor.connect() as conn:
            adres = conn.execute(text("SELECT inet_server_addr()")).scalar()
            kullanici = conn.execute(text("SELECT current_user")).scalar()
        motor.dispose()
        print(f"{TAMAM}{etiket}: bağlandı  (rol={kullanici}, sunucu={adres})")
        return True
    except Exception as hata:
        print(f"{HATA}{etiket}: {aciklama(hata)}")
        return False


def adres_ailesi_karsilastir(url, etiket):
    """
    localhost çözümlemesi IPv6'ya giderse pg_hba farklı davranabilir.

    Not: buraya gelen url bir dizgeyse parolası korunmuş olmalı.
    `str(URL)` parolayı `***` yapar ve o dizge bağlanmaya çalışırsa
    "password authentication failed" alırsın — doğru parolayla.
    """
    temel = make_url(url)
    if temel.host not in ("localhost",):
        return
    print(f"{NOT}{etiket}: host 'localhost' — IPv4/IPv6 ayrı ayrı deneniyor")
    for host, ad in (("127.0.0.1", "IPv4 127.0.0.1"), ("::1", "IPv6 ::1")):
        baglan(temel.set(host=host), f"    {ad}")


def main() -> int:
    sorun = 0

    print("\n=== 0. .env dosyası ===")
    env_yolu = Path(__file__).resolve().parent.parent / ".env"
    env_dosyasi = dotenv_values(env_yolu) if env_yolu.exists() else {}
    if not env_yolu.exists():
        print(f"{NOT}.env yok — ayarlar ortam değişkenlerinden geliyor olmalı")
    else:
        sayac = {}
        for satir in env_yolu.read_text(encoding="utf-8").splitlines():
            eslesme = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", satir)
            if eslesme:
                sayac[eslesme.group(1)] = sayac.get(eslesme.group(1), 0) + 1
        yinelenen = sorted(k for k, n in sayac.items() if n > 1)
        if yinelenen:
            print(f"{HATA}şu anahtarlar birden fazla kez tanımlı: {', '.join(yinelenen)}")
            print(f"{NOT}sessizce SONUNCUSU kazanır — dosya bir şey söyleyip başka bir şey demiş olur")
            sorun += 1
        else:
            print(f"{TAMAM}{len(sayac)} anahtar, yinelenen yok")

    print("\n=== 1. Yapılandırma ===")
    app_url = settings.database_url
    admin_url = settings.migration_database_url
    print(f"{TAMAM}DATABASE_URL           = {maskele(app_url)}")
    if admin_url:
        print(f"{TAMAM}MIGRATION_DATABASE_URL = {maskele(admin_url)}")
    else:
        print(f"{NOT}MIGRATION_DATABASE_URL tanımsız — tek rollü kurulum")

    if admin_url and make_url(app_url).username == make_url(admin_url).username:
        print(f"{HATA}İki URL aynı rolü kullanıyor — RLS'in bir anlamı kalmaz")
        sorun += 1

    print("\n=== 2. Bağlantılar ===")
    if not baglan(app_url, "uygulama rolü / dev"):
        sorun += 1
        adres_ailesi_karsilastir(app_url, "uygulama rolü / dev")
    if admin_url:
        if not baglan(admin_url, "yönetici rolü / dev"):
            sorun += 1
            adres_ailesi_karsilastir(admin_url, "yönetici rolü / dev")

    print("\n=== 3. Uygulama rolünün yetkileri ===")
    try:
        motor = create_engine(app_url, connect_args={"connect_timeout": 5})
        with motor.connect() as conn:
            rol, superuser, bypassrls = conn.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).one()
            if superuser:
                print(f"{HATA}{rol} SUPERUSER — RLS politikaları hiç uygulanmaz")
                sorun += 1
            elif bypassrls:
                print(f"{HATA}{rol} BYPASSRLS taşıyor — RLS politikaları atlanır")
                sorun += 1
            else:
                print(f"{TAMAM}{rol}: superuser değil, bypassrls değil")

            print("\n=== 4. Row-Level Security ===")
            for tablo in ("tasks",):
                satir = conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity "
                        "FROM pg_class WHERE relname = :t"
                    ),
                    {"t": tablo},
                ).first()
                if not satir:
                    print(f"{HATA}{tablo} tablosu yok — migration çalıştı mı?")
                    sorun += 1
                    continue
                acik, zorunlu = satir
                politikalar = (
                    conn.execute(
                        text("SELECT policyname FROM pg_policies WHERE tablename = :t"),
                        {"t": tablo},
                    )
                    .scalars()
                    .all()
                )
                if acik and zorunlu and politikalar:
                    print(f"{TAMAM}{tablo}: RLS açık + FORCE, politikalar: {politikalar}")
                else:
                    print(
                        f"{HATA}{tablo}: enabled={acik} forced={zorunlu} "
                        f"politikalar={politikalar}"
                    )
                    sorun += 1

            # Bağlam yokken sıfır satır dönmeli — fail-closed davranışı.
            sayi = conn.execute(text("SELECT count(*) FROM tasks")).scalar()
            if sayi == 0:
                print(f"{TAMAM}kiracı bağlamı yokken tasks: 0 satır (fail-closed)")
            else:
                print(f"{HATA}kiracı bağlamı yokken tasks: {sayi} satır — politika çalışmıyor")
                sorun += 1
        motor.dispose()
    except Exception as hata:
        print(f"{HATA}uygulama rolüyle kontrol yapılamadı: {aciklama(hata)}")
        sorun += 1

    print("\n=== 5. Test veritabanları ===")
    # tests/conftest.py ile AYNI öncelik sırası: açık bir TEST_* geçersiz kılması
    # varsa o kazanır, yoksa veritabanı adına "_test" eklenir. Burada farklı
    # davranmak, iki aracın farklı veritabanlarını kontrol etmesi demek olurdu —
    # ve o farkı kimse fark etmezdi.
    for etiket, url, gecersiz_kilma in (
        ("uygulama", app_url, "TEST_DATABASE_URL"),
        ("yönetici", admin_url, "TEST_MIGRATION_DATABASE_URL"),
    ):
        if not url:
            continue
        acik = os.environ.get(gecersiz_kilma) or env_dosyasi.get(gecersiz_kilma)
        if acik:
            print(f"{NOT}{etiket}: {gecersiz_kilma} tanımlı — türetme yerine o kullanılıyor")
            test_url = make_url(acik)
        else:
            test_url = make_url(url)
            test_url = test_url.set(database=f"{test_url.database}_test")
        if not baglan(test_url, f"{etiket} rolü / test"):
            sorun += 1
            adres_ailesi_karsilastir(test_url.render_as_string(hide_password=False), f"{etiket} rolü / test")

    print("\n=== 6. Aynı değeri okuyan yollar aynı sonucu veriyor mu ===")
    # Uygulama ve testler ayarları farklı yollardan alıyor:
    #   pydantic-settings  -> ortam değişkeni, yoksa .env
    #   dotenv_values      -> yalnızca .env
    #   os.environ         -> yalnızca ortam
    # Üçü aynı değeri vermelidir. Vermiyorsa, uygulama bir veritabanına,
    # testler başkasına bağlanır — ve hata mesajı bunu söylemez.
    # Parolalar yazdırılmaz; yalnızca uzunluk ve parmak izi karşılaştırılır.
    def parmak_izi(deger):
        if deger is None:
            return "yok"
        ozet = hashlib.sha256(deger.encode("utf-8")).hexdigest()[:8]
        return f"uzunluk={len(deger)} parmak_izi={ozet}"

    for anahtar, ayar_degeri in (
        ("DATABASE_URL", settings.database_url),
        ("MIGRATION_DATABASE_URL", settings.migration_database_url),
        ("TEST_DATABASE_URL", None),
        ("TEST_MIGRATION_DATABASE_URL", None),
    ):
        if ayar_degeri is None and anahtar.startswith("TEST_"):
            deger = os.environ.get(anahtar) or env_dosyasi.get(anahtar)
            if deger:
                print(f"{NOT}{anahtar} tanımlı — testler bunu kullanır, uygulama görmez")
            continue
        kaynaklar = {
            "pydantic (uygulama)": ayar_degeri,
            "dotenv (.env)": env_dosyasi.get(anahtar),
            "os.environ": os.environ.get(anahtar),
        }
        benzersiz = {v for v in kaynaklar.values() if v is not None}
        if len(benzersiz) <= 1:
            print(f"{TAMAM}{anahtar}: tüm kaynaklar aynı  ({parmak_izi(ayar_degeri)})")
        else:
            print(f"{HATA}{anahtar}: KAYNAKLAR ÇELİŞİYOR")
            for ad, deger in kaynaklar.items():
                print(f"           {ad:22s} {parmak_izi(deger)}")
            sorun += 1

    print()
    if sorun:
        print(f"{sorun} sorun bulundu.")
    else:
        print("Her şey yolunda.")
    return 1 if sorun else 0


if __name__ == "__main__":
    raise SystemExit(main())
