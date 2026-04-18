# Open Ledger

A financial ledger service built with FastAPI and PostgreSQL, implementing **double-entry bookkeeping** as an isolated microservice.

> **Learning-focused.** This repository exists primarily as a study reference for financial ledger design — double-entry bookkeeping, immutable audit trails, event-driven architecture, and incremental balance strategies.

## What is this?

A financial ledger is the authoritative, append-only record of all financial events in a system. Every balance is the result of explicit debit and credit entries — nothing is ever overwritten or deleted.

This project implements that model as a standalone service:

- Every financial event (sale, fee, settlement, chargeback) is recorded as a set of balanced debit/credit entries
- Account balances are maintained incrementally via database triggers — no aggregation at query time
- A **World Account** represents the external world, keeping double-entry intact when money enters or leaves the system
- The service consumes events from an upstream system and never reads its database directly
- All event handlers are idempotent; duplicate events are safely ignored

For the full design — data model, chart of accounts, transaction flows, balance strategy — see [`.docs/open-ledger-full-spec.md`](.docs/open-ledger-full-spec.md).

## Technology and Resources

- [Python 3.14](https://www.python.org/downloads/release/python-3140/) - **pre-requisite**
- [Docker](https://www.docker.com/get-started) - **pre-requisite**
- [Docker Compose](https://docs.docker.com/compose/) - **pre-requisite**
- [Poetry](https://python-poetry.org/) - **pre-requisite**
- [Ruff](https://github.com/astral-sh/ruff)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Uvicorn](https://www.uvicorn.org/)
- [Alembic](https://alembic.sqlalchemy.org/en/latest/) - *database migration tool*
- [Testcontainers](https://testcontainers.com/) - *integration testing*

*Please pay attention on **pre-requisites** resources that you must install/configure.*

## How to install, run and test

### Environment variables

Variable | Description | Available Values | Default Value | Required
--- | --- | --- | --- | ---
ENV | The application environment | `dev / test / qa / prod` | `dev` | Yes
PYTHONPATH | Python interpreter path guidance | [ref](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONPATH) | `.` | Yes
DATABASE_USER | The database user | `a valid user` | `postgres` | Yes
DATABASE_PASS | The database user password | `a valid password` | `postgres` | Yes
DATABASE_PORT | The database port | `a valid port number` | `5433` | Yes
DATABASE_NAME | The database name | `a valid database name` | `open_ledger_db` | Yes
DATABASE_ENDPOINT | The database endpoint | `a valid database endpoint` | `localhost` | Yes

*Note: When you run the install command (using docker or locally), a .env file will be created automatically based on [env.template](env.template)*

Command | Docker | Locally | Description
---- | ------- | ------- | -------
install | `make docker/install` | `make local/install` | to install
tests | `make docker/tests` | `make local/tests` | to run the tests with coverage
lint | `make docker/lint` | `make local/lint` | to run static code analysis using ruff
lint/fix | `make docker/lint/fix` | `make local/lint/fix` | to fix files using ruff
run | `make docker/run` | `make local/run` | to run the project
migration apply | - | `make migration/apply` | to apply new version of migrations
migration revision | - | `make migration/revision message="text a new message"` | to create a new revision of migrations
migration downgrade | - | `make migration/downgrade` | to downgrade a version of migrations
build image | `make docker/image/build` | - | to build the production docker image
build image distroless | `make docker/image/build/distroless` | - | to build the distroless production image
push image | `make docker/image/push` | - | to push the docker image
push image distroless | `make docker/image/push/distroless` | - | to push the distroless image

**Helpful commands**

*Please, check all available commands in the [Makefile](Makefile) for more information*.

### Uvicorn settings

Uvicorn is an ASGI web server implementation for Python and you can [configure](https://www.uvicorn.org/settings/) it overriding these values on the [settings.conf](settings.conf) file.

Variable | Description | Available Values | Default Value | Required
--- | --- | --- | --- | ---
UVICORN_HOST | The host of the application |  `a valid host address` | `0.0.0.0` | Yes
UVICORN_PORT | The application port |  `a valid port number` | `8000` | Yes
UVICORN_WORKERS | The number of uvicorn workers |  `a valid number` | `dev` | No
UVICORN_ACCESS_LOG | Enable or disable the access log |  `True / False` | `True` | No
UVICORN_LOG_LEVEL | Set the log level |  `critical / error / warning / info / debug / trace'` | `info` | No

*Note: The default value of these configs are available on [run.py](run.py).*

## Production Docker Images

This project provides two production-ready Docker images with a multi-stage build approach:

### Standard Production Image (`production`)

Based on `python:3.14-slim-bookworm`, this is a minimal image without Poetry or development dependencies.

```bash
make docker/image/build
```

### Distroless Production Image (`production-distroless`)

An ultra-minimal image using [Chainguard](https://www.chainguard.dev/) for maximum security and smallest footprint.

```bash
make docker/image/build/distroless
```

**Why Chainguard?**

- **Minimal attack surface**: No shell, package managers, or unnecessary tools
- **Reduced CVEs**: Significantly fewer vulnerabilities compared to traditional base images
- **Smaller size**: Only essential runtime components included
- **Signed images**: Cryptographically signed with Sigstore for supply chain security
- **SBOM included**: Software Bill of Materials for compliance and auditing

**Trade-offs:**

- No shell access for debugging (use ephemeral debug containers if needed)
- Free tier only provides `:latest` tag (specific version tags like `3.14.x` require paid tier)

**Running the distroless image:**

```bash
docker run -p 8000:8000 --env-file .env open-ledger:latest-distroless
```

For more information about Chainguard images, visit the [official documentation](https://edu.chainguard.dev/chainguard/chainguard-images/).

## Logging

This project uses a simple way to configure the log with [logging.conf](logging.conf) to show the logs on the container output console.

## Settings

This project uses a simple way to manage the settings with [settings.conf](settings.conf) and [ConfigParser](https://docs.python.org/3/library/configparser.html) using a [config class](./src/config/settings.py).
