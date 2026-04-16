FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1     VIRTUAL_ENV=/opt/venv     PATH="/opt/venv/bin:${PATH}"

WORKDIR /src

RUN python -m venv "$VIRTUAL_ENV"     && apt-get update     && apt-get install -y --no-install-recommends build-essential     && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY db_migrations ./db_migrations
COPY deploy ./deploy
COPY docs ./docs
COPY scripts ./scripts
COPY AGENTS.md ./AGENTS.md

RUN pip install --upgrade pip setuptools wheel     && pip install .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     VIRTUAL_ENV=/opt/venv     PATH="/opt/venv/bin:${PATH}"

RUN addgroup --system app     && adduser --system --ingroup app --home /app app     && mkdir -p /app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app app ./app
COPY --chown=app:app db_migrations ./db_migrations
COPY --chown=app:app deploy ./deploy
COPY --chown=app:app docs ./docs
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app AGENTS.md ./AGENTS.md

USER app

EXPOSE 8000 9101 9102

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
