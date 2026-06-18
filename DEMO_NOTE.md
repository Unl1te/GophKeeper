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
