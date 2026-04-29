"""
QueryMind — Abstract DataSource Interface
Every connector must implement this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"
    MONGODB = "mongodb"
    DUCKDB = "duckdb"       # CSV / Parquet


@dataclass
class ColumnMeta:
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: str | None = None     # "table.column"
    description: str = ""
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class TableMeta:
    name: str
    schema: str = "public"
    columns: list[ColumnMeta] = field(default_factory=list)
    row_count: int = 0
    description: str = ""

    def to_ddl(self) -> str:
        """Return a compact DDL representation for prompt injection."""
        col_lines = []
        for col in self.columns:
            pk = " PRIMARY KEY" if col.is_primary_key else ""
            fk = f" REFERENCES {col.references}" if col.is_foreign_key and col.references else ""
            null = "" if col.nullable else " NOT NULL"
            col_lines.append(f"  {col.name} {col.data_type}{pk}{fk}{null}")
        table_ref = f"{self.schema}.{self.name}" if self.schema else self.name
        return f"CREATE TABLE {table_ref} (\n" + ",\n".join(col_lines) + "\n);"


@dataclass
class SchemaInfo:
    source_id: str
    source_type: SourceType
    database: str
    tables: list[TableMeta] = field(default_factory=list)

    def to_prompt_context(self, max_tables: int = 20) -> str:
        """Return a compact schema string for LLM prompts."""
        lines = [f"-- Database: {self.database} ({self.source_type.value})"]
        for table in self.tables[:max_tables]:
            lines.append(table.to_ddl())
        return "\n\n".join(lines)


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: float
    truncated: bool = False          # True if row limit was hit

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, row)) for row in self.rows]


class DataSource(ABC):
    """
    Abstract base class for all QueryMind data source connectors.
    Every connector must implement these methods.
    """

    def __init__(self, source_id: str, credentials: dict[str, Any]):
        self.source_id = source_id
        self.credentials = credentials
        self._connected = False

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection and release resources."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the connection is alive. Returns True if healthy."""
        ...

    # ─── Schema Discovery ─────────────────────────────────────────────────────

    @abstractmethod
    async def get_schema(self) -> SchemaInfo:
        """
        Discover and return full schema metadata:
        tables, columns, types, PKs, FKs, row counts, sample values.
        """
        ...

    # ─── Query Execution ──────────────────────────────────────────────────────

    @abstractmethod
    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        max_rows: int = 10000,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        """
        Execute a read-only query and return results.
        Must enforce max_rows limit and timeout.
        """
        ...

    # ─── SQL Dialect ──────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def sql_dialect(self) -> str:
        """Return the SQL dialect string for prompt generation."""
        ...

    # ─── Context Manager Support ──────────────────────────────────────────────

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source_id={self.source_id!r}, connected={self._connected})"
