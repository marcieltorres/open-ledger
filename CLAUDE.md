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
`run.py` → `src/api.py` → `src/routes/` → `src/services/` → `src/repositories/` → SQLAlchemy session

### Key Modules

- **`src/api.py`** — FastAPI app instance, health check endpoint, router registration
- **`src/config/settings.py`** — `Settings` class wrapping ConfigParser; reads `settings.conf` (INI format) com sections `[default]`, `[dev]`, `[test]`, `[qa]`, `[prod]`; selects section via `ENV`; `settings.get_from_env(name)` reads env vars
- **`src/config/database.py`** — SQLAlchemy engine, `SessionLocal`, `get_db()` FastAPI dependency (commit on success, rollback on exception)
- **`src/model/base_model.py`** — SQLAlchemy `DeclarativeBase` with UUID PK, `created_at`/`updated_at`; all models inherit this
- **`src/model/`** — ORM models (one file per domain entity)
- **`src/model/schemas/`** — Pydantic request/response schemas (one file per domain entity)
- **`src/routes/`** — FastAPI routers (one file per resource); zero business logic here
- **`src/services/`** — domain services with business rules; use repositories for data access
- **`src/exceptions/`** — domain exceptions, one file per domain (e.g. `entity.py`, `account.py`); `__init__.py` re-exports all for convenience
- **`src/repositories/base.py`** — `BaseRepository[T]` with generic CRUD (`get_by_id`, `get_all`, `create`, `update`, `delete`, `exists`)
- **`src/repositories/`** — concrete repositories extending BaseRepository (one file per domain entity)

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

## Padrões de desenvolvimento

- **Estrutura de rotas**: recursos pertencem a `src/routes/<resource>.py`; sub-recursos de uma entidade ficam em `/entities/{id}/<sub-resource>`; schemas Pydantic ficam em `src/model/schemas/<resource>.py`
- **Camada de serviço**: toda lógica de negócio fica em `src/services/*.py`; rotas só fazem parse do request, chamam o serviço e formatam a resposta; serviços usam repositórios para data access
- **Modelos SQLAlchemy**: herdam `BaseModel` de `src/model/base_model.py`; usar `Mapped[T]` para todas as colunas; nunca usar `float` para valores monetários — sempre `Decimal`; quando o nome do atributo colide com o namespace do SQLAlchemy (ex: `metadata`), usar sufixo `_` no atributo e mapear para o nome correto na coluna (`mapped_column("metadata", ...)`)
- **Schemas Pydantic**: usar `validation_alias` para mapear atributos com sufixo `_` do ORM (ex: `Field(None, validation_alias="metadata_")`); sempre usar `ConfigDict(from_attributes=True)` nos schemas de resposta
- **Erros de domínio**: exceções ficam em `src/exceptions/` com um arquivo por domínio (ex: `src/exceptions/entity.py`, `src/exceptions/account.py`); `src/exceptions/__init__.py` re-exporta todas para conveniência; cada exceção estende `Exception` com corpo `pass`; capturadas nas rotas e convertidas para `HTTPException` com o status code correto; usar imports diretos por domínio (ex: `from src.exceptions.entity import EntityNotFoundError`), não o pacote raiz
- **Migrations**: criadas com `make migration/revision message="..."` (requer banco rodando); `migration/env.py` deve importar todos os models para que o autogenerate funcione; uma migration por PR; nunca editar após merge
- **Testes de integração**: usam testcontainers (Postgres real); a fixture `get_db` é sobrescrita via `app.dependency_overrides[get_db] = lambda: self.db_session`; o `db_session` é function-scoped com rollback automático ao final
- **Colima (macOS)**: configurar `DOCKER_HOST=unix://${HOME}/.colima/default/docker.sock` e `TESTCONTAINERS_RYUK_DISABLED=true` no `.env`

## Configuration

**`settings.conf`** — app name/description per environment (INI format).  
**`logging.conf`** — standard Python logging, outputs to console.  
**`pyproject.toml`** — Ruff line length 120, rules `E,F,W,I,N,S`; pytest source `src/`, tests `tests/`.  
**`alembic.ini`** — migration file pattern `{year}_{month}{day}_{hour}{minute}-{rev}_{slug}.py`.
