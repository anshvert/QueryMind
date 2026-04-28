"""
QueryMind — PostgreSQL Connector
Uses asyncpg for async query execution.
"""
import time
import asyncpg
from backend.connectors.base import (
    DataSource, SourceType, SchemaInfo, TableMeta, ColumnMeta, QueryResult
)
from backend.core.config import settings


class PostgreSQLConnector(DataSource):
    """Async PostgreSQL connector using asyncpg connection pool."""

    def __init__(self, source_id: str, credentials: dict):
        super().__init__(source_id, credentials)
        self._pool: asyncpg.Pool | None = None

    @property
    def sql_dialect(self) -> str:
        return "postgresql"

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            host=self.credentials["host"],
            port=int(self.credentials.get("port", 5432)),
            database=self.credentials["database"],
            user=self.credentials["user"],
            password=self.credentials["password"],
            min_size=1,
            max_size=5,
            command_timeout=settings.QUERY_TIMEOUT_SECONDS,
        )
        self._connected = True

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
        self._connected = False

    async def test_connection(self) -> bool:
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def get_schema(self) -> SchemaInfo:
        tables = []
        async with self._pool.acquire() as conn:
            # Get all tables in public schema (and other schemas)
            table_rows = await conn.fetch("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
            """)

            for trow in table_rows:
                schema_name = trow["table_schema"]
                table_name = trow["table_name"]

                # Row count estimate
                row_count = await conn.fetchval(
                    "SELECT reltuples::bigint FROM pg_class WHERE relname = $1",
                    table_name,
                ) or 0

                # Columns
                col_rows = await conn.fetch("""
                    SELECT
                        c.column_name,
                        c.data_type,
                        c.is_nullable,
                        CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_pk,
                        CASE WHEN fk.column_name IS NOT NULL THEN true ELSE false END AS is_fk,
                        fk.foreign_table_name || '.' || fk.foreign_column_name AS fk_ref
                    FROM information_schema.columns c
                    LEFT JOIN (
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                            ON tc.constraint_name = kcu.constraint_name
                        WHERE tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_name = $1
                    ) pk ON c.column_name = pk.column_name
                    LEFT JOIN (
                        SELECT kcu.column_name,
                               ccu.table_name AS foreign_table_name,
                               ccu.column_name AS foreign_column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                            ON tc.constraint_name = kcu.constraint_name
                        JOIN information_schema.constraint_column_usage ccu
                            ON tc.constraint_name = ccu.constraint_name
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                          AND tc.table_name = $1
                    ) fk ON c.column_name = fk.column_name
                    WHERE c.table_name = $1
                      AND c.table_schema = $2
                    ORDER BY c.ordinal_position
                """, table_name, schema_name)

                # Sample values for each column (top 3)
                columns = []
                for col in col_rows:
                    sample_vals = []
                    try:
                        sample_rows = await conn.fetch(
                            f'SELECT DISTINCT "{col["column_name"]}" '
                            f'FROM "{schema_name}"."{table_name}" '
                            f'WHERE "{col["column_name"]}" IS NOT NULL LIMIT 3'
                        )
                        sample_vals = [r[0] for r in sample_rows]
                    except Exception:
                        pass

                    columns.append(ColumnMeta(
                        name=col["column_name"],
                        data_type=col["data_type"],
                        nullable=col["is_nullable"] == "YES",
                        is_primary_key=col["is_pk"],
                        is_foreign_key=col["is_fk"],
                        references=col["fk_ref"],
                        sample_values=sample_vals,
                    ))

                tables.append(TableMeta(
                    name=table_name,
                    schema=schema_name,
                    columns=columns,
                    row_count=int(row_count),
                ))

        return SchemaInfo(
            source_id=self.source_id,
            source_type=SourceType.POSTGRESQL,
            database=self.credentials["database"],
            tables=tables,
        )

    async def execute(
        self,
        query: str,
        params: dict | None = None,
        max_rows: int = settings.MAX_QUERY_ROWS,
        timeout_seconds: int = settings.QUERY_TIMEOUT_SECONDS,
    ) -> QueryResult:
        # Inject LIMIT if not present
        q = query.strip().rstrip(";")
        if "limit" not in q.lower():
            q = f"{q} LIMIT {max_rows}"

        start = time.monotonic()
        async with self._pool.acquire() as conn:
            records = await conn.fetch(q, timeout=timeout_seconds)

        elapsed_ms = (time.monotonic() - start) * 1000
        columns = list(records[0].keys()) if records else []
        rows = [list(r.values()) for r in records]

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=elapsed_ms,
            truncated=len(rows) >= max_rows,
        )
