"""
QueryMind — Health Check Router
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, UTC

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str = "0.1.0"
    service: str = "QueryMind API"


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/")
async def root():
    return {"message": "QueryMind API is running", "docs": "/docs"}
