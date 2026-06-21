from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    login: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


class RegisterResponse(BaseModel):
    message: str


class LoginRequest(BaseModel):
    login: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
