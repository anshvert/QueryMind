"""
QueryMind — DuckDB File Connector
Handles CSV, Parquet, Excel files as queryable tables via DuckDB.
"""
import time
import duckdb
from pathlib import Path
from backend.connectors.base import (
    DataSource, SourceType, SchemaInfo, TableMeta, ColumnMeta, QueryResult
)
from backend.core.config import settings


class DuckDBFileConnector(DataSource):
    """
    Loads CSV/Parquet/Excel files into DuckDB in-memory views.
    Each file becomes a queryable table named after the filename stem.
    """

    def __init__(self, source_id: str, credentials: dict):
        """
        credentials:
          - file_paths: list of absolute file paths
          - OR file_path: single file path
        """
        super().__init__(source_id, credentials)
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._table_names: list[str] = []

    @property
    def sql_dialect(self) -> str:
        return "duckdb"

    async def connect(self) -> None:
        self._conn = duckdb.connect(database=":memory:")
        file_paths = self.credentials.get("file_paths") or [self.credentials["file_path"]]

        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {fp}")

            table_name = path.stem.replace(" ", "_").replace("-", "_").lower()
            ext = path.suffix.lower()

            if ext == ".csv":
                self._conn.execute(
                    f"CREATE VIEW {table_name} AS SELECT * FROM read_csv_auto('{fp}')"
                )
            elif ext in (".parquet", ".pq"):
                self._conn.execute(
                    f"CREATE VIEW {table_name} AS SELECT * FROM read_parquet('{fp}')"
                )
            elif ext in (".xlsx", ".xls"):
                self._conn.execute(
                    f"CREATE VIEW {table_name} AS SELECT * FROM st_read('{fp}')"
                )
            else:
                raise ValueError(f"Unsupported file type: {ext}")

            self._table_names.append(table_name)

        self._connected = True

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    async def test_connection(self) -> bool:
        try:
            self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def get_schema(self) -> SchemaInfo:
        tables = []
        for table_name in self._table_names:
            result = self._conn.execute(f"DESCRIBE {table_name}").fetchall()
            row_count = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

            columns = []
            for row in result:
                col_name, col_type = row[0], row[1]
                # Sample values
                sample = self._conn.execute(
                    f'SELECT DISTINCT "{col_name}" FROM {table_name} '
                    f'WHERE "{col_name}" IS NOT NULL LIMIT 3'
                ).fetchall()
                sample_vals = [r[0] for r in sample]

                columns.append(ColumnMeta(
                    name=col_name,
                    data_type=col_type,
                    nullable=True,
                    sample_values=sample_vals,
                ))

            tables.append(TableMeta(
                name=table_name,
                schema="",
                columns=columns,
                row_count=row_count,
            ))

        return SchemaInfo(
            source_id=self.source_id,
            source_type=SourceType.DUCKDB,
            database="file_source",
            tables=tables,
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

        start = time.monotonic()
        result = self._conn.execute(q).fetchall()
        elapsed_ms = (time.monotonic() - start) * 1000

        description = self._conn.description or []
        columns = [d[0] for d in description]
        rows = [list(r) for r in result]

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=elapsed_ms,
            truncated=len(rows) >= max_rows,
        )
