"""
QueryMind — Critic Agent Node
"""
from openai import AsyncOpenAI
from backend.agents.state import QueryMindState
from backend.core.config import settings
import json

async def critic_agent_node(state: QueryMindState) -> QueryMindState:
    """Verify that the Insight Extractor didn't hallucinate facts not in the data."""
    if state.get("error") or not state.get("results") or not state.get("summary"):
        return state

    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
    )
    
    sample_data = json.dumps(state["results"][:10], default=str)
    
    prompt = f"""
You are the Critic Agent for an Enterprise BI tool.
Validate the analyst summary against the data.
Return STRICT JSON only:
{{
  "verdict": "pass" | "fail",
  "confidence": 0.0 to 1.0,
  "reason": "short reason",
  "corrected_summary": "required only when verdict is fail"
}}

Rules:
- Use verdict=pass when summary is materially correct.
- Use verdict=fail only for factual mismatches, invented numbers, or wrong conclusions.
- Do not rewrite good summaries.

Data:
{sample_data}

Analyst Summary:
{state['summary']}
"""

    try:
        completion = await client.chat.completions.create(
            model=settings.LLM_FAST_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a ruthless data fact-checker."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
    except Exception as exc:
        state["reasoning"] = [f"Critic Agent: model call failed: {exc}"]
        return state
    
    raw = (completion.choices[0].message.content or "{}").strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"verdict": "pass", "reason": "Critic returned non-JSON response."}

    verdict = str(parsed.get("verdict", "pass")).lower()
    confidence = float(parsed.get("confidence", 0.0) or 0.0)
    if verdict == "fail" and confidence >= 0.9:
        corrected = (parsed.get("corrected_summary") or "").strip()
        reason = (parsed.get("reason") or "Factual mismatch detected.").strip()
        if corrected:
            state["summary"] = f"CRITIC CORRECTION: {corrected}"
            state["reasoning"] = [f"Critic Agent: Corrected summary ({reason}, confidence={confidence:.2f})."]
        else:
            state["reasoning"] = [f"Critic Agent: Marked fail but no corrected summary ({reason}, confidence={confidence:.2f})."]
    else:
        state["reasoning"] = [f"Critic Agent: PASS (verdict={verdict}, confidence={confidence:.2f})."]
        
    return state
