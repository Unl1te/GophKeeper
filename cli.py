import argparse
import getpass
import json
import os
import sys

import requests
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich import print as rprint

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
    console.print(f"[red]Error: {message}[/red]")


def print_success(message: str):
    console.print(f"[green]Success: {message}[/green]")


# Background check
def _fetch_versions() -> list | None:
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
        return None


def _refresh_cache_from_server():
    try:
        response = requests.get(f"{SERVER_URL}/items", headers=get_headers())
        if response.status_code == 200:
            cache.sync(response.json())
            console.print("[green]Cache updated.[/green]")
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
    versions = _fetch_versions()
    if versions is None:
        if cache.list_items():
            console.print("[yellow](offline — showing cached items)[/yellow]")
        return False

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
    if len(versions) != len(cached_items):
        need_update = True

    if need_update:
        console.print("[yellow]Updating cache...[/yellow]")
        return _refresh_cache_from_server()
    return False


# Existing commands
def health():
    try:
        response = requests.get(f"{SERVER_URL}/health")
        data = response.json()
        if data.get("status") == "ok":
            console.print("[green]OK[/green]")
        else:
            console.print(f"[red]Unexpected response: {data}[/red]")
    except requests.exceptions.ConnectionError:
        print_error("could not connect to server")


def register():
    login = Prompt.ask("login")
    password = getpass.getpass("password: ")
    try:
        response = requests.post(
            f"{SERVER_URL}/register", json={"login": login, "password": password}
        )
        if response.status_code == 201:
            data = response.json()
            console.print(f"[green]{data.get('message', 'Registered successfully')}[/green]")
        elif response.status_code == 409:
            print_error(f"user '{login}' already exists")
        else:
            print_error(
                f"{response.status_code} — {response.json().get('detail', 'something went wrong')}"
            )
    except requests.exceptions.ConnectionError:
        print_error("could not connect to server")


def login():
    login_input = Prompt.ask("login")
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
            console.print("[green]Logged in successfully[/green]")
        elif response.status_code == 401:
            print_error("invalid login or password")
        else:
            print_error(
                f"{response.status_code} — {response.json().get('detail', 'something went wrong')}"
            )
    except requests.exceptions.ConnectionError:
        print_error("could not connect to server")


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
            file_path = Prompt.ask("Path to file")
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
            print_success(f"Item created (id: {data['id']}, version: {data['version']})")
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
        else:
            print_error(
                f"{response.status_code} — {response.json().get('detail', 'Unknown error')}"
            )
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")


def _print_items(items):
    if not items:
        console.print("[yellow]No items found[/yellow]")
        return
    table = Table(title="Your Items", style="bright_blue")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Version", style="green", justify="right")
    table.add_column("Updated At", style="white")
    for item in items:
        updated = (item.get("updated_at") or "")[:19]
        table.add_row(str(item["id"]), item["type"], str(item["version"]), updated)
    console.print(table)


def list_items():
    refresh = "--refresh" in sys.argv[2:]
    cached = cache.list_items()

    if refresh:
        if _refresh_cache_from_server():
            cached = cache.list_items()
        else:
            if not cached:
                print_error("Could not refresh and no cached items")
                return
            console.print("[yellow](offline — showing cached items)[/yellow]")
    elif cached:
        _check_and_update_cache_if_needed()
        cached = cache.list_items()
    else:
        if _refresh_cache_from_server():
            cached = cache.list_items()
        else:
            print_error("Could not fetch items")
            return

    if not cached:
        console.print("[yellow]No items found[/yellow]")
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

            console.print(f"\n[bold cyan]Item #{item['id']}[/bold cyan]")
            console.print(f"Type: [magenta]{item['type']}[/magenta]")
            console.print(f"Version: [green]{item['version']}[/green]")
            console.print(f"Updated: [white]{item['updated_at']}[/white]")
            console.print(f"Metadata: [yellow]{item.get('metadata', {})}[/yellow]")
            console.print("\n[bold]--- Content ---[/bold]")
            try:
                console.print(decrypted.decode("utf-8"))
            except UnicodeDecodeError:
                console.print(decrypted.hex())
        elif response.status_code == 404:
            cache.remove(item_id)
            print_error(f"Item {item_id} not found on server (removed from local cache)")
        elif response.status_code == 409:
            print_error(f"Conflict detected for item {item_id}. Refreshing cache and retrying...")
            if _refresh_cache_from_server():
                get_item()
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

    if not Confirm.ask(f"[yellow]Are you sure you want to delete item {item_id}?[/yellow]", default=False):
        console.print("[yellow]Cancelled[/yellow]")
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
            print_error(f"Conflict detected for item {item_id}. Refreshing cache and retrying delete...")
            if _refresh_cache_from_server():
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


def history():
    console.print("[yellow]History command not yet implemented.[/yellow]")


def version():
    console.print("[yellow]Version command not yet implemented.[/yellow]")


def export_items():
    console.print("[yellow]Export command not yet implemented.[/yellow]")


def import_items():
    console.print("[yellow]Import command not yet implemented.[/yellow]")


def tui():
    from tui import main as tui_main
    tui_main()


def help():
    console.print(
        """
[bold]GophKeeper CLI - available commands:[/bold]

  [cyan]health[/cyan]    check if the server is running
  [cyan]register[/cyan]  register a new user
  [cyan]login[/cyan]     login to your account

  [cyan]add[/cyan]       add a new item (--type password|card|text|binary --meta key=value)
  [cyan]list[/cyan]      list all items (from cache; use 'list --refresh' to pull from server)
  [cyan]get[/cyan]       get and decrypt an item by ID
  [cyan]delete[/cyan]    delete an item by ID

  [cyan]history[/cyan]   view history of changes (stub)
  [cyan]version[/cyan]   show version and build date (stub)
  [cyan]export[/cyan]    export cache to JSON file (stub)
  [cyan]import[/cyan]    import items from JSON file (stub)
  [cyan]tui[/cyan]       launch the interactive terminal UI (menu-driven)
  [cyan]help[/cyan]      show this help message

[bold]Usage:[/bold] python cli.py <command> [args...]
[bold]Examples:[/bold]
  python cli.py add --type text --content "my secret" --meta note=test
  python cli.py add --type binary --file ./secret.pdf
  python cli.py get 1
"""
    )


COMMANDS = {
    "health": health,
    "register": register,
    "login": login,
    "add": add_item,
    "list": list_items,
    "get": get_item,
    "delete": delete_item,
    "history": history,
    "version": version,
    "export": export_items,
    "import": import_items,
    "tui": tui,
    "help": help,
}


def main():
    if len(sys.argv) < 2:
        console.print("[red]No command provided. Run 'python cli.py help' to see available commands[/red]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command not in COMMANDS:
        console.print(f"[red]Unknown command: '{command}'. Run 'python cli.py help' to see available commands[/red]")
        sys.exit(1)

    COMMANDS[command]()


if __name__ == "__main__":
    main()
