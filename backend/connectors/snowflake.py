"""
QueryMind — Snowflake Connector
"""
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import snowflake.connector
from backend.connectors.base import (
    DataSource, SourceType, SchemaInfo, TableMeta, ColumnMeta, QueryResult
)
from backend.core.config import settings

_executor = ThreadPoolExecutor(max_workers=4)


class SnowflakeConnector(DataSource):
    """
    Snowflake connector (sync SDK wrapped in asyncio executor).
    Snowflake's Python SDK is sync-only.
    """

    def __init__(self, source_id: str, credentials: dict):
        super().__init__(source_id, credentials)
        self._conn = None

    @property
    def sql_dialect(self) -> str:
        return "snowflake"

    def _connect_sync(self):
        return snowflake.connector.connect(
            account=self.credentials["account"],
            user=self.credentials["user"],
            password=self.credentials["password"],
            warehouse=self.credentials.get("warehouse", ""),
            database=self.credentials.get("database", ""),
            schema=self.credentials.get("schema", "PUBLIC"),
            login_timeout=10,
        )

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(_executor, self._connect_sync)
        self._connected = True

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    async def test_connection(self) -> bool:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_executor, lambda: self._conn.cursor().execute("SELECT 1"))
            return True
        except Exception:
            return False

    def _get_schema_sync(self) -> SchemaInfo:
        cur = self._conn.cursor()
        database = self.credentials.get("database", "")
        schema = self.credentials.get("schema", "PUBLIC")

        cur.execute(f"""
            SELECT table_name, row_count
            FROM {database}.information_schema.tables
            WHERE table_schema = '{schema}'
            AND table_type = 'BASE TABLE'
        """)
        table_rows = cur.fetchall()

        tables = []
        for (table_name, row_count) in table_rows:
            cur.execute(f"""
                SELECT column_name, data_type, is_nullable
                FROM {database}.information_schema.columns
                WHERE table_schema = '{schema}' AND table_name = '{table_name}'
                ORDER BY ordinal_position
            """)
            col_rows = cur.fetchall()
            columns = [
                ColumnMeta(
                    name=c[0],
                    data_type=c[1],
                    nullable=c[2] == "YES",
                )
                for c in col_rows
            ]
            tables.append(TableMeta(
                name=table_name,
                schema=schema,
                columns=columns,
                row_count=row_count or 0,
            ))

        return SchemaInfo(
            source_id=self.source_id,
            source_type=SourceType.SNOWFLAKE,
            database=database,
            tables=tables,
        )

    async def get_schema(self) -> SchemaInfo:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._get_schema_sync)

    def _execute_sync(self, query: str, max_rows: int) -> QueryResult:
        cur = self._conn.cursor()
        start = time.monotonic()
        cur.execute(query)
        rows = cur.fetchmany(max_rows)
        elapsed_ms = (time.monotonic() - start) * 1000
        columns = [d[0] for d in (cur.description or [])]
        return QueryResult(
            columns=columns,
            rows=[list(r) for r in rows],
            row_count=len(rows),
            execution_time_ms=elapsed_ms,
            truncated=len(rows) >= max_rows,
        )

    async def execute(
        self,
        query: str,
        params: dict | None = None,
        max_rows: int = settings.MAX_QUERY_ROWS,
        timeout_seconds: int = settings.QUERY_TIMEOUT_SECONDS,
    ) -> QueryResult:
        q = query.strip().rstrip(";")
        if "limit" not in q.lower():
            q = f"{q} LIMIT {max_rows}"
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._execute_sync, q, max_rows)
