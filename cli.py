import sys
import requests

SERVER_URL = "http://localhost:8000"


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
    print("Not implemented")


def login():
    print("Not implemented")


def upload():
    print("Not implemented")


def download():
    print("Not implemented")


def history():
    print("Not implemented")


def help():
    print("""
GophKeeper CLI - available commands:

  health    check if the server is running
  register  register a new user
  login     login to your account
  upload    upload a secret or file
  download  download a secret or file
  history   view history of changes
  help      show this help message

Usage: python cli.py <command>
""")


COMMANDS = {
    "health": health,
    "register": register,
    "login": login,
    "upload": upload,
    "download": download,
    "history": history,
    "help": help,
}


def main():
    if len(sys.argv) < 2:
        print("No command provided. Run 'python cli.py help' to see available commands")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command not in COMMANDS:
        print(f"Unknown command: '{command}'. Run 'python cli.py help' to see available commands")
        sys.exit(1)

    COMMANDS[command]()


if __name__ == "__main__":
    main()
