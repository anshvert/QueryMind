"""
Day 1 chat endpoint: NL question -> SQL generation.
"""
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.orchestrator import get_compiled_graph
from backend.memory.checkpointer import get_checkpointer
from backend.core.database import get_db
from backend.schema_registry.models import DataSourceModel
from backend.security.encryption import decrypt_credentials
from backend.observability.langfuse_client import get_langfuse

router = APIRouter()
logger = structlog.get_logger(__name__)


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
    summary: str | None
    dashboard_spec: dict | None
    reasoning: list[str]
    thread_id: str


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
    
    # Thread ID for Postgres Checkpointer Memory
    thread_id = payload.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

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
        
        # Initialize state. 
        # For LangGraph, if the thread_id exists in Postgres, it will merge this state over it.
        initial_state = {
            "user_id": payload.user_id,
            "source_id": str(source.id),
            "source_type": source.source_type,
            "credentials": credentials,
            "question": payload.question,
            "messages": [("user", payload.question)], # Add to memory log
            "sql": "",
            "error": None,
            "retry_count": 0,
            "results": None,
            "summary": None,
            "dashboard_spec": None,
            "reasoning": []
        }
        
        final_state = initial_state
        async for step_output in graph.astream(initial_state, config=config):
            for node_name, state_update in step_output.items():
                before = _state_view(final_state)
                logger.info(f"--- Completed Node: {node_name} ---")
                if "reasoning" in state_update and state_update["reasoning"]:
                    logger.info(f"Reasoning: {state_update['reasoning'][-1]}")
                if "error" in state_update and state_update["error"]:
                    logger.error(f"Error encountered: {state_update['error']}")
                
                # keep track of final state
                final_state.update(state_update)
                after = _state_view(final_state)
                logger.info("node_state_transition", node=node_name, before=before, after=after)
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

    return ChatResponse(
        source_id=str(source.id),
        question=payload.question,
        intent=result.get("intent", "unknown"),
        sql=result.get("sql"),
        summary=result.get("summary"),
        dashboard_spec=result.get("dashboard_spec"),
        reasoning=result.get("reasoning", []),
        thread_id=thread_id
    )

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
