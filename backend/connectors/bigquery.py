"""
QueryMind — BigQuery Connector
"""
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from google.cloud import bigquery
from google.oauth2 import service_account
from backend.connectors.base import (
    DataSource, SourceType, SchemaInfo, TableMeta, ColumnMeta, QueryResult
)
from backend.core.config import settings

_executor = ThreadPoolExecutor(max_workers=4)


class BigQueryConnector(DataSource):
    def __init__(self, source_id: str, credentials: dict):
        super().__init__(source_id, credentials)
        self._client: bigquery.Client | None = None

    @property
    def sql_dialect(self) -> str:
        return "bigquery"

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        self._client = await loop.run_in_executor(_executor, self._build_client)
        self._connected = True

    def _build_client(self) -> bigquery.Client:
        project = self.credentials.get("project_id") or settings.BIGQUERY_PROJECT_ID
        key_path = self.credentials.get("key_file_path") or settings.GOOGLE_APPLICATION_CREDENTIALS
        if key_path:
            creds = service_account.Credentials.from_service_account_file(
                key_path,
                scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
            )
            return bigquery.Client(project=project, credentials=creds)
        return bigquery.Client(project=project)

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
        self._connected = False

    async def test_connection(self) -> bool:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_executor, lambda: list(self._client.query("SELECT 1").result()))
            return True
        except Exception:
            return False

    def _get_schema_sync(self) -> SchemaInfo:
        dataset_id = self.credentials.get("dataset", "")
        tables = []
        for bq_table in self._client.list_tables(self._client.dataset(dataset_id)):
            table_ref = self._client.get_table(bq_table.reference)
            columns = [
                ColumnMeta(name=f.name, data_type=f.field_type, nullable=f.mode != "REQUIRED")
                for f in table_ref.schema
            ]
            tables.append(TableMeta(
                name=bq_table.table_id, schema=dataset_id,
                columns=columns, row_count=table_ref.num_rows or 0,
            ))
        return SchemaInfo(
            source_id=self.source_id, source_type=SourceType.BIGQUERY,
            database=f"{self._client.project}.{dataset_id}", tables=tables,
        )

    async def get_schema(self) -> SchemaInfo:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._get_schema_sync)

    def _execute_sync(self, query: str, max_rows: int, timeout: int) -> QueryResult:
        start = time.monotonic()
        results = self._client.query(query).result(timeout=timeout)
        elapsed_ms = (time.monotonic() - start) * 1000
        columns = [f.name for f in results.schema]
        rows = [[row[c] for c in columns] for i, row in enumerate(results) if i < max_rows]
        return QueryResult(columns=columns, rows=rows, row_count=len(rows),
                           execution_time_ms=elapsed_ms, truncated=len(rows) >= max_rows)

    async def execute(self, query: str, params=None,
                      max_rows: int = settings.MAX_QUERY_ROWS,
                      timeout_seconds: int = settings.QUERY_TIMEOUT_SECONDS) -> QueryResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._execute_sync, query, max_rows, timeout_seconds)
