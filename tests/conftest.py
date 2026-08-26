"""
Fixtures for the tenant-isolation suite.

These tests run against a REAL PostgreSQL database. SQLite is not an option:
the schema uses native UUID columns with `gen_random_uuid()` server defaults,
and the Row-Level Security policies that form the second isolation layer are a
PostgreSQL feature with no SQLite equivalent.

The schema is built by running the Alembic migrations, NOT by
`Base.metadata.create_all()`. That is deliberate. RLS policies live in
migrations, not in the SQLAlchemy models, so a model-built schema would quietly
omit them — and an isolation suite running against a schema without the
policies it is meant to prove is worse than no suite at all.

Point TEST_DATABASE_URL at a throwaway database:

    createdb saas_project_test
    TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/saas_project_test pytest

If TEST_DATABASE_URL is unset, one is derived by appending `_test` to
DATABASE_URL. The suite refuses to start if the two resolve to the same
database — every run drops and recreates the public schema.
"""

import os
import pathlib
import re
import sys
from dataclasses import dataclass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _from_env_file(key: str):
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        match = re.match(rf"^\s*{key}\s*=\s*(.+?)\s*$", line)
        if match:
            return match.group(1)
    return None


DEV_DATABASE_URL = os.getenv("DATABASE_URL") or _from_env_file("DATABASE_URL")
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if not TEST_DATABASE_URL:
    if not DEV_DATABASE_URL:
        raise RuntimeError(
            "Set TEST_DATABASE_URL (or DATABASE_URL) before running the suite."
        )
    TEST_DATABASE_URL = DEV_DATABASE_URL + "_test"

if TEST_DATABASE_URL == DEV_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL points at the development database. "
        "Refusing to run: every run drops and recreates the schema."
    )

# Must happen before any application module is imported — the app builds its
# engine from settings at import time, and pydantic-settings reads the
# environment before it reads .env.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.limiter import limiter  # noqa: E402
from database import engine  # noqa: E402
from main import app  # noqa: E402

API = "/api/v1"
PASSWORD = "Parola123"


@dataclass
class TenantFixture:
    """One registered company plus a logged-in admin's Authorization header."""

    name: str
    admin_email: str
    admin_id: str
    headers: dict


@pytest.fixture(scope="session", autouse=True)
def database_schema():
    """Rebuild the test schema once per run, from the migrations."""
    with engine.begin() as conn:
        # Requires the connecting role to own the schema. If your test role is
        # not the owner: GRANT ALL ON SCHEMA public TO <role>;
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.fixture(autouse=True)
def empty_tables():
    """Each test starts from an empty database — no ordering dependencies."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE tasks, users, tenants CASCADE"))
    yield


@pytest.fixture(autouse=True)
def rate_limiting_off():
    """
    Rate limiting is orthogonal to isolation and would only add flakiness here:
    `/login` and `/tenants/register` are capped per IP, and TestClient always
    presents the same one. Left on, the third test would fail with 429 without
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
