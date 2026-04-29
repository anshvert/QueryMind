"""
Data source CRUD + test + schema crawl endpoints.
"""
from datetime import datetime, UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.connectors import get_connector
from backend.core.database import get_db
from backend.schema_registry.models import DataSourceModel, SchemaSnapshotModel
from backend.security.encryption import decrypt_credentials, encrypt_credentials
from backend.schema_registry.embeddings import embed_and_store_schema

router = APIRouter()


class CreateSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: str
    description: str = ""
    credentials: dict


class SourceResponse(BaseModel):
    id: str
    name: str
    source_type: str
    description: str
    is_active: bool
    last_schema_crawl: datetime | None
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(payload: CreateSourceRequest, db: AsyncSession = Depends(get_db)):
    encrypted = encrypt_credentials(payload.credentials)
    model = DataSourceModel(
        name=payload.name,
        source_type=payload.source_type,
        description=payload.description,
        encrypted_credentials=encrypted,
        is_active=True,
    )
    db.add(model)
    await db.flush()
    await db.refresh(model)
    return SourceResponse(
        id=str(model.id),
        name=model.name,
        source_type=model.source_type,
        description=model.description,
        is_active=model.is_active,
        last_schema_crawl=model.last_schema_crawl,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


@router.get("", response_model=list[SourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(DataSourceModel).where(DataSourceModel.is_active.is_(True)))
    items = rows.scalars().all()
    return [
        SourceResponse(
            id=str(m.id),
            name=m.name,
            source_type=m.source_type,
            description=m.description,
            is_active=m.is_active,
            last_schema_crawl=m.last_schema_crawl,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in items
    ]


@router.post("/{source_id}/test")
async def test_source_connection(source_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        select(DataSourceModel).where(
            DataSourceModel.id == source_id,
            DataSourceModel.is_active.is_(True),
        )
    )
    source = row.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    credentials = decrypt_credentials(source.encrypted_credentials)
    connector = get_connector(str(source.id), source.source_type, credentials)
    await connector.connect()
    try:
        ok = await connector.test_connection()
    finally:
        await connector.disconnect()
    return {"source_id": str(source.id), "ok": ok}


@router.post("/{source_id}/crawl-schema")
async def crawl_schema(source_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.execute(
        select(DataSourceModel).where(
            DataSourceModel.id == source_id,
            DataSourceModel.is_active.is_(True),
        )
    )
    source = row.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    credentials = decrypt_credentials(source.encrypted_credentials)
    connector = get_connector(str(source.id), source.source_type, credentials)
    await connector.connect()
    try:
        schema = await connector.get_schema()
    finally:
        await connector.disconnect()

    # Day 2: Semantic Schema Embedding
    await embed_and_store_schema(schema)

    snapshot = SchemaSnapshotModel(
        source_id=source.id,
        schema_json={
            "source_id": schema.source_id,
            "source_type": schema.source_type.value,
            "database": schema.database,
            "tables": [
                {
                    "name": t.name,
                    "schema": t.schema,
                    "row_count": t.row_count,
                    "columns": [
                        {
                            "name": c.name,
                            "data_type": c.data_type,
                            "nullable": c.nullable,
                            "is_primary_key": c.is_primary_key,
                            "is_foreign_key": c.is_foreign_key,
                            "references": c.references,
                            "sample_values": c.sample_values,
                        }
                        for c in t.columns
                    ],
                }
                for t in schema.tables
            ],
        },
    )
    source.last_schema_crawl = datetime.now(UTC)
    db.add(snapshot)
    db.add(source)
    return {"source_id": str(source.id), "tables": len(schema.tables)}


@router.delete("/{source_id}")
async def delete_source(source_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.execute(select(DataSourceModel).where(DataSourceModel.id == source_id))
    source = row.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.is_active = False
    db.add(source)
    return {"deleted": True, "source_id": str(source.id)}
