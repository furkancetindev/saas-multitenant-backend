# Multi-tenant SaaS backend — a reference implementation

A small B2B task-tracking API where two companies share one database, one
schema, and one set of tables, separated by a `tenant_id` column and nothing
else. FastAPI, PostgreSQL, SQLAlchemy, Alembic.

The application is not the point. The isolation is. Turning a single-tenant
application into a safely multi-tenant one is a specific job with specific ways
to get it quietly wrong, and this repository exists to show that job done and,
more importantly, **proved** — not asserted in a README, demonstrated by
deleting the protection and watching the tests stay green.

If you have twenty seconds, read
[`tests/test_tenant_isolation.py`](tests/test_tenant_isolation.py). If you have
sixty, run the two commands under *Try it yourself*.

---

## The claim, and how to check it

Isolation is enforced twice: every repository query filters on `tenant_id`, and
PostgreSQL Row-Level Security enforces the same rule inside the database. The
second layer exists because the first one depends on a person remembering.

That claim is cheap to make, so here is what happens when it is attacked.
Each row is an experiment you can run yourself — the command is in the right
column.

| Break this | Suite says | Because |
|---|---|---|
| Delete **every** `tenant_id` filter in `repositories/task_repository.py` | `6 passed` | The database refuses the rows on its own |
| Change `set_config(..., true)` to `false` in `database.py` — i.e. plain `SET` | `2 failed` | The tenant context outlives its request and leaks through the connection pool |
| Point `DATABASE_URL` at a superuser | suite refuses to start | A superuser bypasses every policy; a green run would mean nothing |

The first row is the one that matters. Comment the filters out, run `pytest`,
and watch it pass. That is what "the database enforces it" means, stated as an
experiment rather than a promise.

---

## Try it yourself

Two companies exist in the demo data: **Kuzey Lojistik** (logistics) and
**Ay Yapı** (construction). Same tables, same rows, different tenants.

Task `aaaa0000-0000-0000-0000-000000000001` — "Ankara sevkiyatı" — belongs to
Kuzey Lojistik.

```bash
# Log in as Kuzey Lojistik's admin
curl -s -X POST http://localhost:8000/api/v1/login \
  -d "username=admin@kuzey.example.com&password=Parola123"

# Their own task: 200, with the task in the body
curl -s http://localhost:8000/api/v1/tasks/aaaa0000-0000-0000-0000-000000000001 \
  -H "Authorization: Bearer <kuzey-token>"

# Now log in as Ay Yapı's admin and ask for the same ID
curl -s -X POST http://localhost:8000/api/v1/login \
  -d "username=admin@ayyapi.example.com&password=Parola123"

curl -s http://localhost:8000/api/v1/tasks/aaaa0000-0000-0000-0000-000000000001 \
  -H "Authorization: Bearer <ay-token>"
# 404 {"detail":"Görev bulunamadı!"}
```

**404, not 403.** A 403 would confirm the record exists and merely belongs to
somebody else — an existence oracle for every ID on the platform. The response
Ay Yapı gets for Kuzey's task is byte-identical to the response for an ID that
was never issued, and there is a test asserting exactly that equality.

Or skip the API: log in to the demo accounts and look at the two dashboards
side by side.

| Account | Company | Role |
|---|---|---|
| `admin@kuzey.example.com` | Kuzey Lojistik | admin |
| `calisan@kuzey.example.com` | Kuzey Lojistik | employee |
| `admin@ayyapi.example.com` | Ay Yapı | admin |

Password for all three: `Parola123`

<!-- FAZ 5: canlı demo yayına alındığında bu satırı gerçek URL ile değiştir -->
> **Live demo:** _not deployed yet — run it locally with the quick start below._

---

## Quick start

Requires PostgreSQL 13 or newer (`gen_random_uuid()` is built in from 13; on
older versions enable the `pgcrypto` extension) and Python 3.11+. Verified on
Python 3.11, 3.13 and 3.14, against PostgreSQL 16 locally and PostgreSQL 18 on
Neon. The migrations, the policy and the `set_config` mechanism needed no change
between the two.

```bash
git clone <repo> && cd saas_backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

cp .env.example .env          # then edit it — see the two-role note below
createdb saas_project

alembic upgrade head          # runs as the schema owner
python scripts/setup_db_role.py   # creates the restricted role the app uses
python scripts/seed_demo.py       # two companies, nine tasks, fixed IDs

uvicorn main:app --reload
```

`http://localhost:8000/docs` for the API, `/healthz` for a database ping.

**Two database roles, on purpose.** `.env` holds two URLs. The application
connects as a role that is not a superuser and does not own the tables, so it
cannot bypass or disable the isolation policies — it cannot alter the schema at
all. Alembic connects as the owner. `scripts/setup_db_role.py` creates the first
from the second, and refuses to finish if the role it created turns out to be
privileged.

Not sure your environment is right? `python scripts/check_db_setup.py` checks
every assumption above and tells you which one is wrong.

---

## Deploying

The order matters, because each step needs different privileges:

```bash
alembic upgrade head            # schema owner — creates tables and the RLS policy
python scripts/setup_db_role.py # creates the restricted role the app connects as
python scripts/seed_demo.py     # optional: the two demo companies
python scripts/check_db_setup.py   # verify the database before pointing traffic at it
python scripts/smoke_test.py       # verify the application on top of it
```

Environment variables:

| Variable | |
|---|---|
| `DATABASE_URL` | the restricted role — what the application uses |
| `MIGRATION_DATABASE_URL` | the schema-owning role — Alembic only, see below |
| `SECRET_KEY` | fresh per environment; changing it invalidates issued tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | optional, defaults to 60 |
| `CORS_ORIGINS` | comma-separated; the frontend's real domain in production |

Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

**Do not set `MIGRATION_DATABASE_URL` on the running web service.** Nothing the
application serves reads it — it exists for Alembic and the setup scripts, which
run from a deployment machine, not from the container answering requests. Leaving
it in the service's environment would hand the schema-owner password to the
process you deliberately stripped of schema privileges, and undo the separation
in one environment variable.

**On managed PostgreSQL** — Neon, Supabase, RDS — the administrative role you
are given is usually not a true superuser, and `ALTER ROLE … NOSUPERUSER` is
refused there. `setup_db_role.py` expects that: a role created by a
non-superuser cannot hold `SUPERUSER` or `BYPASSRLS` in the first place, so it
notes the refusal and moves on to what actually matters — verifying that the
role it produced cannot bypass the policies. It exits non-zero if it can.

Run `check_db_setup.py` against production after every deploy. It is the
difference between believing the isolation is on and knowing it.

Then run `smoke_test.py`, which checks the other half. `check_db_setup.py`
inspects the database; `smoke_test.py` drives the running application through
the *Try it yourself* scenario over HTTP — log in as both companies, fetch the
same task ID with each, compare the responses. A database can be configured
perfectly while the application forgets to tell it which tenant is asking, and
only a real request through the real stack shows that.

```bash
python scripts/smoke_test.py                              # in-process, against .env
python scripts/smoke_test.py https://your-app.example.com # against a deployment
```

It asserts one thing a human comparing two curl outputs would not: that the 404
for another tenant's task is *byte-identical* to the 404 for an ID that never
existed. Two 404s differing by a single character are still an existence oracle.

**If you keep a free-tier service warm with an external pinger, point it at `/`
and not at `/healthz`.** `/healthz` opens a database connection by design —
that is what makes it a useful health check. Aimed at a scale-to-zero Postgres
every few minutes, it also stops the database ever going idle, and turns a demo
nobody is using into a metered one. On Neon's free plan the difference is a
compute that lasts the month and one that suspends around day sixteen. `/`
returns a static response and touches nothing.

The pinger's *schedule* needs the same arithmetic. Render's free tier grants 750
instance hours per month; a month is about 730 of them. A ping that keeps one
service awake around the clock therefore spends very nearly the whole allowance
and leaves no room for a second service. Pinging only during the hours somebody
might actually open the link — sixteen a day is roughly 480 hours — keeps the
margin. Outside that window the first request pays the cold start, about a
minute on the free tier.

`.python-version` pins the interpreter. Platforms move their default Python
forward, and a demo nobody is watching should not be rebuilt on a version this
was never tested against.

---

## Isolation model

**Shared database, shared schema, `tenant_id` column.** Not schema-per-tenant,
not database-per-tenant. Those isolate more strongly and cost more per customer:
migrations multiply, connection pools fragment, and onboarding stops being a row
insert. For a product with many small tenants the shared model is usually right —
provided the isolation is enforced somewhere other than the discipline of
whoever writes the next query. Hence the second layer.

**The tenant comes from the database, not the token.** A JWT carries only `sub`,
the user id. `get_current_user` loads that user, and the tenant is
`user.tenant_id`. A token cannot claim to belong to a company; it can only
identify a user whose company is a fact in the database. This costs one query per
request and removes a whole class of forgery.

**The database is told who is asking.** After the user is resolved,
`get_tenant_db` runs `set_config('app.tenant_id', …, true)` and records the
tenant on the session. The policy on `tasks` compares every row against it:

```sql
CREATE POLICY tenant_isolation ON tasks
    USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

Four details, each of which silently voids the policy if skipped:

- **`set_config(..., true)`, never `SET`.** The third argument scopes the value
  to the transaction. Plain `SET` scopes it to the session, so it outlives the
  request, rides the pooled connection back to the pool, and applies to whoever
  borrows it next. The fix for a leak, reintroducing the leak.
- **`NULLIF(..., '')`.** After a transaction-local `set_config` has been used on
  a connection, the setting reverts to the empty string rather than NULL when
  the transaction ends. `''::uuid` raises. Without `NULLIF`, a missing tenant
  context produces a 500 instead of an empty result — and fail-closed has to
  mean *closed*, not *broken*.
- **`WITH CHECK`, not only `USING`.** `USING` filters reads. `WITH CHECK`
  validates writes. Without it, one tenant can insert a row stamped with
  another tenant's id: invisible to the author, visible to the victim.
- **The application role is not a superuser and does not own the tables.**
  Superusers bypass RLS unconditionally — `FORCE` does not stop them. An
  application connecting as `postgres` can carry every policy here and still
  hand every tenant's rows to every caller. `FORCE ROW LEVEL SECURITY` is on
  as well, for the case where ownership changes.

Both layers stay. The manual filters are not redundant with the policy: they
keep the intent visible at the call site, and they are what a reviewer reads.
The policy is what holds when the reviewer misses one.

---

## What is covered, and what is not

Seven ways tenant data leaks in a shared-schema system:

| # | Path | Status |
|---|---|---|
| 1 | **Query layer** — a query without its tenant filter | Covered: manual filters plus RLS on `tasks`; proved by deleting the filters |
| 2 | **IDOR** — fetching another tenant's row by its id | Covered: 404 on every verb, identical to a non-existent id |
| 3 | **File storage** — one tenant's uploads readable by another | Out of scope: this application stores no files |
| 4 | **Background jobs** — a worker running without tenant context | Out of scope: no queue, no workers |
| 5 | **Cache** — a cache key that omits the tenant | Out of scope: no cache layer |
| 6 | **Migrations** — a backfill that crosses tenants | Partial: migrations run as the owner and therefore bypass RLS. Reviewed by hand; not enforced |
| 7 | **Roles and limits** — cross-tenant admin actions, shared rate-limit buckets | Covered: roles are scoped to the tenant, and the rate limiter keys on identity rather than IP, so two tenants behind one office address do not share a bucket |

Rows 3 to 5 are marked out of scope rather than covered because the features do
not exist here. Claiming otherwise would be the same kind of empty assurance
this repository is arguing against.

---

## Known limits

Written down rather than left to be discovered:

- **RLS covers `tasks`, not `users`.** `/login` has to find a user by email
  across all tenants, and `get_current_user` loads the user before the tenant is
  known — both queries are, necessarily, the ones that establish the tenant
  rather than being constrained by it. Covering `users` needs a second,
  differently-privileged session for those two paths, which doubles connection
  pressure. `users` is protected by the manual filters only, and every query
  against it carries one; the two exceptions are commented in place.
- **`users.email` is globally unique**, not unique per tenant. One address
  cannot be a user at two companies. Most real products want
  `UNIQUE(tenant_id, email)`. This is a deliberate simplification, not an
  oversight.
- **Tokens cannot be revoked.** No `jti`, no denylist, no refresh token.
  Deactivating a user stops the next login, but a token already issued stays
  valid until it expires — up to 60 minutes by default.
- **Rate limits live in process memory.** Fine for one instance; a second
  instance means a second set of counters. A shared backend is a config change,
  not a redesign.
- **Migrations bypass RLS.** They run as the table owner. A migration that
  touches tenant data is reviewed by hand.

---

## Tests

```bash
createdb saas_project_test    # or let the suite create it
pytest -v
```

Six tests, all against a real PostgreSQL database. SQLite is not an option: the
schema uses native UUID columns with `gen_random_uuid()`, and RLS has no SQLite
equivalent. The test schema is built by running the Alembic migrations rather
than `Base.metadata.create_all()`, because the policies live in migrations — a
model-built schema would omit them and the suite would be proving nothing.

The suite connects as the restricted application role and uses the admin role
only to build and reset the schema. `test_row_level_security_is_actually_enforced`
asserts that the connection the application uses is not privileged enough to
bypass the policy, and refuses to run if it is.

A note on that last point, because it cost a day. This suite once passed with a
connection string whose password had been replaced by `***` — SQLAlchemy's
`str(URL)` masks passwords, and the masked form was being used as a real
credential. It passed because the development database was configured with
`trust` authentication, where no password is ever checked. A test environment
that authenticates nothing will certify code that authenticates nothing. The
suite now refuses to start if a test URL carries the literal password `***`.

---

## Layout

```
api/          HTTP routes — no queries here
services/     business rules, tenant checks
repositories/ database access — every query filtered by tenant_id
models/       SQLAlchemy models
core/         config, security, dependencies, rate limiting
alembic/      migrations, including the RLS policy
scripts/      role setup, environment preflight, demo data, smoke test
tests/        tenant isolation
```

Comments and API error messages are in Turkish; documentation, tests and commit
messages are in English.
