"""
Tenant isolation — the guarantee this codebase exists to make.

Two companies live in the same database, in the same tables, separated by
nothing but a `tenant_id` column. These tests ask the only question that
matters: can one company reach the other's rows?

The contract under test is **404, never 403**. A 403 would confirm the record
exists and merely belongs to somebody else — an ID enumeration oracle. A 404
says nothing at all, and says exactly the same thing as a row that was never
there. The last test in this file proves those two answers are byte-identical.

Isolation is enforced twice. The repository layer filters every query by
`tenant_id`, and PostgreSQL Row-Level Security enforces the same rule inside the
database, so a query that forgets the filter returns nothing rather than
everything. These tests were written against the filters alone and passed; they
still pass with the filters deleted, because the second layer catches it. That
experiment is the point of the last test in this file, and it is written up in
the README under "Isolation model".
"""

from uuid import uuid4

from sqlalchemy import text

from database import engine as app_engine

API = "/api/v1"


def test_task_is_invisible_to_another_tenant(api, kuzey, ay):
    """Ay Yapı cannot see, read, change or delete a Kuzey Lojistik task."""
    created = api.post(
        f"{API}/tasks/",
        headers=kuzey.headers,
        json={"title": "Ankara shipment", "description": "14 pallets"},
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]

    # The listing endpoint simply does not contain it.
    listing = api.get(f"{API}/tasks/", headers=ay.headers)
    assert listing.status_code == 200
    assert listing.json() == []

    # Knowing the exact ID does not help either. Every verb, one answer.
    assert api.get(f"{API}/tasks/{task_id}", headers=ay.headers).status_code == 404
    assert api.patch(
        f"{API}/tasks/{task_id}/status", headers=ay.headers, json={"status": "done"}
    ).status_code == 404
    assert api.put(
        f"{API}/tasks/{task_id}", headers=ay.headers, json={"title": "hijacked"}
    ).status_code == 404
    assert api.delete(f"{API}/tasks/{task_id}", headers=ay.headers).status_code == 404

    # Those 404s were refusals, not silent successes: the task is untouched.
    survivor = api.get(f"{API}/tasks/{task_id}", headers=kuzey.headers)
    assert survivor.status_code == 200
    assert survivor.json()["title"] == "Ankara shipment"


def test_employees_are_invisible_to_another_tenant(api, kuzey, ay):
    """Neither company's employee list leaks into the other's."""
    kuzey_people = api.get(f"{API}/users/", headers=kuzey.headers)
    assert kuzey_people.status_code == 200
    assert {person["email"] for person in kuzey_people.json()} == {
        "admin@kuzey.example.com",
        "calisan@kuzey.example.com",
    }

    ay_people = api.get(f"{API}/users/", headers=ay.headers)
    assert ay_people.status_code == 200
    assert {person["email"] for person in ay_people.json()} == {
        "admin@ayyapi.example.com"
    }

    # Not just the parsed list — no Kuzey address appears anywhere in the body.
    assert "kuzey.example.com" not in ay_people.text


def test_cross_tenant_assignment_is_rejected(api, kuzey, ay):
    """A task cannot be assigned to someone who works at the other company."""
    ay_admin_id = api.get(f"{API}/users/", headers=ay.headers).json()[0]["id"]

    rejected = api.post(
        f"{API}/tasks/",
        headers=kuzey.headers,
        json={"title": "assign across the fence", "assigned_to": ay_admin_id},
    )
    assert rejected.status_code == 400, rejected.text

    # ...while assignment inside the same company still works. The check
    # rejects the tenant boundary, not the feature.
    kuzey_employee_id = next(
        person["id"]
        for person in api.get(f"{API}/users/", headers=kuzey.headers).json()
        if person["email"] == "calisan@kuzey.example.com"
    )
    accepted = api.post(
        f"{API}/tasks/",
        headers=kuzey.headers,
        json={"title": "assign inside the fence", "assigned_to": kuzey_employee_id},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["assigned_to"] == kuzey_employee_id


def test_foreign_task_is_indistinguishable_from_a_missing_one(api, kuzey, ay):
    """
    The error contract, stated as an equality.

    A task that belongs to another tenant and a task that never existed must
    produce the same status code and the same body. Anything else — a 403, a
    different message, a different shape — turns the endpoint into an oracle
    that answers "does this ID exist?" for the whole platform.
    """
    created = api.post(
        f"{API}/tasks/", headers=kuzey.headers, json={"title": "Ankara shipment"}
    )
    assert created.status_code == 200, created.text

    belongs_to_kuzey = api.get(f"{API}/tasks/{created.json()['id']}", headers=ay.headers)
    never_existed = api.get(f"{API}/tasks/{uuid4()}", headers=ay.headers)

    assert belongs_to_kuzey.status_code == never_existed.status_code == 404
    assert belongs_to_kuzey.json() == never_existed.json()


def test_row_level_security_is_actually_enforced(api, kuzey):
    """
    The meta-test: proof that the tests above are testing something.

    Row-Level Security is bypassed completely by superusers, and — unless the
    table is FORCEd — by the table's owner. An application that connects to
    PostgreSQL as `postgres` can carry every policy in this repository and still
    hand one tenant's rows to another, with a fully green test suite, because
    the tests would run through the same bypassing connection.

    So this test asserts three things about the connection the application
    actually uses: that it is not privileged enough to bypass the policy, that
    the policy exists, and that it filters.
    """
    created = api.post(
        f"{API}/tasks/", headers=kuzey.headers, json={"title": "Ankara shipment"}
    )
    assert created.status_code == 200, created.text
    kuzey_tenant_id = created.json()["tenant_id"]

    # app_engine is the engine the running application uses — not a test fixture.
    with app_engine.connect() as conn:
        role, is_superuser, bypasses_rls = conn.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        assert not is_superuser, f"{role} is a superuser — RLS never applies to it"
        assert not bypasses_rls, f"{role} has BYPASSRLS — RLS never applies to it"

        enabled, forced = conn.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relname = 'tasks'"
            )
        ).one()
        assert enabled, "row level security is not enabled on tasks"
        assert forced, "row level security is not FORCEd on tasks"

        policies = (
            conn.execute(
                text("SELECT policyname FROM pg_policies WHERE tablename = 'tasks'")
            )
            .scalars()
            .all()
        )
        assert "tenant_isolation" in policies

        # Fail-closed. This connection has no tenant context, so the policy
        # compares tenant_id against NULL and matches nothing. A forgotten
        # context returns an empty result, never somebody else's rows.
        assert conn.execute(text("SELECT count(*) FROM tasks")).scalar() == 0

        # With the context a real request would have set, the row is there —
        # so the zero above was the policy filtering, not an empty table.
        conn.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": kuzey_tenant_id},
        )
        assert conn.execute(text("SELECT count(*) FROM tasks")).scalar() == 1


def test_tenant_context_does_not_survive_the_request_that_set_it(api, kuzey):
    """
    The connection pool is where naive RLS implementations leak.

    `SET app.tenant_id = '...'` applies to the whole database session, so it
    outlives the request that set it. The connection goes back to the pool
    still carrying one company's identity, and the next code path to borrow it
    without setting its own — a background job, a health check, a query someone
    adds next year — reads as that company. The fix this codebase exists to
    demonstrate would have reintroduced the exact leak it prevents.

    `set_config(..., true)` scopes the value to the transaction, so it is gone
    the moment the transaction ends. This test makes a real authenticated
    request, then borrows connections back out of the same pool and asserts
    none of them still knows who Kuzey Lojistik is.

    Swap that `true` for `false` in database.py and this test goes red.
    """
    created = api.post(
        f"{API}/tasks/", headers=kuzey.headers, json={"title": "Ankara shipment"}
    )
    assert created.status_code == 200, created.text

    for attempt in range(15):
        with app_engine.connect() as conn:
            leftover = conn.execute(
                text("SELECT current_setting('app.tenant_id', true)")
            ).scalar()
            assert not leftover, (
                f"attempt {attempt}: a pooled connection came back still carrying "
                f"tenant {leftover!r} — the setting outlived its request"
            )
            # And the practical consequence: with no context, no rows. Not the
            # previous tenant's rows.
            assert conn.execute(text("SELECT count(*) FROM tasks")).scalar() == 0
