import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db"
    )

    # JWT
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "your-secret-key-here-change-in-production"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    )

    # App
    APP_NAME: str = "GophKeeper"
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"


settings = Settings()
