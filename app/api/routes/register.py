from fastapi import APIRouter, HTTPException, status

from app.schemas.user import RegisterRequest, RegisterResponse

router = APIRouter(tags=["Registration"])


@router.post("/register", response_model=RegisterResponse)
async def register(user_data: RegisterRequest):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Registration not implemented yet",
    )
