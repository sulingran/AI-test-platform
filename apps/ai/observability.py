"""Best-effort AI call recording and cost estimation."""

import contextvars
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.conf import settings

from .models import AiCallRecord


logger = logging.getLogger("apps.ai.observability")
_scenario = contextvars.ContextVar("ai_scenario", default=None)


def set_scenario(scenario: Optional[str] = None):
    return _scenario.set(scenario)


def reset_scenario(token) -> None:
    _scenario.reset(token)


def get_scenario() -> Optional[str]:
    return _scenario.get()


def estimate_cost(provider: str, model_name: str, prompt_tokens=None, completion_tokens=None):
    """Estimate USD cost using an explicitly configured pricing row."""
    if prompt_tokens is None and completion_tokens is None:
        return None
    try:
        from .models import AiModelPricing

        rows = list(AiModelPricing.objects.filter(provider=provider or ""))
        matching = next(
            (row for row in rows if row.model_keyword and row.model_keyword in (model_name or "")),
            None,
        )
        row = matching or next((item for item in rows if not item.model_keyword), None)
        if row is None:
            return None

        input_cost = Decimal(prompt_tokens or 0) * row.input_per_million / Decimal(1_000_000)
        output_cost = Decimal(completion_tokens or 0) * row.output_per_million / Decimal(1_000_000)
        return (input_cost + output_cost).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except Exception as exc:
        logger.warning("AI cost estimation skipped: %s", type(exc).__name__)
        return None


def emit(
    provider: str = "",
    model_name: str = "",
    role: str = "",
    status: str = "success",
    latency_ms: Optional[int] = None,
    scenario: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    cost_estimate=None,
    error_message: str = "",
    config_id: Optional[int] = None,
    created_by_id: Optional[int] = None,
) -> None:
    """Persist one record without allowing observability to break AI calls."""
    if not getattr(settings, "AI_OBSERVABILITY_ENABLED", True):
        return
    try:
        if cost_estimate is None and status == "success":
            cost_estimate = estimate_cost(provider, model_name, prompt_tokens, completion_tokens)
        total_tokens = None
        if prompt_tokens is not None or completion_tokens is not None:
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        AiCallRecord.objects.create(
            provider=(provider or "")[:30],
            model_name=(model_name or "")[:200],
            role=(role or "")[:30],
            scenario=(scenario or get_scenario() or "general")[:80],
            config_id=config_id,
            created_by_id=created_by_id,
            status=status,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_estimate=cost_estimate,
            # Never persist request/response bodies or credentials.
            error_message=(error_message or "")[:2000],
        )
    except Exception as exc:
        logger.warning("AI call record skipped: %s", type(exc).__name__)
