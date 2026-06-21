from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token
from app.models.models import User
from app.schemas.user import LoginRequest, LoginResponse
import crypto_interface

router = APIRouter(tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate user and return JWT access token.

    - **login**: username
    - **password**: password

    Returns 200 OK with access token, 401 Unauthorized on invalid credentials.
    """
    # Find user
    result = await db.execute(
        select(User).where(User.login == credentials.login)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not crypto_interface.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate JWT
    access_token = create_access_token(data={"sub": user.login, "user_id": user.id})

    return LoginResponse(access_token=access_token, token_type="bearer")