"""
Tenant isolation — the guarantee this codebase exists to make.

Two companies live in the same database, in the same tables, separated by
nothing but a `tenant_id` column. These tests ask the only question that
matters: can one company reach the other's rows?

The contract under test is **404, never 403**. A 403 would confirm the record
exists and merely belongs to somebody else — an ID enumeration oracle. A 404
says nothing at all, and says exactly the same thing as a row that was never
there. The last test in this file proves those two answers are byte-identical.

These tests were written against the hand-written `tenant_id` filters in the
repository layer, and they passed. Phase 3 puts PostgreSQL Row-Level Security
underneath those filters. The proof that the second layer is real is that this
file keeps passing, unchanged, when the filters are temporarily removed — the
database refuses the rows on its own. See README, "Isolation model".
"""

from uuid import uuid4

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
