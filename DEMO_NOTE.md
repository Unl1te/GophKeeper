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

- Week 1 was end-to-end only for `health` (server reachable). All auth and data
  commands were stubs printing "Not implemented".
- Week 2 adds a real authentication path: a user can **register** and **log in**
  from the CLI and receive a stored JWT — the first real user journey beyond a
  liveness check.
- The data model now distinguishes secret types (`Item.type`), preparing for the
  secrets CRUD planned next.
- Still stubbed: real cryptography (hashing/encryption) and the secrets commands
  (`upload` / `download` / `history`).

---

# Week 3

## What was added

- **Server CRUD for items** (`app/api/routes/items.py`) — `POST /items` (create),
  `GET /items` (list, no content), `GET /items/{id}` (detail), `PUT /items/{id}`
  (update with version check), `DELETE /items/{id}` (soft delete). All endpoints
  are protected by JWT.
- **`POST /items/sync`** — batch endpoint that returns all non-deleted items.
- **Item repository layer**, plus `metadata` (JSON) and `deleted` (soft-delete)
  fields and migration `0003` (Mikhail).
- **Real cryptography** (Ivan) — `crypto_interface.py` stubs replaced with
  Argon2id password hashing and ChaCha20-Poly1305 (AEAD) encrypt/decrypt, plus
  key derivation from the master password.
- **CLI `add` / `list` / `get` / `delete`** (Dzhamilia) with client-side
  encryption: derives the key from a master password, encrypts content before
  upload, decrypts on `get`.
- **Local cache wired into the CLI** (`cli_cache.py`, `~/.gophkeeper/cache.json`)
  — `list` reads from the cache by default (`--refresh` pulls from the server and
  falls back to the cache when offline); `add` / `get` / `delete` keep it in sync.
- **Item tests** — `tests/test_api_items.py` (API CRUD + `409` conflict),
  `tests/test_cli_items.py` and `tests/test_cli_cache_integration.py` (Demian).

## How synchronization works

- The server is the source of truth; each item has an integer `version`.
- On update (`PUT /items/{id}`) the client sends the version it holds; if it is
  stale, the server returns `409 Conflict` with the current version, and the
  client is expected to refetch and retry.
- `version` auto-increments on every successful update; `updated_at` is refreshed.
- `DELETE` is a **soft delete** (`deleted = true`): rows stay in the DB and are
  excluded from `list` / `sync`.
- `POST /items/sync` returns the full current set so a client can reconcile.

## How Week 3 extends the MVP (vs Week 2)

- Week 2 added authentication (register / login + JWT). Week 3 adds the actual
  secret storage: a logged-in user can **add**, **list**, **get**, and **delete**
  encrypted items end-to-end.
- Content is encrypted on the client (ChaCha20-Poly1305, key from the master
  password); the server only ever stores ciphertext.
- Secrets now carry a `type` and free-form `metadata`; versioning and soft delete
  lay the groundwork for multi-client synchronization.

## Report material (Week 3)

New features this week: server CRUD for items (+ batch `/sync`), real client-side
cryptography (Argon2id, ChaCha20-Poly1305), and CLI `add` / `list` / `get` /
`delete` with encrypt/decrypt.

Screenshots to capture for the report:

- [ ] Swagger UI (`[/docs](http://10.93.27.17/docs)`) showing the new `/items` endpoints.
- [ ] CLI: `register`, `login`, `add`, `list` in action. (<img width="1371" height="356" alt="26-06-30 231527" src="https://github.com/user-attachments/assets/34bba2eb-1ad9-4428-a6ca-37e84e162326" />)


MVP comparison: see "How Week 3 extends the MVP (vs Week 2)" above.

