"""
Fixtures for the tenant-isolation suite.

These tests run against a REAL PostgreSQL database. SQLite is not an option:
the schema uses native UUID columns with `gen_random_uuid()` server defaults,
and the Row-Level Security policies that form the second isolation layer are a
PostgreSQL feature with no SQLite equivalent.

Two connections, on purpose
---------------------------
The application connects as a restricted role that owns nothing and cannot run
DDL. The test harness connects as the admin role to build and reset the schema.
If both used the same role the suite would still be green — and would prove
nothing, because a superuser bypasses every RLS policy no matter what the
policy says. `test_row_level_security_is_actually_enforced` guards that.

The schema is built by running the Alembic migrations, NOT by
`Base.metadata.create_all()`. RLS policies live in migrations, not in the
SQLAlchemy models; a model-built schema would quietly omit them.

Configuration
-------------
Derived from .env unless overridden:

    DATABASE_URL            -> app role, dev database
    MIGRATION_DATABASE_URL  -> admin role, dev database

The test databases are the same URLs with `_test` appended to the database
name, created automatically on first run. Override with TEST_DATABASE_URL and
TEST_MIGRATION_DATABASE_URL. The suite refuses to start if a test URL resolves
to its development counterpart — every run drops and recreates the schema.
"""

import importlib.util
import os
import pathlib
import re
import sys
from dataclasses import dataclass

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


ENV_PATH = PROJECT_ROOT / ".env"

# Deliberately the same parser pydantic-settings uses, rather than a regex of
# our own. A hand-rolled .env reader and python-dotenv disagree on real files —
# on a duplicated key one returns the first value and the other the last — and
# then the tests connect somewhere the application never would. One parser,
# one answer.
ENV_FILE = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}


def _duplicate_keys():
    """Keys defined more than once in .env. The last one silently wins."""
    if not ENV_PATH.exists():
        return []
    counts = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return sorted(key for key, count in counts.items() if count > 1)


def _with_test_database(url_string: str) -> str:
    """
    The same server, with `_test` appended to the database name.

    `render_as_string(hide_password=False)` is not a detail. `str(URL)` — and
    with it every f-string and `.format()` — renders the password as `***`.
    That is a sensible default for a log line and a silent disaster for a
    connection string: the result still parses, still names the right database,
    still looks correct in any output that prints it, and authenticates with
    the literal password `***`. The failure appears much later, as
    "password authentication failed", accusing credentials that are fine.
    """
    url = make_url(url_string)
    return url.set(database=f"{url.database}_test").render_as_string(
        hide_password=False
    )


_yinelenen = _duplicate_keys()
if _yinelenen:
    raise RuntimeError(
        f".env defines these keys more than once: {', '.join(_yinelenen)}.\n"
        "The last definition silently wins, so the file says one thing and means "
        "another — and a test suite reading it a different way connects somewhere "
        "the application never would. Delete the extra lines and re-run."
    )

DEV_APP_URL = os.getenv("DATABASE_URL") or ENV_FILE.get("DATABASE_URL")
DEV_ADMIN_URL = os.getenv("MIGRATION_DATABASE_URL") or ENV_FILE.get(
    "MIGRATION_DATABASE_URL"
)

if not DEV_APP_URL or not DEV_ADMIN_URL:
    raise RuntimeError(
        "DATABASE_URL and MIGRATION_DATABASE_URL must both be set "
        "(in .env or the environment). See .env.example."
    )

TEST_APP_URL = os.getenv("TEST_DATABASE_URL") or _with_test_database(DEV_APP_URL)
TEST_ADMIN_URL = os.getenv("TEST_MIGRATION_DATABASE_URL") or _with_test_database(
    DEV_ADMIN_URL
)

for test_url, dev_url, label in (
    (TEST_APP_URL, DEV_APP_URL, "TEST_DATABASE_URL"),
    (TEST_ADMIN_URL, DEV_ADMIN_URL, "TEST_MIGRATION_DATABASE_URL"),
):
    if test_url == dev_url:
        raise RuntimeError(
            f"{label} points at the development database. "
            "Refusing to run: every run drops and recreates the schema."
        )

for _etiket, _url in (("TEST app", TEST_APP_URL), ("TEST admin", TEST_ADMIN_URL)):
    if make_url(_url).password == "***":
        raise RuntimeError(
            f"{_etiket} URL carries the literal password '***'. Something "
            "rendered it with str(URL) instead of "
            "render_as_string(hide_password=False), and the masked form was "
            "used as a real credential."
        )

if make_url(TEST_APP_URL).username == make_url(TEST_ADMIN_URL).username:
    raise RuntimeError(
        "The application and admin roles are the same. This suite would pass "
        "for the wrong reason: an owning or superuser role bypasses RLS."
    )

# Must happen before any application module is imported — the app builds its
# engine from settings at import time, and pydantic-settings reads the
# environment before it reads .env.
os.environ["DATABASE_URL"] = TEST_APP_URL
os.environ["MIGRATION_DATABASE_URL"] = TEST_ADMIN_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from core.limiter import limiter  # noqa: E402
from database import engine as app_engine  # noqa: E402
from main import app  # noqa: E402

API = "/api/v1"
PASSWORD = "Parola123"

admin_engine = create_engine(TEST_ADMIN_URL, isolation_level="AUTOCOMMIT")


@dataclass
class TenantFixture:
    """One registered company plus a logged-in admin's Authorization header."""

    name: str
    admin_email: str
    admin_id: str
    headers: dict


def _maskeli(url) -> str:
    url = make_url(str(url))
    return str(url.set(password="***")) if url.password else str(url)


def _create_test_database_if_missing():
    """
    Create the test database, but only if it is actually missing.

    The cheapest check is to connect to it. Doing that first means the common
    case never touches the `postgres` maintenance database — a different
    database, therefore a different pg_hba.conf rule, therefore a connection
    that can fail for reasons that have nothing to do with this project.

    Only a genuinely missing database falls through to creation. Every other
    failure — a refused password, a server that is not running — is re-raised
    as it happened. Swallowing it here and reporting "the database is missing"
    instead would replace a precise error with a misleading one, and send
    whoever reads it looking in the wrong place.
    """
    try:
        with admin_engine.connect():
            return
    except OperationalError as hata:
        eksik = "does not exist" in str(getattr(hata, "orig", hata))
        if not eksik:
            raise RuntimeError(
                f"Could not connect to the test database as the admin role.\n"
                f"    URL: {_maskeli(TEST_ADMIN_URL)}\n"
                f"This is not a missing database — the server answered and "
                f"refused. Check the credentials in .env, and compare with "
                f"`python scripts/check_db_setup.py`.\n\n"
                f"Underlying error: {hata}"
            ) from hata

    url = make_url(TEST_ADMIN_URL)
    server = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as hata:
        raise RuntimeError(
            f"Test database '{url.database}' does not exist, and it could not be "
            f"created automatically: connecting to the 'postgres' maintenance "
            f"database failed.\n\nCreate it by hand and re-run:\n"
            f"    CREATE DATABASE {url.database};\n\n"
            f"Underlying error: {hata}"
        ) from hata
    finally:
        server.dispose()


def _grant_privileges_to_app_role():
    """Run the same script the README tells operators to run — one definition."""
    spec = importlib.util.spec_from_file_location(
        "setup_db_role", PROJECT_ROOT / "scripts" / "setup_db_role.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0, "scripts/setup_db_role.py failed"


@pytest.fixture(scope="session", autouse=True)
def database_schema():
    """Rebuild the test schema once per run, from the migrations."""
    # Printed so that a failure here can be compared, line for line, with what
    # `python scripts/check_db_setup.py` reports. When the two disagree, the
    # disagreement itself is the bug.
    print(f"\n  test app   : {_maskeli(TEST_APP_URL)}")
    print(f"  test admin : {_maskeli(TEST_ADMIN_URL)}")
    _create_test_database_if_missing()

    with admin_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_ADMIN_URL.replace("%", "%%"))
    command.upgrade(alembic_cfg, "head")

    # After DROP SCHEMA the app role owns no grants at all — re-apply them.
    _grant_privileges_to_app_role()

    yield
    app_engine.dispose()


@pytest.fixture(autouse=True)
def empty_tables(database_schema):
    """
    Each test starts from an empty database — no ordering dependencies.

    Truncation runs on the admin connection: the app role deliberately has no
    TRUNCATE privilege, and test plumbing should not need the privileges the
    code under test is denied.
    """
    with admin_engine.connect() as conn:
        conn.execute(text("TRUNCATE tasks, users, tenants CASCADE"))
    yield


@pytest.fixture(autouse=True)
def rate_limiting_off():
    """
    Rate limiting is orthogonal to isolation and would only add flakiness here:
    `/login` and `/tenants/register` are capped per IP, and TestClient always
    presents the same one. Left on, later tests would fail with 429 without
    telling us anything about tenants.
    """
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture
def api():
    with TestClient(app) as client:
        yield client


def _register_and_login(api, company_name, admin_full_name, admin_email):
    registered = api.post(
        f"{API}/tenants/register",
        json={
            "company_name": company_name,
            "admin_full_name": admin_full_name,
            "admin_email": admin_email,
            "admin_password": PASSWORD,
        },
    )
    assert registered.status_code == 200, registered.text

    logged_in = api.post(
        f"{API}/login", data={"username": admin_email, "password": PASSWORD}
    )
    assert logged_in.status_code == 200, logged_in.text

    headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}
    me = api.get(f"{API}/me", headers=headers)
    assert me.status_code == 200, me.text

    return TenantFixture(
        name=company_name,
        admin_email=admin_email,
        admin_id=me.json()["id"],
        headers=headers,
    )


@pytest.fixture
def kuzey(api):
    """Kuzey Lojistik — a logistics company, with one admin and one employee."""
    tenant = _register_and_login(
        api, "Kuzey Lojistik", "Kuzey Admin", "admin@kuzey.example.com"
    )
    hired = api.post(
        f"{API}/users/",
        headers=tenant.headers,
        json={
            "full_name": "Kuzey Çalışan",
            "email": "calisan@kuzey.example.com",
            "role": "user",
            "password": PASSWORD,
        },
    )
    assert hired.status_code == 200, hired.text
    return tenant


@pytest.fixture
def ay(api):
    """Ay Yapı — a construction company. Same database, same tables, other rows."""
    return _register_and_login(
        api, "Ay Yapı", "Ay Admin", "admin@ayyapi.example.com"
    )
