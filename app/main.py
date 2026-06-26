from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import health_router, login_router, register_router, items_router

app = FastAPI(
    title="GophKeeper API",
    description="Backend for secure secret storage",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="")
app.include_router(register_router, prefix="")
app.include_router(login_router, prefix="")
app.include_router(items_router, prefix="")


@app.get("/")
async def root():
    return {"message": "GophKeeper server is running"}
