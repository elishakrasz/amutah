# Amutah aid case management

The specification is [`amutah.md`](amutah.md), extended by [`ADOPTED_PRACTICES.md`](ADOPTED_PRACTICES.md) (cite items as `AP-n`). Decisions and open questions: [`docs/decisions.md`](docs/decisions.md).

**Demo only.** The demo uses synthetic data. It does not prove performance under load,
encryption at rest, MFA, or backup and restore.

## Run the demo

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 22+.

```sh
# API
cd api
cp .env.example .env
uv run python -m app.scripts.gen_keys >> .env   # fills the three keys
uv sync --all-extras
uv run alembic upgrade head
uv run python -m app.scripts.seed_demo
uv run uvicorn app.main:app --reload            # http://localhost:8000/docs

# Web (second terminal)
cd web
npm install
npm run dev                                      # http://localhost:3000/staff/login
```

## Checks

```sh
cd api
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
# Also against PostgreSQL:
docker run -d --rm --name pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=amutah_test -p 55432:5432 postgres:16
AMUTAH_TEST_PG_URL=postgresql+psycopg://postgres:test@localhost:55432/amutah_test uv run pytest
```

## Build progress

- [x] 1. Foundation: settings, SQLite + Alembic baseline with append-only triggers (both dialects), local `DocumentStore`, `Notifier` and `AuthProvider`, dev role picker, CI (SQLite + PostgreSQL + web)
- [x] Schema for ADOPTED_PRACTICES (migration 0003): referrer status, leads, intake calls, rights checks, income worksheet, allocations, voucher stock, public stats and documents
- [x] 2. Domain rules engine: config, tiers, gate, caps, documents, scoring, income (standard persons), approval panels, decision checks, workflow, working days, budget. 100% branch coverage, enforced in CI (incl. AP-1, 2, 5, 7, 8, 9, 10, 12, 13, 16, 20)
- [ ] 3. Intake
- [ ] 4. Committee
- [ ] 5. Payments
- [ ] 6. Seed and demo script
