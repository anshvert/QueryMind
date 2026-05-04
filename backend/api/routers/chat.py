"""
Day 1 chat endpoint: NL question -> SQL generation.
"""
import uuid
import json
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from backend.agents.orchestrator import get_compiled_graph
from backend.memory.checkpointer import get_checkpointer
from backend.core.database import get_db
from backend.schema_registry.models import DataSourceModel
from backend.schema_registry.audit_models import AuditLogModel
from backend.security.encryption import decrypt_credentials
from backend.observability.langfuse_client import get_langfuse

router = APIRouter()
logger = structlog.get_logger(__name__)


class ChatRequest(BaseModel):
    source_id: uuid.UUID
    question: str = Field(min_length=1)
    user_id: str = Field(default="user_default")
    thread_id: str | None = Field(default=None, description="Provide a thread_id to resume a conversation.")


class ChatResponse(BaseModel):
    source_id: str
    question: str
    intent: str
    sql: str | None
    results: list[dict] | None = None
    summary: str | None
    dashboard_spec: dict | None
    reasoning: list[str]
    thread_id: str


def _state_view(state: dict) -> dict:
    """Create a compact, safe state view for debug logs."""
    return {
        "intent": state.get("intent"),
        "question": state.get("question"),
        "sql": (state.get("sql") or "")[:300],
        "error": state.get("error"),
        "retry_count": state.get("retry_count"),
        "row_count": state.get("row_count"),
        "results_count": len(state.get("results") or []),
        "summary": (state.get("summary") or "")[:300],
        "dashboard_spec_present": bool(state.get("dashboard_spec")),
        "reasoning_tail": (state.get("reasoning") or [])[-1:] if state.get("reasoning") else [],
    }


async def _log_audit(db: AsyncSession, payload: ChatRequest, result: dict, source_id: str, thread_id: str):
    """Log the query execution for governance."""
    try:
        log_entry = AuditLogModel(
            source_id=source_id,
            user_id=payload.user_id,
            thread_id=thread_id,
            question=payload.question,
            intent=result.get("intent"),
            generated_sql=result.get("sql"),
            row_count=len(result.get("results") or []),
            is_success=not bool(result.get("error")),
            error_message=result.get("error"),
        )
        db.add(log_entry)
        await db.commit()
    except Exception as exc:
        logger.error("audit_log_failed", error=str(exc))


def _build_initial_state(payload: ChatRequest, source: DataSourceModel, credentials: dict) -> tuple[str, dict, dict]:
    thread_id = payload.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "user_id": payload.user_id,
        "source_id": str(source.id),
        "source_type": source.source_type,
        "credentials": credentials,
        "question": payload.question,
        "messages": [("user", payload.question)],
        "sql": "",
        "error": None,
        "retry_count": 0,
        "results": None,
        "summary": None,
        "dashboard_spec": None,
        "reasoning": [],
    }
    return thread_id, config, initial_state


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    logger.info("chat_request_received", source_id=str(payload.source_id), user_id=payload.user_id)
    row = await db.execute(
        select(DataSourceModel).where(
            DataSourceModel.id == payload.source_id,
            DataSourceModel.is_active.is_(True),
        )
    )
    source = row.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    credentials = decrypt_credentials(source.encrypted_credentials)
    logger.info("chat_source_loaded", source_id=str(source.id), source_type=source.source_type)
    
    thread_id, config, initial_state = _build_initial_state(payload, source, credentials)

    logger.info("chat_graph_start", thread_id=thread_id)
    langfuse = get_langfuse()
    trace = None
    if langfuse:
        try:
            trace = langfuse.trace(
                name="chat_api",
                user_id=payload.user_id,
                input={"question": payload.question, "source_id": str(payload.source_id), "thread_id": thread_id},
            )
        except Exception as exc:
            logger.warning("langfuse_trace_init_failed", error=str(exc))

    async with get_checkpointer() as checkpointer:
        graph = get_compiled_graph(checkpointer=checkpointer)
        
        final_state = initial_state
        async for step_output in graph.astream(initial_state, config=config):
            for node_name, state_update in step_output.items():
                before = _state_view(final_state)
                logger.info("⚡ node_complete", node=node_name,
                            intent=state_update.get("intent"),
                            has_sql=bool(state_update.get("sql")),
                            has_results=bool(state_update.get("results")),
                            has_summary=bool(state_update.get("summary")),
                            error=state_update.get("error"),
                            reasoning_tail=(state_update.get("reasoning") or [])[-1:],
                            )
                if state_update.get("error"):
                    logger.error("node_error", node=node_name, error=state_update["error"])

                # keep track of final state
                final_state.update(state_update)
                after = _state_view(final_state)
                if trace:
                    try:
                        trace.event(
                            name=f"node_{node_name}",
                            input=before,
                            output=after,
                        )
                    except Exception as exc:
                        logger.warning("langfuse_node_event_failed", node=node_name, error=str(exc))
                
        result = final_state
    logger.info("chat_graph_complete", thread_id=thread_id, intent=result.get("intent"))
    if trace:
        try:
            trace.update(
                output={
                    "intent": result.get("intent"),
                    "sql": result.get("sql"),
                    "summary": result.get("summary"),
                    "dashboard_spec": result.get("dashboard_spec"),
                    "reasoning": result.get("reasoning", []),
                }
            )
            langfuse.flush()
        except Exception as exc:
            logger.warning("langfuse_trace_finalize_failed", error=str(exc))

    await _log_audit(db, payload, result, source.id, thread_id)

    if result.get("error"):
        logger.error("chat_graph_failed", error=result["error"], thread_id=thread_id)
        raise HTTPException(status_code=500, detail=result["error"])

    return ChatResponse(
        source_id=str(source.id),
        question=payload.question,
        intent=result.get("intent", "unknown"),
        sql=result.get("sql"),
        summary=result.get("summary"),
        results=result.get("results"),
        dashboard_spec=result.get("dashboard_spec"),
        reasoning=result.get("reasoning", []),
        thread_id=thread_id
    )


@router.post("/stream")
async def chat_stream(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    stream_logger = structlog.get_logger("chat_stream")
    stream_logger.info("stream_request_received", source_id=str(payload.source_id))
    row = await db.execute(
        select(DataSourceModel).where(
            DataSourceModel.id == payload.source_id,
            DataSourceModel.is_active.is_(True),
        )
    )
    source = row.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    credentials = decrypt_credentials(source.encrypted_credentials)
    thread_id, config, initial_state = _build_initial_state(payload, source, credentials)
    stream_logger.info("stream_graph_starting", thread_id=thread_id)

    async def event_gen():
        try:
            async with get_checkpointer() as checkpointer:
                graph = get_compiled_graph(checkpointer=checkpointer)
                final_state = dict(initial_state)
                stream_logger.info("stream_emitting_start", thread_id=thread_id)
                yield {"event": "start", "data": json.dumps({"thread_id": thread_id})}
                async for step_output in graph.astream(initial_state, config=config):
                    for node_name, state_update in step_output.items():
                        final_state.update(state_update)
                        stream_logger.info("stream_node_done", node=node_name,
                                           error=final_state.get("error"),
                                           reasoning_tail=(final_state.get("reasoning") or [])[-1:])
                        payload_event = {
                            "node": node_name,
                            "state": _state_view(final_state),
                            "reasoning": final_state.get("reasoning", []),
                        }
                        yield {"event": "node", "data": json.dumps(payload_event, default=str)}

                done_payload = {
                    "source_id": str(source.id),
                    "question": payload.question,
                    "intent": final_state.get("intent", "unknown"),
                    "sql": final_state.get("sql"),
                    "summary": final_state.get("summary"),
                    "results": final_state.get("results"),
                    "dashboard_spec": final_state.get("dashboard_spec"),
                    "reasoning": final_state.get("reasoning", []),
                    "thread_id": thread_id,
                }
                stream_logger.info("stream_emitting_final", thread_id=thread_id,
                                   results_count=len(done_payload.get("results") or []),
                                   has_dashboard=bool(done_payload.get("dashboard_spec")))
                                   
                # Async generator cannot await safely on detached session if disconnected, but we try
                await _log_audit(db, payload, final_state, source.id, thread_id)
                
                yield {"event": "final", "data": json.dumps(done_payload, default=str)}
        except Exception as exc:
            stream_logger.error("stream_generator_error", error=str(exc))
            yield {"event": "error", "data": json.dumps({"error": str(exc)})}

    return EventSourceResponse(event_gen())

@router.get("/{thread_id}/history")
async def get_chat_history(thread_id: str):
    """Retrieve the conversation history for a specific thread_id."""
    async with get_checkpointer() as checkpointer:
        config = {"configurable": {"thread_id": thread_id}}
        state = await checkpointer.aget(config)
        if not state:
            raise HTTPException(status_code=404, detail="Thread not found")
            
        return {
            "thread_id": thread_id,
            "messages": [
                {"type": msg.type, "content": msg.content} 
                for msg in state["channel_values"].get("messages", [])
            ]
        }
