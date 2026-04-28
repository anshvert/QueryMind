"""
QueryMind — Connector Factory
Creates and caches connector instances by source_id.
"""
from backend.connectors.base import DataSource, SourceType
from backend.connectors.postgresql import PostgreSQLConnector
from backend.connectors.mongodb import MongoDBConnector
from backend.connectors.snowflake import SnowflakeConnector
from backend.connectors.bigquery import BigQueryConnector
from backend.connectors.duckdb_file import DuckDBFileConnector

_registry: dict[str, DataSource] = {}


def get_connector(source_id: str, source_type: str, credentials: dict) -> DataSource:
    """Return a connector instance for the given source."""
    st = SourceType(source_type)
    mapping = {
        SourceType.POSTGRESQL: PostgreSQLConnector,
        SourceType.MONGODB: MongoDBConnector,
        SourceType.SNOWFLAKE: SnowflakeConnector,
        SourceType.BIGQUERY: BigQueryConnector,
        SourceType.DUCKDB: DuckDBFileConnector,
    }
    cls = mapping.get(st)
    if not cls:
        raise ValueError(f"Unsupported source type: {source_type}")
    return cls(source_id=source_id, credentials=credentials)


async def get_or_connect(source_id: str, source_type: str, credentials: dict) -> DataSource:
    """Return a cached, connected connector or create a new one."""
    if source_id not in _registry or not _registry[source_id].is_connected:
        connector = get_connector(source_id, source_type, credentials)
        await connector.connect()
        _registry[source_id] = connector
    return _registry[source_id]


async def disconnect_all():
    for connector in _registry.values():
        await connector.disconnect()
    _registry.clear()
