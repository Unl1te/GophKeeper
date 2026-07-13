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

- [X] Swagger UI (`http://10.93.27.17/docs`) showing the new `/items` endpoints.
- [X] CLI: `register`, `login`, `add`, `list` in action. 
<img width="1371" height="356" alt="26-06-30 231527" src="https://github.com/user-attachments/assets/34bba2eb-1ad9-4428-a6ca-37e84e162326" />

---

# Week 4

## What was added

- **`GET /items/versions`** — lightweight `id / version / updated_at` list so a
  client can check for changes without downloading full data.
- **Incremental `POST /items/sync`** — the client sends the `{id, version}` pairs
  it holds; the server returns only items whose version is newer.
- **Version conflict resolution (Last-Write-Wins)** — `PUT /items/{id}` returns
  `409 Conflict` with the current version when the client's version is stale.
- **CLI background check & auto conflict resolution** (Dzhamilia) — `list` calls
  `/items/versions` and refreshes the cache; on a `409` during `get` / `delete`
  the CLI refreshes and retries automatically ("Conflict detected … retrying").
- **Two-client demo script** `demo_two_clients.sh` (Ivan) — runs two independent
  CLI instances for one account, changes an item on one, and shows it appear on
  the other; also proves item isolation between accounts.
- **Sync & crypto tests** — `tests/test_cli_sync_integration.py`, a two-client
  simulation, and performance tests for `encrypt_data` / `decrypt_data`.

## Two-client demonstration

- Client A and Client B log into the **same** account using separate config
  directories (via `GOPHKEEPER_HOME`), so they behave like two devices.
- Client A creates an item and then modifies it (`PUT /items/{id}` with the
  current version → the server bumps the version).
- Client B runs `list --refresh` / `get` and sees the updated content and the new
  version — the background check picks up the change.
- A second account (`bob`) requesting the same item id gets `404`, proving items
  are private per account.

## How Week 4 extends the MVP (vs Week 3)

- Week 3 gave a single client full CRUD over encrypted items. Week 4 makes it
  **multi-client**: a change made on one client becomes visible on another.
- Conflicts are resolved with a clear policy (Last-Write-Wins + `409`), and the
  client detects changes cheaply via `/items/versions` instead of re-downloading
  everything.

## Report material (Week 4)

New features this week: version model + conflict resolution (Last-Write-Wins),
background update check (`/items/versions`), incremental sync (`/items/sync`), and
a two-client demo.

To include in the report:

- [X] Screenshot: two CLI clients — a change on Client A appearing on Client B.
<img width="1865" height="516" alt="two_client_demo" src="https://github.com/user-attachments/assets/835b74b5-d5c9-4c54-8083-693bd6cf9298" />

- [X] Screenshot: a `409` conflict being detected and auto-resolved.
<img width="1415" height="100" alt="conflict_demo" src="https://github.com/user-attachments/assets/f95dc6c6-e30c-4963-8559-caf6bdfa1eee" />

- [X] Measurements vs baseline (Industrial track): `encrypt_data` / `decrypt_data`
      timings on large payloads (e.g. 10 MB) from the crypto performance tests.
<img width="1512" height="417" alt="crypto_perf" src="https://github.com/user-attachments/assets/86c9e0ef-ed9c-4255-a62e-3cfab54e875c" />

---

# Week 5

## What was added

- **Full CLI UX** — the client now uses `rich` for coloured output, tables and
  interactive prompts, plus a **`tui`** command (menu-driven terminal UI).
- **New commands** — `update` (interactive edit), `history` (local change
  history of an item), and `logout` (clears token, cache, history).
- **OTP (one-time passwords)** — new `otp` data type; `otp <id>` prints the
  current TOTP code and `verify-otp <id> <code>` checks a code. The TOTP secret
  is stored encrypted; codes are generated on the client (`pyotp`).
- **Export / import** — `export <file>` / `import <file>` save and load the local
  cache as JSON (local only, no sync).
- **Binary builds** — GitHub Actions (`build.yml`) builds standalone binaries
  (Windows / Linux) with PyInstaller; `version` shows the version and build date.
- **Extra tests** — OTP tests (`tests/test_otp.py`, `tests/test_otp_api.py`) and
  a binary-protocol proof of concept (`tests/test_binary_protocol_poc.py`).

## How Week 5 extends the MVP (vs Week 4)

- Week 4 made the vault multi-client (sync + conflict resolution). Week 5 rounds
  out the **user experience and data types**: a polished coloured CLI (and a TUI),
  an interactive `update`, local `history`, `logout`, and `export` / `import`.
- New **OTP** type turns GophKeeper into a working authenticator — TOTP codes are
  generated locally, the server never sees the secret.
- Distribution: the CLI is now built as standalone binaries.

## Report material (Week 5)

New features this week: full `rich` CLI UX + `tui`, `update` / `history` /
`logout`, OTP (`otp` / `verify-otp`), `export` / `import`, and binary builds.

Screenshots to capture for the report:

- [X] CLI with the new coloured UI / `tui` menu.
<img width="1047" height="802" alt="cli_ui" src="https://github.com/user-attachments/assets/06281431-c46d-42fa-a84a-a4cb8491ef28" />

- [X] OTP in action: `add --type otp …` then `otp <id>` showing a TOTP code.
<img width="1081" height="135" alt="otp_demo" src="https://github.com/user-attachments/assets/5bfed88e-174e-4039-8ee9-14d989e1a846" />

- [X] `export` / `import` of the local cache.
<img width="948" height="303" alt="export_import_demo" src="https://github.com/user-attachments/assets/f679a928-df26-4c06-93f9-72559e2b8cc3" />


---
