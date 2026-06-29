import json
import os
import sys
import argparse
import getpass

import requests

from crypto_interface import derive_key, encrypt_data, decrypt_data

SERVER_URL = "http://localhost"
CONFIG_DIR = os.path.expanduser("~/.gophkeeper")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


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
    print(f"Error: {message}")


def print_success(message: str):
    print(f"Success: {message}")


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
    login = input("login: ")
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
            print("Logged in successfully")
        elif response.status_code == 401:
            print("Error: invalid login or password")
        else:
            print(
                f"Error: {response.status_code} — {response.json().get('detail', 'something went wrong')}"
            )
    except requests.exceptions.ConnectionError:
        print("Error: could not connect to server")


def add_item():
    parser = argparse.ArgumentParser(prog="cli.py add", add_help=False)
    parser.add_argument("--type", required=True, choices=["password", "card", "text", "binary"])
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
            content = input("Content: ")
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
            print_success(f"Item created (id: {data['id']}, version: {data['version']})")
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
        else:
            print_error(f"{response.status_code} — {response.json().get('detail', 'Unknown error')}")
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")


def list_items():
    try:
        response = requests.get(f"{SERVER_URL}/items", headers=get_headers())
        if response.status_code == 200:
            items = response.json()
            if not items:
                print("No items found")
                return
            print(f"{'ID':<6} {'Type':<10} {'Version':<8} {'Updated At'}")
            print("-" * 50)
            for item in items:
                updated = item["updated_at"][:19]
                print(f"{item['id']:<6} {item['type']:<10} {item['version']:<8} {updated}")
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
        else:
            print_error(f"{response.status_code} — {response.json().get('detail', 'Unknown error')}")
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")


def get_item():
    if len(sys.argv) < 3:
        print_error("Usage: python cli.py get <id>")
        return
    item_id = sys.argv[2]

    try:
        response = requests.get(f"{SERVER_URL}/items/{item_id}", headers=get_headers())
        if response.status_code == 200:
            item = response.json()
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
            print_error(f"Item {item_id} not found")
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
        else:
            print_error(f"{response.status_code} — {response.json().get('detail', 'Unknown error')}")
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")


def delete_item():
    if len(sys.argv) < 3:
        print_error("Usage: python cli.py delete <id>")
        return
    item_id = sys.argv[2]

    confirm = input(f"Are you sure you want to delete item {item_id}? [y/N] ")
    if confirm.lower() != "y":
        print("Cancelled")
        return

    try:
        response = requests.delete(f"{SERVER_URL}/items/{item_id}", headers=get_headers())
        if response.status_code == 204:
            print_success(f"Item {item_id} deleted")
        elif response.status_code == 404:
            print_error(f"Item {item_id} not found")
        elif response.status_code == 401:
            print_error("Not authenticated. Please login first.")
        else:
            print_error(f"{response.status_code} — {response.json().get('detail', 'Unknown error')}")
    except requests.exceptions.ConnectionError:
        print_error("Could not connect to server")


def history():
    print("Not implemented")


def version():
    print("Not implemented")


def help():
    print(
        """
GophKeeper CLI - available commands:

  health    check if the server is running
  register  register a new user
  login     login to your account

  add       add a new item (--type password|card|text|binary --meta key=value)
  list      list all items
  get <id>  get and decrypt an item by ID
  delete <id>  delete an item by ID

  history   view history of changes
  version   show version and build date
  help      show this help message

Usage: python cli.py <command> [args...]
Examples:
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
