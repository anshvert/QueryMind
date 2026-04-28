"""
QueryMind — MongoDB Connector
Uses motor (async) for queries, translates NL SQL to aggregation pipelines.
"""
import time
from motor.motor_asyncio import AsyncIOMotorClient
from backend.connectors.base import (
    DataSource, SourceType, SchemaInfo, TableMeta, ColumnMeta, QueryResult
)
from backend.core.config import settings


class MongoDBConnector(DataSource):
    """Async MongoDB connector using motor."""

    def __init__(self, source_id: str, credentials: dict):
        super().__init__(source_id, credentials)
        self._client: AsyncIOMotorClient | None = None
        self._db = None

    @property
    def sql_dialect(self) -> str:
        return "mongodb_aggregation"

    async def connect(self) -> None:
        uri = self.credentials.get("uri") or (
            f"mongodb://{self.credentials['user']}:{self.credentials['password']}"
            f"@{self.credentials['host']}:{self.credentials.get('port', 27017)}"
        )
        self._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        self._db = self._client[self.credentials["database"]]
        self._connected = True

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
        self._connected = False

    async def test_connection(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    async def get_schema(self) -> SchemaInfo:
        """
        MongoDB is schemaless — we sample documents to infer schema.
        Each collection = one 'table'.
        """
        tables = []
        collection_names = await self._db.list_collection_names()

        for coll_name in collection_names:
            collection = self._db[coll_name]
            row_count = await collection.count_documents({})

            # Sample 100 docs to infer schema
            sample_docs = await collection.find({}).limit(100).to_list(100)
            field_types: dict[str, set] = {}
            for doc in sample_docs:
                for key, val in doc.items():
                    if key not in field_types:
                        field_types[key] = set()
                    field_types[key].add(type(val).__name__)

            columns = []
            for field_name, types in field_types.items():
                is_pk = field_name == "_id"
                columns.append(ColumnMeta(
                    name=field_name,
                    data_type=" | ".join(types),
                    nullable=True,
                    is_primary_key=is_pk,
                    sample_values=[
                        doc.get(field_name)
                        for doc in sample_docs[:3]
                        if doc.get(field_name) is not None
                    ],
                ))

            tables.append(TableMeta(
                name=coll_name,
                schema="",
                columns=columns,
                row_count=row_count,
            ))

        return SchemaInfo(
            source_id=self.source_id,
            source_type=SourceType.MONGODB,
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
        """
        For MongoDB, 'query' is expected to be a JSON aggregation pipeline string.
        Format: {"collection": "orders", "pipeline": [...]}
        """
        import json
        payload = json.loads(query)
        collection = self._db[payload["collection"]]
        pipeline = payload.get("pipeline", [])
        pipeline.append({"$limit": max_rows})

        start = time.monotonic()
        cursor = collection.aggregate(pipeline, maxTimeMS=timeout_seconds * 1000)
        docs = await cursor.to_list(max_rows)
        elapsed_ms = (time.monotonic() - start) * 1000

        if not docs:
            return QueryResult(columns=[], rows=[], row_count=0, execution_time_ms=elapsed_ms)

        # Flatten all keys across all docs
        all_keys = list({k for doc in docs for k in doc.keys()})
        rows = [[str(doc.get(k, None)) for k in all_keys] for doc in docs]

        return QueryResult(
            columns=all_keys,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=elapsed_ms,
            truncated=len(rows) >= max_rows,
        )
