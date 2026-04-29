"""
QueryMind — Intent Classifier Node
"""
from typing import Literal
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from backend.agents.state import QueryMindState
from backend.core.config import settings
from backend.memory.long_term import retrieve_user_preferences
import structlog

logger = structlog.get_logger(__name__)

class IntentSchema(BaseModel):
    intent: Literal["data_query", "dashboard", "clarification"] = Field(
        description="The classified intent of the user's message."
    )
    confidence: float = Field(
        description="Confidence score from 0.0 to 1.0. If below 0.8, intent must be 'clarification'."
    )
    reasoning: str = Field(description="Why this intent was chosen.")
    clarification_question: str | None = Field(
        description="If intent is clarification, what exactly should be asked back to the user?",
        default=None
    )

async def intent_classifier_node(state: QueryMindState) -> QueryMindState:
    """Classify the user intent and load long-term user preferences."""
    # Load long term preferences early, but never block the flow on memory issues.
    try:
        prefs = await retrieve_user_preferences(state["user_id"], state["question"])
    except Exception as exc:
        logger.warning("intent_preferences_lookup_failed", error=str(exc))
        prefs = []
    state["long_term_preferences"] = "\n".join(prefs) if prefs else "None"

    if not settings.OPENROUTER_API_KEY:
        state["intent"] = "data_query"
        state["confidence"] = 1.0
        state["needs_clarification"] = False
        state["reasoning"] = ["Intent Classifier: OPENROUTER_API_KEY missing, defaulted to data_query."]
        return state

    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
    )
    
    prompt = f"""
You are the Intent Classifier for QueryMind, an Enterprise AI-to-SQL platform.
Analyze the user's question and determine the intent.
User's long term preferences: {state['long_term_preferences']}

User Question: "{state['question']}"

If the question is extremely vague or lacks enough context to query a database, set confidence low and intent to 'clarification'.
If it asks for a chart/graph/dashboard, set intent to 'dashboard'.
Otherwise, set 'data_query'.
"""

    try:
        completion = await client.chat.completions.create(
            model=settings.LLM_FAST_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are an intent classifier. Always respond in pure JSON matching the schema: {intent, confidence, reasoning, clarification_question}",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        raw_json = completion.choices[0].message.content or "{}"
        result = IntentSchema.model_validate_json(raw_json)
        
        state["intent"] = result.intent
        state["confidence"] = result.confidence
        state["needs_clarification"] = (result.intent == "clarification")
        
        if state["needs_clarification"]:
            state["summary"] = result.clarification_question
            
        state["reasoning"] = [f"Intent Classifier: Decided '{result.intent}' (Confidence: {result.confidence}). {result.reasoning}"]
    except Exception as e:
        state["intent"] = "data_query"
        state["confidence"] = 1.0
        state["needs_clarification"] = False
        state["reasoning"] = [f"Intent Classifier failed to parse JSON, falling back to data_query. Error: {e}"]
        
    return state
