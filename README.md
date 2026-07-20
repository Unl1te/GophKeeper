# GophKeeper

GophKeeper is a secure client-server vault for private data: passwords, text
notes, bank cards, and arbitrary files. The user works through a CLI client that
talks to a backend server; data is stored in PostgreSQL. Sensitive content is
encrypted on the client side.

---

## Project links

| Resource | Link |
|----------|------|
| Repository | https://github.com/Unl1te/GophKeeper |
| Deployed backend VM | http://10.93.27.17 |
| Swagger UI | http://10.93.27.17/docs |
| OpenAPI JSON | http://10.93.27.17/openapi.json |
| Web testing instrument | http://10.93.27.17/web |
| Architecture document | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Demo notes | [DEMO_NOTE.md](DEMO_NOTE.md) |
| Capstone board | https://github.com/users/Unl1te/projects/1/views/1 |
| Final report draft | https://www.overleaf.com/project/6a5cd9dc6a4b588304fcc32e |

GophKeeper is CLI-first. A Figma prototype is not required for this project
because there is no graphical product UI; manual web testing is done through
Swagger UI and the project web testing endpoint.

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

For the deployed VM, point the client to the team server:

```bash
# Linux / macOS
export GOPHKEEPER_SERVER=http://10.93.27.17

# Windows PowerShell
$env:GOPHKEEPER_SERVER = "http://10.93.27.17"
```

### Available commands

| Command    | What it does                                 | Status            |
|------------|----------------------------------------------|-------------------|
| `health`   | Checks that the server is running            | ✅ works           |
| `register` | Register a new user                          | ✅ works           |
| `login`    | Log in to your account                       | ✅ works           |
| `add`      | Add a new item (encrypts content client-side)| ✅ works           |
| `list`     | List your items (from local cache; `--refresh` to pull from server) | ✅ works           |
| `get`      | Get and decrypt an item by id                | ✅ works           |
| `update`   | Update an existing item (interactive)        | ✅ works           |
| `delete`   | Delete an item by id (soft delete)           | ✅ works           |
| `history`  | View the local change history of an item     | ✅ works           |
| `otp`      | Show the current TOTP code for an OTP item   | ✅ works           |
| `verify-otp` | Verify a TOTP code against an OTP item     | ✅ works           |
| `export`   | Export the local cache to a JSON file        | ✅ works           |
| `import`   | Import items from a JSON file                | ✅ works           |
| `tui`      | Launch the interactive terminal UI (menu)    | ✅ works           |
| `version`  | Show version and build date                  | ✅ works           |
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

### Items: `add` / `list` / `get` / `delete`

All `/items*` endpoints require a valid JWT (`Authorization: Bearer <token>`),
so log in first. Content is encrypted on the client (ChaCha20-Poly1305, with the
key derived from a master password) before it is sent — the server only ever
stores ciphertext.

| Method & path        | Body                                  | Success                | Errors |
|----------------------|---------------------------------------|------------------------|--------|
| `POST /items/`       | `{type, content (hex), metadata}`     | `201` item detail      | `401` |
| `GET /items/`        | —                                     | `200` list (no content)| `401` |
| `GET /items/{id}`    | —                                     | `200` item + content   | `404`, `401` |
| `PUT /items/{id}`    | `{content, metadata, version}`        | `200` item detail      | `409` version conflict, `404`, `401` |
| `DELETE /items/{id}` | —                                     | `204` (soft delete)    | `404`, `401` |
| `GET /items/versions`| —                                     | `200 [{id, version, updated_at}]` | `401` |
| `POST /items/sync`   | `{items: [{id, version}]}`            | `200 {updates: [...]}` (only items newer than the client's version) | `401` |

CLI usage examples (each `add` / `get` asks for the master password to
derive the encryption key):

```bash
# add a text secret with metadata
$ python cli.py add --type text --content "my secret" --meta note=test
Master password: ******
Success: Item created (id: 1, version: 1)

# add a binary file
$ python cli.py add --type binary --file ./secret.pdf

# list your items
$ python cli.py list
ID     Type       Version  Updated At
--------------------------------------------------
1      text       1        2026-06-30T12:00:00

# get and decrypt an item
$ python cli.py get 1
Master password: ******
Item #1
Type: text
...
--- Content ---
my secret

# delete an item (soft delete)
$ python cli.py delete 1
Are you sure you want to delete item 1? [y/N] y
Success: Item 1 deleted
```

`list` reads from a local cache (`~/.gophkeeper/cache.json`) by default; pass
`--refresh` to pull the latest from the server. `add` / `get` / `delete` keep the
cache in sync, and `list` falls back to the cache when the server is unreachable.

### Versions and conflicts

Every item has an integer `version`. Multi-client changes are reconciled with a
**Last-Write-Wins** policy:

- On `PUT /items/{id}` the client sends the version it holds. If it is stale, the
  server replies `409 Conflict` with the current version; on success `version` is
  incremented.
- **Background check:** `list` calls `GET /items/versions` (a lightweight
  `id / version / updated_at` list) to detect changes and refresh the local cache
  automatically. `list --refresh` forces a full pull.
- **Incremental sync:** `POST /items/sync` takes the `{id, version}` pairs the
  client holds and returns only the items whose server version is newer.
- On a conflict during `get` / `delete`, the CLI automatically refreshes and
  retries, printing a short "Conflict detected … retrying" message.
  
The CRUD and synchronization sequence diagrams are in
[ARCHITECTURE.md](ARCHITECTURE.md#3-interaction-diagrams).

### More CLI commands

The CLI uses [rich](https://github.com/Textualize/rich) for coloured output and
tables, and adds:

- **`update <id>`** — edit an existing item interactively (re-encrypts and bumps
  the version).
- **`history <id>`** — show the local change history of an item.
- **`logout`** — clear the stored token, cache, and history.
- **`export <file>` / `import <file>`** — save the local cache to a JSON file and
  load it back (local only, no sync).
- **OTP (one-time passwords):** add an item with `--type otp`, then `otp <id>`
  prints the current TOTP code and `verify-otp <id> <code>` checks a code.
- **`tui`** — launch an interactive, menu-driven terminal UI.

```bash
python cli.py update 1
python cli.py history 1
python cli.py export backup.json
python cli.py import backup.json
python cli.py add --type otp --content "OTP_SECRET" --meta site=github
python cli.py otp 1
python cli.py verify-otp 1 123456
python cli.py tui
python cli.py logout
```

### Metadata

Any item can carry free-form **metadata** — arbitrary `key=value` pairs passed
with `--meta`. Metadata is stored as JSON on the server and is **not encrypted**
(it is meant for labels/search — website, account, bank — not for secrets), and
it is returned in both `list` and `get` responses.

```bash
python cli.py add --type password --content "s3cret" --meta site=github --meta user=alice
```

---

## Binary usage

GitHub Actions builds standalone CLI binaries for Windows and Linux. Download
the artifact for your OS from the repository Actions / Releases page, then point
the binary to the running backend.

Linux:

```bash
chmod +x ./gophkeeper-linux
export GOPHKEEPER_SERVER=http://10.93.27.17
./gophkeeper-linux help
./gophkeeper-linux login
./gophkeeper-linux list --refresh
```

macOS:

```bash
chmod +x ./gophkeeper-macos
export GOPHKEEPER_SERVER=http://10.93.27.17
./gophkeeper-macos help
./gophkeeper-macos login
./gophkeeper-macos list --refresh
```

Windows PowerShell:

```powershell
$env:GOPHKEEPER_SERVER = "http://10.93.27.17"
.\gophkeeper-windows.exe help
.\gophkeeper-windows.exe login
.\gophkeeper-windows.exe list --refresh
```

To use another backend, replace `http://10.93.27.17` with the target server URL.
For isolated local clients on the same machine, set `GOPHKEEPER_HOME` to a
different folder.

---

## Environment variables

Settings are read from environment variables (see `.env.example`). Use `.env`
to configure local Docker runs, VM deployment, database credentials and the
published API port.

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
- ✅ Secrets CRUD (`add` / `list` / `get` / `delete`) + incremental `/items/sync` + `/items/versions`
- ✅ Real cryptography (Argon2id hashing, ChaCha20-Poly1305 encryption)
- ✅ Local cache for the CLI (`list` from cache, `--refresh`, offline fallback)
- ✅ Version conflicts (Last-Write-Wins, `409`): CLI background check + auto-retry
- ✅ CLI `update` / `history` / `logout` / `version` commands
- ✅ Full CLI UX with `rich` (colours, tables, interactive prompts) + `tui` menu
- ✅ Data types incl. `otp` (TOTP): `otp` / `verify-otp`
- ✅ `export` / `import` of the local cache (JSON)
- ✅ Binary builds (Windows / Linux) via PyInstaller (GitHub Actions)

---
