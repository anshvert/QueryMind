"""
QueryMind — Data Source SQLAlchemy Models
"""
import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, String, DateTime, Text, Boolean, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from backend.core.database import Base


class DataSourceModel(Base):
    """Persisted data source record with encrypted credentials."""
    __tablename__ = "data_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)   # postgresql, snowflake, bigquery, etc.
    description = Column(Text, default="")
    encrypted_credentials = Column(Text, nullable=False)  # AES-256 encrypted JSON
    is_active = Column(Boolean, default=True)
    last_schema_crawl = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC))

    def __repr__(self):
        return f"<DataSource id={self.id} name={self.name!r} type={self.source_type}>"


class SchemaSnapshotModel(Base):
    """Stores crawled schema metadata for a data source."""
    __tablename__ = "schema_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=False, index=True)
    schema_json = Column(JSON, nullable=False)
    crawled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
