"""
Loads the two demo companies the README's "Try it yourself" section refers to.

    python scripts/seed_demo.py            # refuses if data already exists
    python scripts/seed_demo.py --reset    # wipes the three tables first

The IDs are fixed, not generated. A reader following the README needs a task ID
they can paste into a request and get a 404 from; a random UUID would mean the
README could only gesture at the demo instead of handing it over.

Two connections, deliberately:

  * The reset runs as the admin role. The application role has no TRUNCATE
    privilege, and giving it one so a script could be shorter would weaken the
    thing this repository exists to demonstrate.

  * The seeding itself runs as the ordinary application role, through the same
    session machinery a request uses — including setting `app.tenant_id` before
    touching `tasks`. Row-Level Security applies to this script exactly as it
    applies to the API. If the tenant context were wrong here, the inserts
    would be refused rather than silently landing in the wrong company.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from core.config import settings  # noqa: E402
from core.security import get_password_hash  # noqa: E402
from database import SessionLocal  # noqa: E402
from models.domain import Task, Tenant, User  # noqa: E402

PASSWORD = "Parola123"

KUZEY_ID = "11111111-1111-1111-1111-111111111111"
AY_ID = "22222222-2222-2222-2222-222222222222"

KUZEY_ADMIN_ID = "11111111-0000-0000-0000-000000000001"
KUZEY_STAFF_ID = "11111111-0000-0000-0000-000000000002"
AY_ADMIN_ID = "22222222-0000-0000-0000-000000000001"

# The README quotes this one. Changing it means changing the README.
KUZEY_FIRST_TASK_ID = "aaaa0000-0000-0000-0000-000000000001"

DEMO = [
    {
        "tenant_id": KUZEY_ID,
        "name": "Kuzey Lojistik",
        "users": [
            (KUZEY_ADMIN_ID, "Kuzey Admin", "admin@kuzey.example.com", "admin"),
            (KUZEY_STAFF_ID, "Kuzey Çalışan", "calisan@kuzey.example.com", "user"),
        ],
        "tasks": [
            (KUZEY_FIRST_TASK_ID, "Ankara sevkiyatı", "14 palet, soğuk zincir", "in_progress", KUZEY_STAFF_ID),
            ("aaaa0000-0000-0000-0000-000000000002", "Gümrük evrakları", "2317 numaralı konteyner", "todo", KUZEY_STAFF_ID),
            ("aaaa0000-0000-0000-0000-000000000003", "İzmir depo sayımı", "Çeyrek sonu envanter", "done", None),
            ("aaaa0000-0000-0000-0000-000000000004", "Sürücü vardiya planı", "Eylül dönemi", "todo", None),
            ("aaaa0000-0000-0000-0000-000000000005", "Araç bakım randevusu", "34 ABC 123 — 90.000 km", "todo", None),
        ],
    },
    {
        "tenant_id": AY_ID,
        "name": "Ay Yapı",
        "users": [
            (AY_ADMIN_ID, "Ay Admin", "admin@ayyapi.example.com", "admin"),
        ],
        "tasks": [
            ("bbbb0000-0000-0000-0000-000000000001", "Beton döküm planı", "B blok, 3. kat", "in_progress", AY_ADMIN_ID),
            ("bbbb0000-0000-0000-0000-000000000002", "İskele güvenlik denetimi", "Aylık kontrol", "todo", None),
            ("bbbb0000-0000-0000-0000-000000000003", "Elektrik projesi revizyonu", "Zemin kat değişikliği", "done", None),
            ("bbbb0000-0000-0000-0000-000000000004", "Hafriyat ruhsatı yenileme", "Belediye başvurusu", "todo", None),
        ],
    },
]


def _reset():
    if not settings.migration_database_url:
        print(
            "--reset needs MIGRATION_DATABASE_URL: the application role has no "
            "TRUNCATE privilege, and it should not have one.",
            file=sys.stderr,
        )
        return False
    engine = create_engine(settings.migration_database_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE tasks, users, tenants CASCADE"))
    engine.dispose()
    print("mevcut veri silindi")
    return True


def _set_tenant(db, tenant_id: str):
    """
    Tells the database which company the following writes belong to.

    The same two steps `get_tenant_db` performs on every authenticated request:
    remember it on the session so the after_begin listener re-applies it to each
    new transaction, and apply it to the transaction already open.
    """
    db.info["tenant_id"] = tenant_id
    db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def main() -> int:
    reset = "--reset" in sys.argv

    db = SessionLocal()
    try:
        if db.query(Tenant).first() is not None:
            if not reset:
                print(
                    "Veritabanında zaten kayıt var. Üzerine yazmıyorum.\n"
                    "Silip yeniden yüklemek için: python scripts/seed_demo.py --reset",
                    file=sys.stderr,
                )
                return 1
            db.close()
            if not _reset():
                return 1
            db = SessionLocal()

        hashed = get_password_hash(PASSWORD)

        for company in DEMO:
            db.add(Tenant(id=company["tenant_id"], name=company["name"]))
            for user_id, full_name, email, role in company["users"]:
                db.add(
                    User(
                        id=user_id,
                        tenant_id=company["tenant_id"],
                        full_name=full_name,
                        email=email,
                        hashed_password=hashed,
                        role=role,
                        is_active=True,
                    )
                )
            db.flush()

            # Tasks are behind a row-level security policy: without the tenant
            # context these inserts are refused, not misfiled.
            _set_tenant(db, company["tenant_id"])
            for task_id, title, description, status, assigned_to in company["tasks"]:
                db.add(
                    Task(
                        id=task_id,
                        tenant_id=company["tenant_id"],
                        title=title,
                        description=description,
                        status=status,
                        assigned_to=assigned_to,
                    )
                )
            db.commit()
            print(f"{company['name']}: {len(company['users'])} kullanıcı, {len(company['tasks'])} görev")
    finally:
        db.close()

    print(
        "\nDemo hesapları (şifre hepsinde: %s)\n"
        "  admin@kuzey.example.com     Kuzey Lojistik — admin\n"
        "  calisan@kuzey.example.com   Kuzey Lojistik — çalışan\n"
        "  admin@ayyapi.example.com    Ay Yapı — admin\n"
        "\nREADME'nin 'Try it yourself' bölümündeki görev kimliği:\n"
        "  %s  (Kuzey Lojistik'e ait)" % (PASSWORD, KUZEY_FIRST_TASK_ID)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
