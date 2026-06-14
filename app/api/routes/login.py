from fastapi import APIRouter, HTTPException, status
from app.schemas.user import LoginRequest, LoginResponse

router = APIRouter(tags=["Authentication"])

@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Login not implemented yet"
    )