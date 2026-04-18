# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**open-ledger** is a financial ledger service built on FastAPI + PostgreSQL. It implements double-entry bookkeeping as an isolated microservice: every financial event (sale, anticipation, settlement, cancellation) is recorded as immutable debit/credit entries, balances are maintained incrementally by the application layer within the same DB transaction, and the ledger communicates with upstream systems exclusively through events.

The full design spec is at `.docs/open-ledger-full-spec.md`. Read it before adding new domain logic.

Python 3.14+ and Poetry are required.

## Common Commands

```bash
# Setup
make local/install          # Install dependencies via Poetry
make docker/install         # Build Docker dev image

# Running
make local/run              # Run locally (poetry run python run.py)
make docker/up              # Start docker-compose services
make docker/down            # Stop services

# Testing
make local/tests            # Run all tests with 100% coverage enforcement
make docker/test            # Run tests in Docker

# Single test
poetry run pytest tests/unit/config/test_settings.py -s
poetry run pytest tests/unit/config/test_settings.py::SettingsTest::test_get_setting_value_with_success -s

# Linting
make local/lint             # Run Ruff linter
make local/lint/fix         # Auto-fix Ruff issues

# Migrations
make migration/apply                           # alembic upgrade head
make migration/revision message="description" # Create new migration
make migration/downgrade                       # Revert last migration
```

## Architecture

### Request Flow
`run.py` → `src/api.py` (FastAPI app) → routes → SQLAlchemy sessions

### Key Modules

- **`src/api.py`** — FastAPI app instance, health check endpoint, route registration
- **`src/config/settings.py`** — `Settings` class wrapping ConfigParser; reads `settings.conf` (INI format) with sections `[default]`, `[dev]`, `[test]`, `[qa]`, `[prod]`; selects section via `ENV` environment variable
- **`src/model/base_model.py`** — SQLAlchemy `DeclarativeBase` with UUID primary key, `created_at`/`updated_at` timestamps; all models inherit this

### Ledger Domain

The core tables are: `entities`, `chart_of_accounts`, `transactions`, `transaction_entries`, `event_log`, `receivables`, `account_balance_snapshots`, `accounting_periods`. Key invariants:

- **Immutability** — entries are never updated or deleted; corrections post new reversing entries.
- **Double-entry** — every `transaction` must have Σ debits = Σ credits before committing.
- **Incremental balance** — the application updates `chart_of_accounts.current_balance` via `SELECT FOR UPDATE` within the same DB transaction that inserts the entries. Never compute balances by summing entries at query time except in the nightly validation job.
- **World account** — account `9.9.999` represents the outside world. Use it whenever money crosses the system boundary (deposits, withdrawals, settlements, chargebacks).
- **Transfer account** — account `9.9.998` represents money moving between entities *within* the ledger. Use it for internal transfers (e.g. PIX between two BaaS customers). Σ Transfer across all entities = 0 always.
- **Idempotency** — `event_log(event_id, event_type)` and `transactions(idempotency_key)` have UNIQUE constraints. All event handlers must be idempotent.
- **Entity isolation** — each entity (seller, buyer, payfac) has its own chart of accounts provisioned from a template on `entity.created`. Never share accounts across entities.
- **Regulatory mapping** — COSIF and other framework mappings are the responsibility of the upstream reporting layer, not the ledger. Internal account codes are free-form. See the "Regulatory Mapping" section in the full spec.

### Database / Migrations
- SQLAlchemy 2.0 style with `Mapped` type annotations
- Alembic migrations live in `migration/`; env vars (`DATABASE_USER`, `DATABASE_PASS`, `DATABASE_ENDPOINT`, `DATABASE_PORT`, `DATABASE_NAME`) configure the connection
- Copy `env.template` to `.env` for local development

### Testing Infrastructure
- **Unit tests** (`tests/unit/`) — no database, fast
- **Integration tests** (`tests/it/`) — spin up a real PostgreSQL 13.3 container via testcontainers; each test function gets an isolated session with automatic rollback
- 100% coverage is required (`fail_under = 100` in `pyproject.toml`)

### Docker
Multi-stage `Dockerfile` with three targets:
- `development` — full Poetry environment
- `production` — slim image (requirements.txt export, no Poetry)
- `production-distroless` — Chainguard minimal image for security

## Configuration

**`settings.conf`** — app name/description per environment (INI format).  
**`logging.conf`** — standard Python logging, outputs to console.  
**`pyproject.toml`** — Ruff line length 120, rules `E,F,W,I,N,S`; pytest source `src/`, tests `tests/`.  
**`alembic.ini`** — migration file pattern `{year}_{month}{day}_{hour}{minute}-{rev}_{slug}.py`.
