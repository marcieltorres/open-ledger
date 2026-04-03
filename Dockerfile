# =============================================================================
# BUILDER STAGE - Export dependencies (discarded after build)
# =============================================================================
FROM python:3.14-slim-bookworm AS builder

WORKDIR /build

COPY pyproject.toml poetry.lock* ./

RUN pip install --no-cache-dir poetry poetry-plugin-export && \
    poetry export --without dev --format=requirements.txt --output=requirements.txt

# =============================================================================
# DEVELOPMENT STAGE - Full Poetry environment for development
# =============================================================================
FROM python:3.14-slim-bookworm AS development

EXPOSE 8000
WORKDIR /src

COPY pyproject.toml poetry.lock* ./

RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install && \
    rm -rf ~/.cache/pypoetry

COPY . .

# =============================================================================
# DEPENDENCIES STAGE - Install deps to a portable directory
# =============================================================================
FROM python:3.14-slim-bookworm AS dependencies

WORKDIR /build

COPY --from=builder /build/requirements.txt .

RUN pip install --no-cache-dir --target=/deps -r requirements.txt

# =============================================================================
# PRODUCTION STAGE - Minimal image without Poetry
# =============================================================================
FROM python:3.14-slim-bookworm AS production

EXPOSE 8000
WORKDIR /src

COPY --from=dependencies /deps /usr/local/lib/python3.14/site-packages

COPY src src
COPY settings.conf src
COPY logging.conf src
COPY run.py src
COPY migration src
COPY alembic.ini src

# =============================================================================
# PRODUCTION DISTROLESS - Ultra minimal with Chainguard (Python 3.14)
# =============================================================================
# Chainguard: minimal, secure, no shell (https://images.chainguard.dev/directory/image/python)
# Note: Version tags (3.14.x) require paid tier. Free tier only has :latest
FROM cgr.dev/chainguard/python:latest AS production-distroless

WORKDIR /app

COPY --from=dependencies /deps /home/nonroot/.local/lib/python3.14/site-packages
COPY src /app/src
COPY settings.conf /app
COPY logging.conf /app
COPY run.py /app
COPY migration /app/migration
COPY alembic.ini /app

EXPOSE 8000

ENTRYPOINT ["python", "run.py"]
