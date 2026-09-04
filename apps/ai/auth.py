"""Provider-aware headers and URL construction for OpenAI-compatible APIs."""

import re
from typing import Dict, Optional

from .providers import get_provider


def build_headers(provider: str, api_key: Optional[str], api_version: str = None) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if not api_key:
        return headers

    style = get_provider(provider).get("auth", "bearer")
    if style == "api_key":
        headers["api-key"] = api_key
    elif style == "azure":
        headers["api-key"] = api_key
    elif style == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def build_url(
    base_url: str,
    endpoint: str,
    provider: str = "other",
    api_version: str = None,
) -> str:
    """Normalize roots, versioned roots and already-expanded endpoints."""
    normalized = (base_url or "").rstrip("/")
    if not normalized:
        raise ValueError("AI base_url is required")

    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    if normalized.endswith(endpoint):
        url = normalized
    else:
        for known in ("/chat/completions", "/models", "/embeddings"):
            if normalized.endswith(known):
                normalized = normalized[: -len(known)]
                break
        if re.search(r"/v\d+(?:beta\d*)?$", normalized):
            url = f"{normalized}{endpoint}"
        else:
            url = f"{normalized}/v1{endpoint}"

    if provider == "azure_openai" and api_version:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}api-version={api_version}"
    return url
