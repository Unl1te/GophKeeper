from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import crypto_interface
from app.core.database import get_db
from app.models.models import User
from app.schemas.user import RegisterRequest, RegisterResponse

router = APIRouter(tags=["Registration"])


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register(user_data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user.

    - **login**: unique username (min 3 characters)
    - **password**: password (min 6 characters)

    Returns 201 Created on success, 409 Conflict if login already exists.
    """
    # Check if user already exists
    existing_user = await db.execute(select(User).where(User.login == user_data.login))
    if existing_user.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with login '{user_data.login}' already exists",
        )

    # Hash password
    hashed = crypto_interface.hash_password(user_data.password)

    # Create user
    new_user = User(
        login=user_data.login,
        hashed_password=hashed,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return RegisterResponse(message=f"User '{user_data.login}' registered successfully")
