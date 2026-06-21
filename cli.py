import sys
import os
import json
import requests

SERVER_URL = "http://localhost"
CONFIG_DIR = os.path.expanduser("~/.gophkeeper")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


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
    password = input("password: ")
    try:
        response = requests.post(
            f"{SERVER_URL}/register",
            json={"login": login, "password": password}
        )
        if response.status_code == 201:
            data = response.json()
            print(data.get("message", "Registered successfully"))
        elif response.status_code == 409:
            print(f"Error: user '{login}' already exists")
        else:
            print(f"Error: {response.status_code} — {response.json().get('detail', 'something went wrong')}")
    except requests.exceptions.ConnectionError:
        print("Error: could not connect to server")


def login():
    login_input = input("login: ")
    password = input("password: ")
    try:
        response = requests.post(
            f"{SERVER_URL}/login",
            json={"login": login_input, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            save_token(token)
            print("Logged in successfully")
        elif response.status_code == 401:
            print("Error: invalid login or password")
        else:
            print(f"Error: {response.status_code} — {response.json().get('detail', 'something went wrong')}")
    except requests.exceptions.ConnectionError:
        print("Error: could not connect to server")


def upload():
    print("Not implemented")


def download():
    print("Not implemented")


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
  upload    upload a secret or file
  download  download a secret or file
  history   view history of changes
  version   show version and build date
  help      show this help message

Usage: python cli.py <command>
"""
    )


COMMANDS = {
    "health": health,
    "register": register,
    "login": login,
    "upload": upload,
    "download": download,
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
