"""
Terminal UI (TUI) for GophKeeper — a menu-driven alternative to the CLI.

Run:  python tui.py        (or: python cli.py tui)

Reuses the CLI's auth/token/crypto/cache helpers and talks to the same server.
The API layer (api_* functions) is kept free of prompts so it can be unit-tested.
"""

import sys

import requests

import cli
from crypto_interface import decrypt_data, encrypt_data

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, IntPrompt, Prompt
    from rich.table import Table
except ImportError:  # pragma: no cover
    print("The TUI needs 'rich'. Install it with:  pip install rich")
    sys.exit(1)

console = Console()

TYPES = ["password", "card", "text", "binary"]


# ---------------- status helpers ----------------
def ok(msg):
    console.print(f"[bold green]OK[/] {msg}")


def err(msg):
    console.print(f"[bold red]Error:[/] {msg}")


def info(msg):
    console.print(f"[cyan]{msg}[/]")


def _detail(response):
    try:
        return response.json().get("detail", f"HTTP {response.status_code}")
    except Exception:
        return f"HTTP {response.status_code}"


# ---------------- API layer (no prompts -> unit-testable) ----------------
def api_login(login, password):
    r = requests.post(
        f"{cli.SERVER_URL}/login", json={"login": login, "password": password}
    )
    if r.status_code == 200:
        return r.json().get("access_token"), None
    if r.status_code == 401:
        return None, "invalid login or password"
    return None, _detail(r)


def api_list():
    r = requests.get(f"{cli.SERVER_URL}/items", headers=cli.get_headers())
    if r.status_code == 200:
        return r.json(), None
    return None, _detail(r)


def api_get(item_id):
    r = requests.get(f"{cli.SERVER_URL}/items/{item_id}", headers=cli.get_headers())
    if r.status_code == 200:
        return r.json(), None
    if r.status_code == 404:
        return None, f"item {item_id} not found"
    return None, _detail(r)


def api_add(item_type, content_bytes, metadata, key):
    payload = {
        "type": item_type,
        "content": encrypt_data(content_bytes, key).hex(),
        "metadata": metadata,
    }
    r = requests.post(
        f"{cli.SERVER_URL}/items", json=payload, headers=cli.get_headers()
    )
    if r.status_code == 201:
        return r.json(), None
    return None, _detail(r)


def api_update(item_id, content_bytes, metadata, version, key):
    payload = {
        "content": encrypt_data(content_bytes, key).hex(),
        "metadata": metadata,
        "version": version,
    }
    r = requests.put(
        f"{cli.SERVER_URL}/items/{item_id}", json=payload, headers=cli.get_headers()
    )
    if r.status_code == 200:
        return r.json(), None
    if r.status_code == 409:
        return None, "version conflict — refresh and try again"
    if r.status_code == 404:
        return None, f"item {item_id} not found"
    return None, _detail(r)


def api_delete(item_id):
    r = requests.delete(f"{cli.SERVER_URL}/items/{item_id}", headers=cli.get_headers())
    if r.status_code == 204:
        return True, None
    if r.status_code == 404:
        return False, f"item {item_id} not found"
    return False, _detail(r)


def _decrypt_content(item, key):
    return decrypt_data(bytes.fromhex(item["content"]), key)


# ---------------- interactive flows ----------------
def _require_auth():
    if not cli.load_token():
        err("please log in first (menu option 1)")
        return False
    return True


def _prompt_metadata():
    raw = Prompt.ask("Metadata key=value,key=value (optional)", default="")
    meta = {}
    for pair in (p for p in raw.split(",") if p.strip()):
        if "=" in pair:
            k, v = pair.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta


def _render_items(items):
    if not items:
        info("No items.")
        return
    table = Table(title="Items")
    table.add_column("ID", justify="right")
    table.add_column("Type")
    table.add_column("Version", justify="right")
    table.add_column("Updated")
    for it in items:
        table.add_row(
            str(it["id"]),
            str(it.get("type", "")),
            str(it.get("version", "")),
            (it.get("updated_at") or "")[:19],
        )
    console.print(table)


def flow_login():
    login = Prompt.ask("Login")
    password = Prompt.ask("Password", password=True)
    try:
        token, error = api_login(login, password)
    except requests.exceptions.ConnectionError:
        err("could not connect to server")
        return
    if error:
        err(error)
        return
    cli.save_token(token)
    cli.cache.clear()
    ok("logged in")


def flow_list():
    if not _require_auth():
        return
    try:
        items, error = api_list()
    except requests.exceptions.ConnectionError:
        cached = cli.cache.list_items()
        if cached:
            info("(offline — showing cached items)")
            _render_items(cached)
        else:
            err("could not connect to server")
        return
    if error:
        err(error)
        return
    cli.cache.sync(items)
    _render_items(items)


def flow_view():
    if not _require_auth():
        return
    item_id = IntPrompt.ask("Item id")
    try:
        item, error = api_get(item_id)
    except requests.exceptions.ConnectionError:
        err("could not connect to server")
        return
    if error:
        err(error)
        return
    cli.cache.upsert(item)
    key = cli.derive_encryption_key(Prompt.ask("Master password", password=True))
    try:
        content = _decrypt_content(item, key)
    except Exception:
        err("could not decrypt (wrong master password?)")
        return
    header = (
        f"[bold]#{item['id']}[/]  type={item['type']}  version={item['version']}\n"
        f"metadata={item.get('metadata', {})}\n\n"
    )
    try:
        body = content.decode("utf-8")
    except UnicodeDecodeError:
        body = f"<binary, {len(content)} bytes>"
    console.print(Panel(header + body, title=f"Item {item['id']}"))


def flow_add():
    if not _require_auth():
        return
    item_type = Prompt.ask("Type", choices=TYPES, default="text")
    content = Prompt.ask("Content")
    metadata = _prompt_metadata()
    key = cli.derive_encryption_key(Prompt.ask("Master password", password=True))
    try:
        item, error = api_add(item_type, content.encode("utf-8"), metadata, key)
    except requests.exceptions.ConnectionError:
        err("could not connect to server")
        return
    if error:
        err(error)
        return
    cli.cache.upsert(item)
    ok(f"created item {item['id']} (version {item['version']})")


def flow_update():
    if not _require_auth():
        return
    item_id = IntPrompt.ask("Item id")
    try:
        current, error = api_get(item_id)
    except requests.exceptions.ConnectionError:
        err("could not connect to server")
        return
    if error:
        err(error)
        return
    content = Prompt.ask("New content")
    metadata = _prompt_metadata()
    key = cli.derive_encryption_key(Prompt.ask("Master password", password=True))
    try:
        item, error = api_update(
            item_id, content.encode("utf-8"), metadata, current["version"], key
        )
    except requests.exceptions.ConnectionError:
        err("could not connect to server")
        return
    if error:
        err(error)
        return
    cli.cache.upsert(item)
    ok(f"updated item {item['id']} (version {item['version']})")


def flow_delete():
    if not _require_auth():
        return
    item_id = IntPrompt.ask("Item id")
    if not Confirm.ask(f"Delete item {item_id}?", default=False):
        info("cancelled")
        return
    try:
        deleted, error = api_delete(item_id)
    except requests.exceptions.ConnectionError:
        err("could not connect to server")
        return
    if error:
        err(error)
        return
    if deleted:
        cli.cache.remove(item_id)
        ok(f"deleted item {item_id}")

def flow_logout():
    cli.logout()


def flow_help():
    table = Table(title="Available Commands", show_header=True)
    table.add_column("Option", justify="center", style="bold")
    table.add_column("Command")
    table.add_column("Description")
    rows = [
        ("1", "Login",       "Authenticate with your username and password"),
        ("2", "List items",  "Show all your stored secrets"),
        ("3", "View item",   "Decrypt and display a single item by ID"),
        ("4", "Add item",    "Create a new encrypted secret"),
        ("5", "Update item", "Edit the content or metadata of an existing item"),
        ("6", "Delete item", "Permanently remove an item"),
        ("7", "Logout",      "Clear your session token and local cache"),
        ("h", "Help",        "Show this help screen"),
        ("0", "Exit",        "Quit the TUI"),
    ]
    for opt, cmd, desc in rows:
        table.add_row(opt, cmd, desc)
    console.print(table)


MENU = [
    ("1", "Login",       flow_login),
    ("2", "List items",  flow_list),
    ("3", "View item",   flow_view),
    ("4", "Add item",    flow_add),
    ("5", "Update item", flow_update),
    ("6", "Delete item", flow_delete),
    ("7", "Logout",      flow_logout),
    ("h", "Help",        flow_help),
    ("0", "Exit",        None),
]

def main():
    console.print(Panel.fit("[bold]GophKeeper TUI[/]", subtitle=cli.SERVER_URL))
    actions = {key: fn for key, _, fn in MENU}
    while True:
        console.print()
        for key, label, _ in MENU:
            console.print(f"  [bold]{key}[/]  {label}")
        try:
            choice = Prompt.ask("Select", choices=[k for k, _, _ in MENU], default="0")
        except (EOFError, KeyboardInterrupt):
            console.print()
            info("bye")
            return
        if choice in ("0", "q", "Q"):
            info("bye")
            return
        try:
            actions[choice]()
        except KeyboardInterrupt:
            console.print()
            info("cancelled")
        except Exception as exc:  # never crash the menu; always return to it
            err(f"unexpected error: {exc}")


if __name__ == "__main__":
    main()
