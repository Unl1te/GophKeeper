"""
Temporary JWT stub
Need's to be replaced by real implementation
"""

from datetime import datetime, timedelta
from typing import Optional
import jwt
from app.core.config import settings


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    raise NotImplementedError("Will be implemented")


def decode_token(token: str) -> dict:
    raise NotImplementedError("Will be implemented")
    
    