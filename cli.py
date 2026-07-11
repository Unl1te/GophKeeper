import argparse
import getpass
import json
import os
import sys

import requests

from rich import print
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

from crypto_interface import derive_key, encrypt_data, decrypt_data
from cli_cache import LocalCache

SERVER_URL = os.environ.get("GOPHKEEPER_SERVER", "http://localhost")
# Config dir holds the token and the local cache. Override with GOPHKEEPER_HOME
# to run several independent clients side by side (e.g. the two-client demo).
CONFIG_DIR = os.environ.get("GOPHKEEPER_HOME") or os.path.expanduser("~/.gophkeeper")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

cache = LocalCache(path=os.path.join(CONFIG_DIR, "cache.json"))

console = Console()


# Token management
def save_token(token: str):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump({"token": token}, f)


def load_token():
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
    return data.get("token")


def get_headers():
    token = load_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def ask_master_password() -> str:
    return getpass.getpass("Master password: ")


def derive_encryption_key(master_password: str) -> bytes:
    salt = b"gophkeeper_salt_16bytes"
    return derive_key(master_password, salt)


def print_error(message: str):
    console.print(f"[bold red]Error:[/bold red] {message}")

def print_success(message: str):
    console.print(f"[bold green]{message}[/bold green]")

def print_warning(message: str):
    console.print(f"[yellow]{message}[/yellow]")


# Background check: fetch /items/versions and refresh cache if needed
def _fetch_versions() -> list | None:
    """Fetch /items/versions from server. Returns list of {id, version, updated_at} or None on failure."""
    try:
        response = requests.get(f"{SERVER_URL}/items/versions", headers=get_headers())
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
            return None
        else:
            print_error(
                f"{response.status_code} — {response.json().get('detail', 'Unknown error')}"
            )
            return None
    except requests.exceptions.ConnectionError:
        return None  # offline


def _refresh_cache_from_server():
    """Pull full item list from /items and sync the cache."""
    try:
        response = requests.get(f"{SERVER_URL}/items", headers=get_headers())
        if response.status_code == 200:
            cache.sync(response.json())
            print("Cache updated.")
            return True
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
            return False
        else:
            print_error(
                f"{response.status_code} — {response.json().get('detail', 'Unknown error')}"
            )
            return False
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")
        return False


def _check_and_update_cache_if_needed():
    """
    Check server versions via /items/versions.
    If any version differs from cache, update cache.
    Returns True if cache was updated, False otherwise.
    """
    versions = _fetch_versions()
    if versions is None:
        # Server unreachable or error – no update
        return False

    # Compare with cache
    cached_items = cache.list_items()
    cached_versions = {item["id"]: item["version"] for item in cached_items}

    need_update = False
    for v in versions:
        sid = v["id"]
        sver = v["version"]
        cver = cached_versions.get(sid)
        if cver is None or cver != sver:
            need_update = True
            break
    # Also check if server has fewer items (deletions)
    if len(versions) != len(cached_items):
        need_update = True

    if need_update:
        print("Updating cache...")
        return _refresh_cache_from_server()
    return False


# Existing commands
def health():
    try:
        response = requests.get(f"{SERVER_URL}/health")
        data = response.json()
        if data.get("status") == "ok":
            print("OK")
        else:
            print(f"Unexpected response: {data}")
    except requests.exceptions.ConnectionError:
        print("Error: could not connect to server")


def register():
    login = Prompt.ask("Login")
    password = getpass.getpass("password: ")
    try:
        response = requests.post(
            f"{SERVER_URL}/register", json={"login": login, "password": password}
        )
        if response.status_code == 201:
            data = response.json()
            print(data.get("message", "Registered successfully"))
        elif response.status_code == 409:
            print(f"Error: user '{login}' already exists")
        else:
            print(
                f"Error: {response.status_code} — {response.json().get('detail', 'something went wrong')}"
            )
    except requests.exceptions.ConnectionError:
        print("Error: could not connect to server")


def login():
    login_input = input("login: ")
    password = getpass.getpass("password: ")
    try:
        response = requests.post(
            f"{SERVER_URL}/login", json={"login": login_input, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            save_token(token)
            cache.clear()
            print("Logged in successfully")
        elif response.status_code == 401:
            print("Error: invalid login or password")
        else:
            print(
                f"Error: {response.status_code} — {response.json().get('detail', 'something went wrong')}"
            )
    except requests.exceptions.ConnectionError:
        print("Error: could not connect to server")


# Item commands
def add_item():
    parser = argparse.ArgumentParser(prog="cli.py add", add_help=False)
    parser.add_argument(
        "--type", required=True, choices=["password", "card", "text", "binary"]
    )
    parser.add_argument("--meta", action="append", help="metadata in key=value format")
    parser.add_argument("--file", help="read content from file (for binary type)")
    parser.add_argument("--content", help="content string (for text/password/card)")
    args, unknown = parser.parse_known_args(sys.argv[2:])

    metadata = {}
    if args.meta:
        for pair in args.meta:
            if "=" in pair:
                key, value = pair.split("=", 1)
                metadata[key] = value
            else:
                metadata[pair] = True

    content_bytes = None
    if args.file:
        try:
            with open(args.file, "rb") as f:
                content_bytes = f.read()
        except FileNotFoundError:
            print_error(f"File not found: {args.file}")
            return
    elif args.content:
        content_bytes = args.content.encode("utf-8")
    else:
        if args.type == "binary":
            file_path = input("Path to file: ").strip()
            if not file_path:
                print_error("No file provided")
                return
            try:
                with open(file_path, "rb") as f:
                    content_bytes = f.read()
            except FileNotFoundError:
                print_error(f"File not found: {file_path}")
                return
        else:
            content = Prompt.ask("Content")
            content_bytes = content.encode("utf-8")

    if content_bytes is None:
        print_error("No content provided")
        return

    master_password = ask_master_password()
    key = derive_encryption_key(master_password)
    encrypted = encrypt_data(content_bytes, key)

    payload = {
        "type": args.type,
        "content": encrypted.hex(),
        "metadata": metadata,
    }

    try:
        response = requests.post(
            f"{SERVER_URL}/items",
            json=payload,
            headers=get_headers(),
        )
        if response.status_code == 201:
            data = response.json()
            cache.upsert(data)
            print_success(
                f"Item created (id: {data['id']}, version: {data['version']})"
            )
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
        else:
            print_error(
                f"{response.status_code} — {response.json().get('detail', 'Unknown error')}"
            )
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")


def _print_items(items):
    table = Table(title="Stored Items")

    table.add_column("ID", style="cyan")
    table.add_column("Type")
    table.add_column("Version")
    table.add_column("Updated")

    for item in items:
        table.add_row(
            str(item["id"]),
            item["type"],
            str(item["version"]),
            (item.get("updated_at") or "")[:19],
        )

    console.print(table)


def list_items():
    """
    List items from the local cache by default. Use --refresh to pull from server.
    If cache is empty or stale (missing required fields), automatically refresh.
    Falls back to cache if server is unreachable.
    """
    refresh = "--refresh" in sys.argv[2:]
    cached = cache.list_items()

    # If --refresh is given, force fetch from server
    if refresh:
        if _refresh_cache_from_server():
            cached = cache.list_items()
        else:
            # If refresh failed, still try to show what we have
            if not cached:
                print_error("Could not refresh and no cached items")
                return
            print("(offline — showing cached items)")

    # Otherwise, do background check if cache is not empty
    elif cached:
        # Background check: fetch /items/versions and update if needed
        _check_and_update_cache_if_needed()
        cached = cache.list_items()
    else:
        # Cache empty – fetch from server
        if _refresh_cache_from_server():
            cached = cache.list_items()
        else:
            print_error("Could not fetch items")
            return

    if not cached:
        print("No items found")
        return

    _print_items(cached)


def get_item():
    if len(sys.argv) < 3:
        print_error("Usage: python cli.py get <id>")
        return
    item_id = sys.argv[2]

    try:
        response = requests.get(f"{SERVER_URL}/items/{item_id}", headers=get_headers())
        if response.status_code == 200:
            item = response.json()
            cache.upsert(item)
            master_password = ask_master_password()
            key = derive_encryption_key(master_password)

            encrypted_bytes = bytes.fromhex(item["content"])
            decrypted = decrypt_data(encrypted_bytes, key)

            print(f"\nItem #{item['id']}")
            print(f"Type: {item['type']}")
            print(f"Version: {item['version']}")
            print(f"Updated: {item['updated_at']}")
            print(f"Metadata: {item.get('metadata', {})}")
            print("\n--- Content ---")
            try:
                print(decrypted.decode("utf-8"))
            except UnicodeDecodeError:
                print(decrypted.hex())
        elif response.status_code == 404:
            # Remove stale entry from cache
            cache.remove(item_id)
            print_error(
                f"Item {item_id} not found on server (removed from local cache)"
            )
        elif response.status_code == 409:
            # Conflict: server version is newer – refresh cache and retry
            print_error(
                f"Conflict detected for item {item_id}. Refreshing cache and retrying..."
            )
            if _refresh_cache_from_server():
                # After refresh, try again automatically
                get_item()  # recursive retry
            else:
                print_error("Could not refresh cache. Please try again later.")
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
        else:
            print_error(
                f"{response.status_code} — {response.json().get('detail', 'Unknown error')}"
            )
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")


def delete_item():
    if len(sys.argv) < 3:
        print_error("Usage: python cli.py delete <id>")
        return
    item_id = sys.argv[2]

    confirm = Confirm.ask(
        f"Delete item {item_id}?",
        default=False
    )
    
    if not confirm:
        print_warning("Cancelled")
        return

    try:
        response = requests.delete(
            f"{SERVER_URL}/items/{item_id}", headers=get_headers()
        )
        if response.status_code == 204:
            cache.remove(item_id)
            print_success(f"Item {item_id} deleted")
        elif response.status_code == 404:
            cache.remove(item_id)
            print_error(f"Item {item_id} not found (removed from local cache)")
        elif response.status_code == 409:
            # Conflict: server version is newer – refresh cache and retry deletion
            print_error(
                f"Conflict detected for item {item_id}. Refreshing cache and retrying delete..."
            )
            if _refresh_cache_from_server():
                # After refresh, retry deletion (call recursively)
                delete_item()
            else:
                print_error("Could not refresh cache. Please try again later.")
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
        else:
            print_error(
                f"{response.status_code} — {response.json().get('detail', 'Unknown error')}"
            )
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")


def update_item():
    if len(sys.argv) < 3:
        print_error("Usage: update <id>")
        return

    item_id = sys.argv[2]

    response = requests.get(
        f"{SERVER_URL}/items/{item_id}",
        headers=get_headers()
    )

    if response.status_code != 200:
        print_error("Item not found")
        return

    item = response.json()

    master_password = ask_master_password()

    key = derive_encryption_key(master_password)

    try:
        decrypted = decrypt_data(
            bytes.fromhex(item["content"]),
            key
        ).decode("utf-8")
    except Exception:
        print_error("Invalid master password or corrupted data")
        return

    console.print(f"\nCurrent content:\n{decrypted}\n")

    new_content = Prompt.ask(
        "New content",
        default=decrypted
    )

    metadata = item.get("metadata", {})

    for key_name, value in list(metadata.items()):

        metadata[key_name] = Prompt.ask(
            f"{key_name}",
            default=str(value)
        )

    encrypted = encrypt_data(
        new_content.encode(),
        key
    )

    payload = {
        "content": encrypted.hex(),
        "metadata": metadata,
        "version": item["version"]
    }

    response = requests.put(
        f"{SERVER_URL}/items/{item_id}",
        json=payload,
        headers=get_headers()
    )

    if response.status_code == 200:

        updated = response.json()

        cache.upsert(updated)

        print_success(
            f"Item updated (version {updated['version']})"
        )

        return

    if response.status_code == 409:

        print_warning(
            "Item was modified on server. Retrying..."
        )

        return update_item()

    print_error(
        response.json().get(
            "detail",
            "Unknown error"
        )
    )


def export_cache():
    if len(sys.argv) < 3:
        print_error("Usage: export <file>")
        return

    filename = sys.argv[2]

    items = cache.list_items()

    with open(filename, "w", encoding="utf8") as f:
        json.dump(items, f, indent=4)

    print_success(f"Exported {len(items)} items to {filename}")


def import_cache():
    if len(sys.argv) < 3:
        print_error("Usage: import <file>")
        return

    filename = sys.argv[2]

    try:
        with open(filename, "r", encoding="utf8") as f:
            imported = json.load(f)
    except Exception as e:
        print_error(str(e))
        return

    existing = {str(i["id"]): i for i in cache.list_items()}

    for item in imported:
        existing[str(item["id"])] = item

    cache.sync(list(existing.values()))

    print_success(f"Imported {len(imported)} items")


# Stubs and help
def history():
    if len(sys.argv) < 3:
        print_error("Usage: history <id>")
        return

    item_id = sys.argv[2]

    response = requests.get(
        f"{SERVER_URL}/items/{item_id}",
        headers=get_headers()
    )

    if response.status_code != 200:
        print_error("Item not found")
        return

    item = response.json()

    table = Table(title=f"History of item {item_id}")

    table.add_column("Version")
    table.add_column("Updated at")

    table.add_row(
        str(item["version"]),
        item["updated_at"]
    )

    console.print(table)

    console.print(
        "[yellow]Full history is planned for future versions.[/yellow]"
    )


def version():
    try:
        with open("VERSION", "r") as f:
            console.print(f.read())
    except FileNotFoundError:
        console.print("[red]VERSION file not found[/red]")


def help():
    print(
        """
GophKeeper CLI - available commands:

  health    check if the server is running
  register  register a new user
  login     login to your account

  add       add a new item (--type password|card|text|binary --meta key=value)
  list      list all items (from cache; use 'list --refresh' to pull from server)
  get <id>  get and decrypt an item by ID
  update <id>  update an existing item
  delete <id>  delete an item by ID

  export <file>  export local cache to a JSON file
  import <file>  import items from a JSON file into local cache

  history <id>  show item version history
  version   show version and build date
  help      show this help message

Usage: python cli.py <command> [args...]

Examples:
  python cli.py add --type text --content "my secret" --meta note=test
  python cli.py add --type binary --file ./secret.pdf
  python cli.py get 1
  python cli.py update 1
  python cli.py export backup.json
  python cli.py import backup.json
"""
    )


COMMANDS = {
    "health": health,
    "register": register,
    "login": login,
    "add": add_item,
    "list": list_items,
    "get": get_item,
    "update": update_item,
    "delete": delete_item,
    "export": export_cache,
    "import": import_cache,
    "history": history,
    "version": version,
    "help": help,
}


def main():
    if len(sys.argv) < 2:
        print("No command provided. Run 'python cli.py help' to see available commands")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command not in COMMANDS:
        print(
            f"Unknown command: '{command}'. Run 'python cli.py help' to see available commands"
        )
        sys.exit(1)

    COMMANDS[command]()


if __name__ == "__main__":
    main()
