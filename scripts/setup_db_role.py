"""
Creates the restricted database role the application connects as.

Run once per environment, AFTER `alembic upgrade head`. Safe to re-run.

    python scripts/setup_db_role.py

Why this script exists
----------------------
PostgreSQL superusers bypass Row-Level Security. Not "unless FORCE is set" —
always. A superuser connection reads every row of every tenant no matter what
policies say. So an application that connects as `postgres` and enables RLS has
policies that do nothing, tests that pass for the wrong reason, and a README
that lies.

The role created here is NOSUPERUSER and NOBYPASSRLS, and it does not own the
tables, so it also cannot turn the policies off. It can read and write rows and
nothing else.

Where the credentials come from
-------------------------------
The role name and password are read from DATABASE_URL — the URL the app itself
uses — so there is exactly one place to change them. The admin connection comes
from MIGRATION_DATABASE_URL.

    DATABASE_URL=postgresql://saas_app:<password>@localhost:5432/saas_project
    MIGRATION_DATABASE_URL=postgresql://postgres:<password>@localhost:5432/saas_project
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from core.config import settings  # noqa: E402

TABLOLAR = ("tenants", "users", "tasks")


def main() -> int:
    if not settings.migration_database_url:
        print(
            "MIGRATION_DATABASE_URL tanımlı değil.\n"
            "Rol oluşturmak için şema sahibi / yönetici bir bağlantı gerekiyor;\n"
            "uygulamanın kısıtlı rolü kendi kendine yetki veremez (vermemeli).",
            file=sys.stderr,
        )
        return 1

    app_url = make_url(settings.database_url)
    admin_url = make_url(settings.migration_database_url)

    rol = app_url.username
    parola = app_url.password
    veritabani = app_url.database

    if not rol or not parola:
        print("DATABASE_URL kullanıcı adı ve parola içermeli.", file=sys.stderr)
        return 1

    # Güvenlik freni: bu script'in amacı kısıtlı bir rol kurmak. Yönetici rolünün
    # adı verilmişse büyük ihtimalle .env yanlış doldurulmuştur.
    if rol == admin_url.username:
        print(
            f"DATABASE_URL ve MIGRATION_DATABASE_URL aynı rolü ('{rol}') kullanıyor.\n"
            "Uygulama ayrı, yetkisiz bir rolle bağlanmalı — aksi hâlde RLS'in bir anlamı yok.",
            file=sys.stderr,
        )
        return 1

    if admin_url.database != veritabani:
        print(
            f"İki URL farklı veritabanlarını gösteriyor: "
            f"'{admin_url.database}' ve '{veritabani}'.",
            file=sys.stderr,
        )
        return 1

    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        var_mi = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :rol"), {"rol": rol}
        ).scalar()

        # Rol adı ve parola kimlik bilgisidir, bağlanabilir parametre değil:
        # CREATE ROLE / GRANT bunları yer tutucu olarak kabul etmez. Bu yüzden
        # SQL'e gömüyoruz — ve gömmeden önce doğruluyoruz.
        if not rol.replace("_", "").isalnum():
            print(f"Rol adı beklenmedik karakterler içeriyor: {rol!r}", file=sys.stderr)
            return 1
        guvenli_parola = parola.replace("'", "''")

        if var_mi:
            conn.execute(text(f"ALTER ROLE {rol} WITH LOGIN PASSWORD '{guvenli_parola}'"))
            print(f"rol '{rol}' zaten vardı — parola .env ile eşitlendi")
        else:
            conn.execute(
                text(f"CREATE ROLE {rol} LOGIN PASSWORD '{guvenli_parola}'")
            )
            print(f"rol '{rol}' oluşturuldu")

        # Superuser ve BYPASSRLS'i her koşuda açıkça kapatıyoruz. Biri elle
        # yetki yükseltmişse bu script onu geri alır ve haber verir.
        conn.execute(text(f"ALTER ROLE {rol} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"))

        conn.execute(text(f'GRANT CONNECT ON DATABASE "{veritabani}" TO {rol}'))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {rol}"))
        for tablo in TABLOLAR:
            conn.execute(
                text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tablo} TO {rol}")
            )

        # İleride migration'la eklenecek tablolar da otomatik kapsansın.
        conn.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin_url.username} IN SCHEMA public "
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {rol}"
            )
        )

        # DDL yok: uygulama rolü şemayı değiştiremesin, politikayı kapatamasın.
        conn.execute(text(f"REVOKE CREATE ON SCHEMA public FROM {rol}"))

        satir = conn.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname = :rol"
            ),
            {"rol": rol},
        ).one()

    if any(satir):
        print(f"UYARI: '{rol}' hâlâ yükseltilmiş yetkiler taşıyor: {satir}", file=sys.stderr)
        return 1

    print(
        f"'{rol}' hazır: superuser değil, bypassrls değil, DDL yetkisi yok.\n"
        f"{', '.join(TABLOLAR)} tablolarında satır okuma/yazma yetkisi var."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
