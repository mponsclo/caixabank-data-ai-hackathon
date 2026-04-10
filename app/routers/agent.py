"""Agent endpoint with 3-layer LLM strategy:
1. Vertex AI Gemini (scaffold, inactive by default)
2. Ollama (local testing)
3. Regex fallback (always available, production default)

Controlled via AGENT_LLM_BACKEND env var: "vertex", "ollama", or "regex" (default).
"""

import os

from fastapi import APIRouter

from app.schemas import AgentRequest, AgentResponse

router = APIRouter()

BACKEND = os.environ.get("AGENT_LLM_BACKEND", "regex")


def _extract_dates_vertex(prompt: str) -> tuple[str | None, str | None]:
    """Vertex AI Gemini date extraction (scaffold — not yet active)."""
    try:
        from vertexai.generative_models import GenerativeModel

        model = GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            f"Extract start_date and end_date from this request. "
            f'Return JSON only: {{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}}.\n\n'
            f"Request: {prompt}"
        )
        import json

        result = json.loads(response.text)
        return result.get("start_date"), result.get("end_date")
    except Exception:
        return None, None


def _extract_dates_ollama(prompt: str) -> tuple[str | None, str | None]:
    """Ollama local LLM date extraction (for development/testing)."""
    try:
        from langchain_ollama import ChatOllama

        llm = ChatOllama(model="llama3.2:1b", temperature=0)

        from src.agent.tools import EXTRACTION_PROMPT

        response = llm.invoke(EXTRACTION_PROMPT.format(input=prompt))
        import json

        result = json.loads(response.content)
        return result.get("start_date"), result.get("end_date")
    except Exception:
        return None, None


def _extract_dates_regex(prompt: str) -> tuple[str | None, str | None]:
    """Regex-based date extraction (deterministic, always available)."""
    from src.agent.tools import regex_extract_dates

    result = regex_extract_dates(prompt)
    if result is None:
        return None, None
    return result


@router.post("/generate", response_model=AgentResponse)
def generate_report(body: AgentRequest):
    start_date, end_date = None, None
    backend_used = BACKEND

    # Try configured backend first
    if BACKEND == "vertex":
        start_date, end_date = _extract_dates_vertex(body.prompt)
        backend_used = "vertex"
    elif BACKEND == "ollama":
        start_date, end_date = _extract_dates_ollama(body.prompt)
        backend_used = "ollama"

    # Always fall back to regex if LLM extraction failed or regex is default
    if start_date is None or end_date is None:
        start_date, end_date = _extract_dates_regex(body.prompt)
        backend_used = "regex" if BACKEND == "regex" else f"{BACKEND}+regex_fallback"

    if start_date and end_date:
        message = f"Dates extracted: {start_date} to {end_date} for client {body.client_id}"
    else:
        message = "Could not extract date range from prompt"

    return AgentResponse(
        client_id=body.client_id,
        start_date=start_date,
        end_date=end_date,
        backend_used=backend_used,
        message=message,
    )
