"""
Day 1 chat endpoint: NL question -> SQL generation.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.day1_react import run_day1_react_agent
from backend.core.database import get_db
from backend.schema_registry.models import DataSourceModel
from backend.security.encryption import decrypt_credentials

router = APIRouter()


class ChatRequest(BaseModel):
    source_id: UUID
    question: str = Field(min_length=1)


class ChatResponse(BaseModel):
    source_id: str
    question: str
    sql: str
    reasoning: list[str]


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        select(DataSourceModel).where(
            DataSourceModel.id == payload.source_id,
            DataSourceModel.is_active.is_(True),
        )
    )
    source = row.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    credentials = decrypt_credentials(source.encrypted_credentials)
    result = await run_day1_react_agent(
        source_id=str(source.id),
        source_type=source.source_type,
        credentials=credentials,
        question=payload.question,
    )
    return ChatResponse(
        source_id=str(source.id),
        question=payload.question,
        sql=result["sql"],
        reasoning=result["reasoning"],
    )
