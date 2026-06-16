# GophKeeper

Backend for secure secret storage — **FastAPI + PostgreSQL**.

## Run with Docker

Prerequisites: Docker and Docker Compose.

```bash
docker-compose up --build
```

That's it — sensible defaults are baked in, so no extra setup is needed for local
development. The stack starts two services: the FastAPI **backend** and a
**PostgreSQL** database (the backend waits until the DB is healthy).

Once it's up, the API is available at:

| Endpoint | Description |
|----------|-------------|
| http://localhost:8000/health | Liveness check → `{"status": "ok"}` |
| http://localhost:8000/db-check | DB connectivity → `{"db": "ok"}` |
| http://localhost:8000/docs | Swagger UI |

Quick smoke test:

```bash
curl http://localhost:8000/health    # {"status":"ok"}
curl http://localhost:8000/db-check  # {"db":"ok"}
```

Stop the stack:

```bash
docker-compose down       # stop containers, keep the database
docker-compose down -v    # also wipe the database volume
```

### Configuration (optional)

Defaults work out of the box. To override them (custom credentials, or publishing the
API on port 80 on the course VM), create a `.env` file from the template:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://gophkeeper:gophkeeper@db:5432/gophkeeper` | Async DB connection string used by the backend |
| `API_PORT` | `8000` | Host port the API is published on (set to `80` on the VM) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `gophkeeper` | PostgreSQL credentials (must match `DATABASE_URL`) |

`.env` is git-ignored — only `.env.example` is committed.
