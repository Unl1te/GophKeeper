#!/usr/bin/env bash
#
# GophKeeper — two-client demo (issue #19)
# ------------------------------------------------------------------------
# Simulates two independent CLI "devices" sharing one account:
#
#   1. Registers two users: `alice` (the account we actually demo with)
#      and `bob` (used only at the end to prove item isolation between
#      accounts — the "two users" the task asks for).
#   2. Starts two independent CLI instances for alice ("Client A" and
#      "Client B") using GOPHKEEPER_HOME, which cli.py reads specifically
#      to support running several clients side by side.
#   3. Client A creates an item.
#   4. Client A "modifies" it. There is currently no `update` command in
#      cli.py (only health/register/login/add/list/get/delete exist) even
#      though the server exposes PUT /items/{id}. So the demo talks to
#      that endpoint directly, re-using the exact same crypto module and
#      fixed salt cli.py uses internally, so the result is something a
#      real client can decrypt.
#   5. Client B calls `list --refresh` and `get` and must see the new
#      content and the bumped version.
#   6. Bob tries to fetch the same item id and must get a 404 (item is
#      private to alice's account).
#
#   GOPHKEEPER_SERVER   Base URL of a running backend (default: see below)
#   REPO_DIR            Path to the GophKeeper checkout (default: this
#                        script's directory)
# ------------------------------------------------------------------------

set -euo pipefail

SERVER_URL="${GOPHKEEPER_SERVER:-http://localhost}"
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

if [[ ! -f "$REPO_DIR/cli.py" ]]; then
    echo "cli.py not found in $REPO_DIR — set REPO_DIR to your GophKeeper checkout." >&2
    exit 1
fi

WORKDIR="$(mktemp -d /tmp/gophkeeper-demo.XXXXXX)"
CLIENT_A_HOME="$WORKDIR/client_a"
CLIENT_B_HOME="$WORKDIR/client_b"
BOB_HOME="$WORKDIR/bob"
mkdir -p "$CLIENT_A_HOME" "$CLIENT_B_HOME" "$BOB_HOME"

STAMP=$(date +%s)
ALICE_LOGIN="alice_${STAMP}"
BOB_LOGIN="bob_${STAMP}"
PASSWORD="Sup3rSecret!1"
MASTER_PASSWORD="MasterPass123!"
ORIGINAL_CONTENT="hello from client A"
UPDATED_CONTENT="updated by client A — v2 payload"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo -e "\n${YELLOW}==>${NC} $*"; }
ok()   { echo -e "${GREEN}  ok:${NC} $*"; }
fail() { echo -e "${RED}  FAIL:${NC} $*"; cleanup; exit 1; }
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

# cli.py prompts for passwords with getpass, which prefers to open /dev/tty
# directly (bypassing a piped stdin) whenever a controlling terminal is
# available — i.e. whenever this script itself is run from an interactive
# terminal, not just in CI. Detaching from the controlling terminal via
# os.setsid() makes getpass fall back to stdin, which is what lets us script
# register/login/add/get non-interactively either way.
#
# We deliberately don't shell out to the external `setsid` command: it's a
# GNU/util-linux tool that isn't installed on macOS by default. os.setsid()
# is the underlying POSIX syscall and is available via Python's `os` module
# on both Linux and macOS, so we use a tiny inline wrapper instead. Using
# `python3 -c` (not a heredoc) is important here: a heredoc would itself
# consume fd 0, replacing the piped register/login input before the real
# cli.py process ever sees it. `-c` reads the wrapper's own code from the
# argv instead, leaving stdin untouched and intact all the way through to
# the exec'd cli.py process.
PYRUN() {
    python3 -c '
import os
import sys

try:
    os.setsid()
except OSError:
    pass  # already a session/process-group leader — nothing to detach

os.execvp("python3", ["python3"] + sys.argv[1:])
' "$@"
}

run_a() { GOPHKEEPER_HOME="$CLIENT_A_HOME" GOPHKEEPER_SERVER="$SERVER_URL" PYRUN "$REPO_DIR/cli.py" "$@"; }
run_b() { GOPHKEEPER_HOME="$CLIENT_B_HOME" GOPHKEEPER_SERVER="$SERVER_URL" PYRUN "$REPO_DIR/cli.py" "$@"; }
run_bob() { GOPHKEEPER_HOME="$BOB_HOME" GOPHKEEPER_SERVER="$SERVER_URL" PYRUN "$REPO_DIR/cli.py" "$@"; }

step "0. Checking server health at $SERVER_URL"
UP=0
for i in $(seq 1 10); do
    if curl -sf "$SERVER_URL/health" 2>/dev/null | grep -q '"status":"ok"'; then
        UP=1
        break
    fi
    sleep 1
done
[[ "$UP" -eq 1 ]] || fail "server did not respond at $SERVER_URL/health (is docker-compose up?)"
ok "server is up"

step "1. Registering two users: '$ALICE_LOGIN' and '$BOB_LOGIN'"
printf '%s\n%s\n' "$ALICE_LOGIN" "$PASSWORD" | run_a register
printf '%s\n%s\n' "$BOB_LOGIN" "$PASSWORD"   | run_bob register

step "2. Logging in Client A and Client B as the SAME user ('$ALICE_LOGIN') — two devices, one account"
printf '%s\n%s\n' "$ALICE_LOGIN" "$PASSWORD" | run_a login
printf '%s\n%s\n' "$ALICE_LOGIN" "$PASSWORD" | run_b login
printf '%s\n%s\n' "$BOB_LOGIN" "$PASSWORD"   | run_bob login

step "3. Client A creates an item"
ADD_OUTPUT=$(printf '%s\n' "$MASTER_PASSWORD" | run_a add --type text --content "$ORIGINAL_CONTENT" --meta demo=two-clients)
echo "$ADD_OUTPUT"
ITEM_ID=$(echo "$ADD_OUTPUT" | grep -oE 'id: [0-9]+' | grep -oE '[0-9]+' | head -1)
BASE_VERSION=$(echo "$ADD_OUTPUT" | grep -oE 'version: [0-9]+' | grep -oE '[0-9]+' | head -1)
[[ -n "$ITEM_ID" && -n "$BASE_VERSION" ]] || fail "could not parse item id/version from add output"
ok "created item #$ITEM_ID at version $BASE_VERSION"

step "4. Client B pulls the item BEFORE the update (sanity check)"
BEFORE=$(printf '%s\n' "$MASTER_PASSWORD" | run_b get "$ITEM_ID")
echo "$BEFORE"
echo "$BEFORE" | grep -qF "$ORIGINAL_CONTENT" || fail "Client B did not see the original content"
ok "Client B sees the original content"

step "5. Client A modifies the item (direct PUT /items/{id} — no CLI 'update' command exists yet)"
PYTHONPATH="$REPO_DIR" MASTER_PASSWORD="$MASTER_PASSWORD" SERVER_URL="$SERVER_URL" \
CONFIG_FILE="$CLIENT_A_HOME/config.json" \
python3 - "$ITEM_ID" "$BASE_VERSION" "$UPDATED_CONTENT" <<'PYEOF'
import json, os, sys
import requests
from crypto_interface import derive_key, encrypt_data

item_id, base_version, new_content = sys.argv[1], int(sys.argv[2]), sys.argv[3]
server = os.environ["SERVER_URL"]
master_password = os.environ["MASTER_PASSWORD"]

with open(os.environ["CONFIG_FILE"]) as f:
    token = json.load(f)["token"]

# Same fixed salt cli.py's derive_encryption_key() uses, so real clients
# (Client B below) can decrypt this with their own master password.
salt = b"gophkeeper_salt_16bytes"
key = derive_key(master_password, salt)
encrypted = encrypt_data(new_content.encode("utf-8"), key)

resp = requests.put(
    f"{server}/items/{item_id}",
    json={
        "content": encrypted.hex(),
        "metadata": {"demo": "two-clients", "edited": "true"},
        "version": base_version,
    },
    headers={"Authorization": f"Bearer {token}"},
)
print(f"PUT /items/{item_id} -> {resp.status_code}: {resp.text}")
sys.exit(0 if resp.status_code == 200 else 1)
PYEOF
PUT_RC=$?
set -e
[[ $PUT_RC -eq 0 ]] || fail "direct update via PUT /items/$ITEM_ID failed"
ok "item #$ITEM_ID updated by Client A"

step "6. Client B refreshes its cache and checks it now sees the update"
run_b list --refresh
AFTER=$(printf '%s\n' "$MASTER_PASSWORD" | run_b get "$ITEM_ID")
echo "$AFTER"
echo "$AFTER" | grep -qF "$UPDATED_CONTENT" || fail "Client B did not see the updated content"
echo "$AFTER" | grep -qE "Version: $((BASE_VERSION + 1))" || fail "Client B did not see the bumped version"
ok "Client B sees the updated content and version $((BASE_VERSION + 1))"

step "7. Bob (a different account) must NOT be able to see alice's item"
set +e
BOB_ATTEMPT=$(printf '%s\n' "$MASTER_PASSWORD" | run_bob get "$ITEM_ID" 2>&1)
set -e
echo "$BOB_ATTEMPT"
echo "$BOB_ATTEMPT" | grep -qi "not found" || fail "expected bob to get a 404/not-found for alice's item"
ok "item isolation between accounts confirmed"

echo -e "\n${GREEN}All two-client demo steps passed.${NC}"
