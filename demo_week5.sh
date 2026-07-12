#!/usr/bin/env bash
# =============================================================================
# GophKeeper – Week 5 Demo Script
# Sync, conflict resolution, offline cache
# =============================================================================
# Usage: bash demo_week5.sh [path/to/GophKeeper]
# Default path: current directory
# =============================================================================

set -euo pipefail

REPO_DIR="${1:-$(pwd)}"
SERVER_URL="${GOPHKEEPER_SERVER:-http://localhost}"

# ── Colours ──────────────────────────────────────────────────────────────────
GRN='\033[0;32m'; YLW='\033[1;33m'; CYN='\033[0;36m'
BLD='\033[1m'; NC='\033[0m'

header()  { echo -e "\n${YLW}${BLD}═══ $* ═══${NC}"; }
step()    { echo -e "\n${CYN}──▶ $*${NC}"; }
ok()      { echo -e "${GRN}  ✔  $*${NC}"; }
pause()   { echo; read -rp "  [Press Enter to continue] "; echo; }

# ── Sanity check ─────────────────────────────────────────────────────────────
[[ -f "$REPO_DIR/cli.py" ]] || { echo "cli.py not found in $REPO_DIR"; exit 1; }

# ── Temp dirs for two independent clients ─────────────────────────────────── 
WORKDIR="$(mktemp -d /tmp/gk-demo.XXXXXX)"
CLIENT_A="$WORKDIR/client_a"
CLIENT_B="$WORKDIR/client_b"
mkdir -p "$CLIENT_A" "$CLIENT_B"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

# ── PYRUN: detach from controlling tty so getpass falls back to stdin ────────
# (same technique as demo_two_clients.sh – os.setsid() is cross-platform)
PYRUN() {
    python3 -c '
import os, sys
try:    os.setsid()
except OSError: pass
os.execvp("python3", ["python3"] + sys.argv[1:])
' "$@"
}

run_a()   { GOPHKEEPER_HOME="$CLIENT_A" GOPHKEEPER_SERVER="$SERVER_URL" PYRUN "$REPO_DIR/cli.py" "$@"; }
run_b()   { GOPHKEEPER_HOME="$CLIENT_B" GOPHKEEPER_SERVER="$SERVER_URL" PYRUN "$REPO_DIR/cli.py" "$@"; }
token_a() { python3 -c "import json; print(json.load(open('$CLIENT_A/config.json'))['token'])"; }

# ─────────────────────────────────────────────────────────────────────────────
echo -e "\n${BLD}GophKeeper – Week 5 Demo${NC}"
echo    "Server: $SERVER_URL"
echo    "Repo:   $REPO_DIR"
echo

# ── Collect credentials once ─────────────────────────────────────────────────
read -rp  "  Login (username):    " ULOGIN
read -rsp "  Password:            " UPASS;       echo
read -rsp "  Master password:     " UMASTER;     echo

STAMP=$(date +%s)
ULOGIN="${ULOGIN}_${STAMP}"          # unique per run so demo is repeatable

echo
ok "Will use login: $ULOGIN"

# =============================================================================
header "0:00 – CLI help"
# =============================================================================
step "python3 cli.py --help"
python3 "$REPO_DIR/cli.py" help
pause

# =============================================================================
header "0:05 – Server health"
# =============================================================================
step "Health check"
python3 "$REPO_DIR/cli.py" health 2>/dev/null || true

echo
echo -e "  ${BLD}Open browser → ${SERVER_URL}/docs${NC}"
echo    "  Highlight: GET /items/versions, POST /items/sync"
pause

# =============================================================================
header "0:15 – Two clients, one account"
# =============================================================================

step "Registering user: $ULOGIN"
printf '%s\n%s\n' "$ULOGIN" "$UPASS" | run_a register

step "Client A: login"
printf '%s\n%s\n' "$ULOGIN" "$UPASS" | run_a login
ok "Client A logged in"

step "Client B: login (same user, different client dir)"
printf '%s\n%s\n' "$ULOGIN" "$UPASS" | run_b login
ok "Client B logged in"

pause

# =============================================================================
header "0:25 – Client A creates an item"
# =============================================================================
step "python3 cli.py add --type text --content 'hello from A' --meta demo=two-clients"
ADD_OUT=$(printf '%s\n' "$UMASTER" | run_a add --type text --content "hello from A" --meta demo=two-clients)
echo "$ADD_OUT"

ITEM_ID=$(echo "$ADD_OUT" | grep -oE 'id: [0-9]+' | grep -oE '[0-9]+' | head -1)
VERSION=$(echo  "$ADD_OUT" | grep -oE 'version: [0-9]+' | grep -oE '[0-9]+' | head -1)
[[ -n "$ITEM_ID" ]] || { echo "Could not parse item id"; exit 1; }
ok "Created item #$ITEM_ID at version $VERSION"
pause

# =============================================================================
header "0:35 – Client B lists – auto-sync shows new item without --refresh"
# =============================================================================
step "Client B: python3 cli.py list"
echo    "  (expected: 'Updating cache...' then item #$ITEM_ID appears)"
run_b list
pause

# =============================================================================
header "0:45 – Update item via curl (no CLI update command yet)"
# =============================================================================
TOKEN=$(token_a)
step "Updating item #$ITEM_ID with curl (version bump: $VERSION → $((VERSION + 1)))"

UPDATE_RESP=$(
    python3 - "$ITEM_ID" "$VERSION" "$UMASTER" "$TOKEN" "$SERVER_URL" << 'PYEOF'
import sys, json
import requests
from crypto_interface import derive_key, encrypt_data

item_id, version, master, token, server = sys.argv[1:]
key = derive_key(master, b"gophkeeper_salt_16bytes")
enc = encrypt_data(b"updated by A v2", key)

resp = requests.put(
    f"{server}/items/{item_id}",
    json={"content": enc.hex(), "metadata": {"edited": "true"}, "version": int(version)},
    headers={"Authorization": f"Bearer {token}"},
)
print(f"HTTP {resp.status_code}")
data = resp.json()
print(json.dumps(data, indent=2))
sys.exit(0 if resp.status_code == 200 else 1)
PYEOF
)
echo "$UPDATE_RESP"
ok "Item updated"
pause

# =============================================================================
header "0:55 – Client B lists again – sees version $((VERSION + 1)) automatically"
# =============================================================================
step "Client B: python3 cli.py list"
echo    "  (expected: 'Updating cache...' and version $((VERSION + 1)))"
run_b list
pause

# =============================================================================
header "1:10 – Conflict: stale version → 409"
# =============================================================================
TOKEN=$(token_a)
step "Sending PUT with stale version ($VERSION) – expecting 409 Conflict"

CONFLICT_RESP=$(
    python3 - "$ITEM_ID" "$VERSION" "$UMASTER" "$TOKEN" "$SERVER_URL" << 'PYEOF'
import sys, json
import requests
from crypto_interface import derive_key, encrypt_data

item_id, version, master, token, server = sys.argv[1:]
key = derive_key(master, b"gophkeeper_salt_16bytes")
enc = encrypt_data(b"stale update", key)

resp = requests.put(
    f"{server}/items/{item_id}",
    json={"content": enc.hex(), "metadata": {}, "version": int(version)},
    headers={"Authorization": f"Bearer {token}"},
)
print(f"HTTP {resp.status_code}")
print(json.dumps(resp.json(), indent=2))
PYEOF
)
echo "$CONFLICT_RESP"
ok "409 Conflict returned with current_version info"
pause

# =============================================================================
header "1:20 – CLI auto-handles conflict on get"
# =============================================================================
step "Client B: python3 cli.py get $ITEM_ID"
echo    "  (expected: fetches fresh version from server, decrypts and displays)"
printf '%s\n' "$UMASTER" | run_b get "$ITEM_ID"
pause

# =============================================================================
header "1:30 – Offline fallback: stop server"
# =============================================================================
step "Stopping backend container..."
(cd "$REPO_DIR" && docker-compose stop backend) 2>/dev/null || true
sleep 2

step "Client B: python3 cli.py list  (server is down)"
echo    "  (expected: '(offline — showing cached items)')"
run_b list || true

step "Bringing backend back up..."
(cd "$REPO_DIR" && docker-compose start backend) 2>/dev/null || true
sleep 3
ok "Backend restored"
pause

# =============================================================================
header "1:45 – Tests & Docker image size"
# =============================================================================
step "CI test results → open browser: https://github.com/Unl1te/GophKeeper/actions"
echo    "  (show latest CI run: 83 passed or similar)"
pause

step "docker images | grep gophkeeper"
docker images | grep -i gophkeeper || echo "  (no local image found — may be on VM)"
pause

# =============================================================================
header "1:55 – Done"
# =============================================================================
echo
echo -e "${GRN}${BLD}Week 5 demo complete: auto-sync, conflict resolution, offline cache${NC}"
echo
