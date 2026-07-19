# conftest.py (в корне tests/, если ещё не сделано)
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
