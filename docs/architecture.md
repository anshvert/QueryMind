# QueryMind Architecture & ADRs

## 1. System Overview
QueryMind is an enterprise-grade AI-to-SQL platform built on a containerized, Kubernetes-native architecture. It translates natural language questions into highly accurate, dialect-specific SQL queries, executes them against connected data warehouses securely, and dynamically generates interactive dashboards based on the semantic properties of the results.

### High-Level Architecture
- **Frontend**: React (Vite), rendering a split-panel interface (conversational AI on the left, live generated Recharts/ECharts dashboards on the right).
- **Backend API**: FastAPI (Python 3.12), serving REST endpoints and managing LangGraph WebSocket streams.
- **Agent Orchestration**: LangGraph, executing a multi-agent "crew" with short-term and long-term memory.
- **Memory & State**: PostgreSQL (LangGraph Checkpointer) and Qdrant (Semantic Memory).
- **Observability**: Langfuse (tracing) and Prometheus/Grafana (metrics).

---

## 2. Architecture Decision Records (ADRs)

### ADR 1: The "Universal Connector" Model
**Context**: Enterprise BI systems must query data where it lives (Snowflake, BigQuery, Postgres) without duplicating or ingesting it into a central lake.
**Decision**: We implemented a stateless execution connector layer. The platform stores only the encrypted connection string and a JSON schema snapshot of the target database.
**Consequences**: 
- **Pros**: Zero data gravity; complies with strict data residency requirements.
- **Cons**: High network latency for large analytical queries (mitigated by DuckDB edge execution for CSVs).

### ADR 2: LangGraph over LangChain Agents
**Context**: We needed a deterministic, inspectable, and cyclic agent orchestration framework capable of self-correction (retrying on SQL execution failure).
**Decision**: We chose LangGraph over standard LangChain ReAct agents or AutoGen.
**Consequences**:
- **Pros**: Explicit state machine; allows us to inject a `sql_validator` node that can route back to the LLM if the database returns a syntax error, creating a robust self-healing loop.
- **Cons**: Slightly higher boilerplate complexity in state management.

### ADR 3: Heuristic vs. LLM-Generated Dashboards
**Context**: The frontend needs a JSON specification to render charts (which X-axis, which Y-axis, which chart type).
**Decision**: We currently use a heuristic Python rule engine to generate the dashboard spec based on data types (e.g., if a datetime column and a numeric column exist, generate a Line Chart). 
**Consequences**:
- **Pros**: Extremely fast; costs $0 in LLM tokens.
- **Cons**: Can lead to semantic plotting errors (e.g., treating `PassengerId` as a summable metric because it is technically an integer). **Future Work**: Migrate dashboard spec generation to a specialized, smaller, fast LLM (like GPT-4o-mini) to provide semantic awareness.

### ADR 4: Security & Tenant Isolation
**Context**: The platform connects to sensitive data sources.
**Decision**: All connections are AES-encrypted in PostgreSQL. The backend executes queries via read-only users, and we enforce a hard row limit (e.g., `MAX_QUERY_ROWS = 10000`) in the SQL executor to prevent out-of-memory crashes or data exfiltration.
