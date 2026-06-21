# GophKeeper

GophKeeper is a secure client-server vault for private data: passwords, text
notes, bank cards, and arbitrary files. The user works through a CLI client that
talks to a backend server; data is stored in PostgreSQL. Sensitive content is
encrypted on the client side.

---

## Run with Docker
Backend for secure secret storage — **FastAPI + PostgreSQL**.

Requirements: Docker and Docker Compose.

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

---

## CLI client

The client runs separately and talks to the server at `http://localhost:8000`.

```bash
python cli.py <command>
```

### Available commands

| Command    | What it does                                 | Status            |
|------------|----------------------------------------------|-------------------|
| `health`   | Checks that the server is running            | ✅ works           |
| `register` | Register a new user                          | ✅ works           |
| `login`    | Log in to your account                       | ✅ works           |
| `upload`   | Upload a secret or file                      | 🚧 in progress     |
| `download` | Download a secret or file                    | 🚧 in progress     |
| `history`  | View change history (versions)              | 🚧 in progress     |
| `help`     | Show help                                    | ✅ works           |

### The `health` command (in detail)

`health` is the simplest way to confirm the server is reachable. The client
sends `GET /health` and expects `{"status": "ok"}`.

```bash
# 1. make sure the server is running (docker-compose up)
# 2. in another terminal:
python cli.py health
```

Possible output:

| Output                             | What it means                           |
|------------------------------------|-----------------------------------------|
| `OK`                               | Server is running and responds correctly |
| `Error: could not connect to server` | Server is not running or unreachable |
| `Unexpected response: ...`         | Server responded, but not `{"status":"ok"}` |

The sequence diagram for `health` is in [ARCHITECTURE.md](ARCHITECTURE.md#diagram-health).

### Authentication: `register` and `login`

The server exposes two auth endpoints (full schemas in Swagger UI at `/docs`):

| Method & path     | Body                      | Success                                   | Errors |
|-------------------|---------------------------|-------------------------------------------|--------|
| `POST /register`  | `{"login","password"}`    | `201 {"message":"User '<login>' registered successfully"}` | `409` if login already exists |
| `POST /login`     | `{"login","password"}`    | `200 {"access_token","token_type":"bearer"}` | `401` on invalid login/password |

- `login` must be at least 3 characters, `password` at least 6.
- On login the server returns a JWT (HS256, 15-minute lifetime); the CLI stores
  it in `~/.gophkeeper/config.json` and sends it as `Authorization: Bearer
  <token>` on protected requests.

CLI usage examples:

```bash
# Register a new user
$ python cli.py register
login: alice
password: ******
User 'alice' registered successfully

# Log in (the JWT is saved to ~/.gophkeeper/config.json)
$ python cli.py login
login: alice
password: ******
Logged in successfully
```

The registration and login sequence diagrams are in
[ARCHITECTURE.md](ARCHITECTURE.md#3-interaction-diagrams).

---

## Environment variables

Settings are read from environment variables (see `.env.example`). For a local
Docker run everything works on the defaults — `.env` is optional.

| Variable          | Default      | Purpose                                                         |
|-------------------|--------------|-----------------------------------------------------------------|
| `DATABASE_URL`    | `postgresql+asyncpg://gophkeeper:gophkeeper@db:5432/gophkeeper` | Async DB connection string used by the backend |
| `API_PORT`        | `8000`       | Host port the API is published on (set to `80` on the course VM) |
| `POSTGRES_USER`   | `gophkeeper` | PostgreSQL user (must match `DATABASE_URL`)                     |
| `POSTGRES_PASSWORD` | `gophkeeper` | PostgreSQL password                                          |
| `POSTGRES_DB`     | `gophkeeper` | Database name                                                  |

> Important: the async `asyncpg` driver is used, so the URL must start with the
> `postgresql+asyncpg://` prefix. In docker-compose the database host is the
> service name `db`.

To override the defaults (custom credentials or port 80 on the VM), create a `.env`:

```bash
cp .env.example .env
# edit .env as needed
```

`.env` is git-ignored — only `.env.example` is committed.

---

## Architecture (in brief)

```
CLI client  ──HTTP──►  Backend (FastAPI)  ──async──►  PostgreSQL
 (requests)            register / login / JWT         users, items
                       secrets CRUD
```

More detail in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Project status

- ✅ DB models and connection
- ✅ Server skeleton, `/health`, `/db-check`
- ✅ CLI skeleton, `health` command
- ✅ Crypto interface (stubs) + tests
- ✅ CI, pre-commit, tests
- ✅ Docker / docker-compose, deployment
- ✅ register / login logic, JWT
- ✅ CLI register / login with local token storage
- 🚧 Secrets CRUD (upload / download / history)
- 🚧 Real cryptography implementation
