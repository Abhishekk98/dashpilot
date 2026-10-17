import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from llm import LLMError, LLMNotConfiguredError, LLMRateLimitError, build_provider

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMTestResponse(BaseModel):
    provider: str
    model: str
    response: str
    latency_ms: int


@router.get("/test", response_model=LLMTestResponse)
def llm_test(settings: Settings = Depends(get_settings)) -> LLMTestResponse:
    """Send "Reply with OK" to the active provider so you can check your API key works."""
    try:
        provider = build_provider(settings)
        started = time.perf_counter()
        reply = provider.generate_text("Reply with OK")
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return LLMTestResponse(
        provider=provider.name,
        model=provider.model,
        response=reply.strip(),
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
