# Notes from internal demo

---

## Demo date

2026-06-16

## Attendees

- [x] Mikhail (DB)
- [x] Artem U. (backend)
- [x] Artem N. (DevOps)
- [x] Dzhamilia (CLI)
- [x] Ivan (crypto)
- [x] Demian (CI/CD)
- [x] Nastya (documentation)

## What was shown

- Brought the stack up with `docker-compose up --build` (backend + PostgreSQL).
- `GET /health` → `{"status":"ok"}`; tried `GET /db-check` (revealed an async
  bug, see below).
- CLI: `python cli.py health` → `OK`; walked through `python cli.py help`.
- Tried the remaining CLI commands and the `/register`, `/login` endpoints.

## What worked

- `docker-compose up` starts cleanly; the backend waits for the DB healthcheck,
  so there's no race on the first run.
- `/health` returns OK from inside the compose network.
- The CLI `health` and `help` commands work and print the expected output.
- Swagger UI at `/docs` lists all routes — handy for the demo.

## What didn't work / issues

Found during the demo:

1. **No DB tables are created.** Models (`User`, `Item`) are defined, and
   `/db-check` relies only on `SELECT 1` — but there is no `metadata.create_all`
   / migration step, so any real query would fail on an empty schema. **Blocker**
   for register/login and secrets work.
2. **`register` / `login` return `501 Not Implemented`** — business logic not
   written yet (expected, but it's the critical path).
3. **Async bug in `/db-check`** — the handler called `db.execute(...)`
   synchronously on an `AsyncSession`, so the DB check failed. (Fixed after the
   demo, see below.)

## Done after the demo

- **Fixed the `/db-check` async bug** — switched to `await db.execute(...)` with
  `AsyncSession`; `/db-check` now returns `{"db":"ok"}`.
- **Added Docker**: `Dockerfile`, `.env.example`, `.dockerignore`,
  `docker-compose.yml` (backend + PostgreSQL with healthcheck).

## Decisions and agreements

- Table creation / migrations is the top priority: without it nothing can be
  tested end-to-end. Mikhail to add schema creation (Alembic or `create_all`
  on startup).
- After the schema lands: Artem U. implements `register` (hash the account
  password, store the user), then `login` + JWT.
- Ivan keeps the stub interface stable so CLI/backend can integrate against it,
  and starts the real Argon2id / ChaCha20-Poly1305 implementation.
- Dzhamilia wires the CLI commands to real HTTP calls once `register`/`login` exist.
- Nastya updates the docs as endpoints become real (status table, diagrams).

---

# Week 2

## What was added

- **`POST /register`** — checks for a duplicate login (`409`), hashes the
  password via `crypto_interface.hash_password` (still a stub), stores the user,
  returns `201`.
- **`POST /login`** — validates the user and password, issues a JWT
  (`access_token`), returns `401` on invalid credentials.
- **JWT module** (`app/core/security.py`) — `create_access_token` /
  `decode_token`, HS256, 15-minute lifetime, `SECRET_KEY` from the environment;
  config in `app/core/config.py`. Unit tests for the JWT functions added.
- **DB schema is now created automatically** on container startup
  (`alembic upgrade head`, with a `create_all` fallback) — the Week 2 blocker is
  resolved.
- **Alembic migrations** and **`Item.type`** (`DataType` enum: password / card /
  text / binary) added to the model.
- **CLI `register` / `login`** now send real HTTP requests and store the JWT in
  `~/.gophkeeper/config.json`.
- **Auth unit tests** — `tests/test_api_auth.py` (register/login: success,
  duplicate login, wrong password) and `tests/test_cli_auth.py` (CLI with mocked
  HTTP). CI runs `pytest` with coverage (`pytest-cov`).

## How Week 2 extends the MVP (vs Week 1)

- Week 2 was end-to-end only for `health` (server reachable). All auth and data
  commands were stubs printing "Not implemented".
- Week 3 adds a real authentication path: a user can **register** and **log in**
  from the CLI and receive a stored JWT — the first real user journey beyond a
  liveness check.
- The data model now distinguishes secret types (`Item.type`), preparing for the
  secrets CRUD planned next.
- Still stubbed: real cryptography (hashing/encryption) and the secrets commands
  (`upload` / `download` / `history`).

---
