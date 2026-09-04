"""Stateless async/sync AI client for OpenAI-compatible providers."""

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any, Dict, Optional

import httpx
from asgiref.sync import sync_to_async

from .auth import build_headers, build_url
from .providers import provider_display_name


logger = logging.getLogger("apps.ai.client")
TIMEOUT = httpx.Timeout(connect=60.0, read=900.0, write=60.0, pool=60.0)
MAX_CONTINUATIONS = 5


class AIClient:
    """One transport implementation shared by AI-enabled applications."""

    @staticmethod
    def _parts(config, messages, max_tokens=None, stream=False):
        provider = getattr(config, "model_type", "other") or "other"
        api_key = getattr(config, "api_key", None)
        extra = getattr(config, "provider_extra", None)
        api_version = extra.get("api_version") if isinstance(extra, dict) else None
        data = {
            "model": getattr(config, "model_name", ""),
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else getattr(config, "max_tokens", 4096),
            "temperature": getattr(config, "temperature", 0.7),
            "top_p": getattr(config, "top_p", 0.9),
            "stream": stream,
        }
        return (
            provider,
            provider_display_name(provider),
            build_url(getattr(config, "base_url", ""), "/chat/completions", provider, api_version),
            build_headers(provider, api_key, api_version),
            data,
        )

    @staticmethod
    def _error(provider_name: str, operation: str, exc: Exception) -> Exception:
        if isinstance(exc, httpx.TimeoutException):
            return Exception(f"{provider_name} {operation} timeout")
        if isinstance(exc, httpx.HTTPStatusError):
            return Exception(f"{provider_name} {operation} failed with HTTP {exc.response.status_code}")
        return Exception(f"{provider_name} {operation} failed: {type(exc).__name__}")

    @staticmethod
    def _usage(payload):
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage, dict):
            return None, None
        return usage.get("prompt_tokens"), usage.get("completion_tokens")

    @staticmethod
    def _emit(config, provider, status, latency_ms, scenario=None, prompt_tokens=None, completion_tokens=None, error_message=""):
        """Record observability best-effort; never let it break a request."""
        try:
            from .observability import emit

            emit(
                provider=provider,
                model_name=getattr(config, "model_name", ""),
                role=getattr(config, "role", ""),
                status=status,
                latency_ms=latency_ms,
                scenario=scenario or "general",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error_message=error_message,
                config_id=getattr(config, "id", None),
                created_by_id=getattr(config, "created_by_id", None),
            )
        except Exception as exc:
            logger.warning("AI observability skipped: %s", type(exc).__name__)

    @staticmethod
    async def _emit_async(config, provider, status, latency_ms, scenario=None, prompt_tokens=None, completion_tokens=None, error_message=""):
        await sync_to_async(AIClient._emit, thread_sensitive=True)(
            config,
            provider,
            status,
            latency_ms,
            scenario,
            prompt_tokens,
            completion_tokens,
            error_message,
        )

    @staticmethod
    async def chat(config, messages, max_tokens: int = None, scenario: Optional[str] = None, retries: int = 0) -> Dict[str, Any]:
        provider, provider_name, url, headers, data = AIClient._parts(config, messages, max_tokens, False)
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, http2=False) as client:
                response = await client.post(url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
            prompt_tokens, completion_tokens = AIClient._usage(result)
            await AIClient._emit_async(
                config, provider, "success", round((time.monotonic() - started) * 1000),
                scenario, prompt_tokens, completion_tokens,
            )
            return result
        except Exception as exc:
            logger.error("AI %s request failed: %s", provider, type(exc).__name__)
            await AIClient._emit_async(
                config, provider, "failed", round((time.monotonic() - started) * 1000),
                scenario, error_message=type(exc).__name__,
            )
            raise AIClient._error(provider_name, "chat", exc) from exc

    @staticmethod
    async def chat_stream(config, messages, callback=None, max_tokens: int = None, scenario: Optional[str] = None) -> AsyncIterator[str]:
        provider = getattr(config, "model_type", "other") or "other"
        provider_name = provider_display_name(provider)
        model_name = getattr(config, "model_name", "")
        api_key = getattr(config, "api_key", None)
        extra = getattr(config, "provider_extra", None)
        api_version = extra.get("api_version") if isinstance(extra, dict) else None
        url = build_url(getattr(config, "base_url", ""), "/chat/completions", provider, api_version)
        headers = build_headers(provider, api_key, api_version)
        actual_max_tokens = max_tokens if max_tokens is not None else getattr(config, "max_tokens", 4096)
        current_messages = list(messages)
        continuation_count = 0
        started = time.monotonic()
        final_prompt_tokens = None
        final_completion_tokens = None

        while continuation_count <= MAX_CONTINUATIONS:
            data = {
                "model": model_name,
                "messages": current_messages,
                "max_tokens": actual_max_tokens,
                "temperature": getattr(config, "temperature", 0.7),
                "top_p": getattr(config, "top_p", 0.9),
                "stream": True,
            }
            content_buffer = ""
            finish_reason = None
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT, http2=False) as client:
                    async with client.stream("POST", url, headers=headers, json=data) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip() or not line.startswith("data:"):
                                continue
                            payload = line[5:].strip()
                            if payload == "[DONE]":
                                break
                            try:
                                chunk = json.loads(payload)
                            except json.JSONDecodeError:
                                continue
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            chunk_prompt_tokens, chunk_completion_tokens = AIClient._usage(chunk)
                            final_prompt_tokens = chunk_prompt_tokens or final_prompt_tokens
                            final_completion_tokens = chunk_completion_tokens or final_completion_tokens
                            finish_reason = choice.get("finish_reason")
                            text = (choice.get("delta") or {}).get("content") or ""
                            if text:
                                content_buffer += text
                                if callback:
                                    result = callback(text)
                                    if hasattr(result, "__await__"):
                                        await result
                                yield text
                if finish_reason != "length":
                    await AIClient._emit_async(
                        config, provider, "success", round((time.monotonic() - started) * 1000),
                        scenario, final_prompt_tokens, final_completion_tokens,
                    )
                    return
                continuation_count += 1
                if content_buffer:
                    if current_messages and current_messages[-1].get("role") == "assistant":
                        current_messages[-1]["content"] += content_buffer
                    else:
                        current_messages.append({"role": "assistant", "content": content_buffer})
                if not current_messages or current_messages[-1].get("role") != "user":
                    current_messages.append({"role": "user", "content": "Continue output without repeating prior content."})
            except Exception as exc:
                logger.error("AI %s stream failed: %s", provider, type(exc).__name__)
                await AIClient._emit_async(
                    config, provider, "failed", round((time.monotonic() - started) * 1000),
                    scenario, error_message=type(exc).__name__,
                )
                raise AIClient._error(provider_name, "stream", exc) from exc

    @staticmethod
    async def embeddings(config, texts, scenario: Optional[str] = None):
        provider = getattr(config, "model_type", "other") or "other"
        provider_name = provider_display_name(provider)
        extra = getattr(config, "provider_extra", None)
        api_version = extra.get("api_version") if isinstance(extra, dict) else None
        started = time.monotonic()
        try:
            url = build_url(getattr(config, "base_url", ""), "/embeddings", provider, api_version)
            headers = build_headers(provider, getattr(config, "api_key", None), api_version)
            payload = {"model": getattr(config, "model_name", ""), "input": texts}
            async with httpx.AsyncClient(timeout=TIMEOUT, http2=False) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
            values = [item["embedding"] for item in body.get("data", [])]
            prompt_tokens, completion_tokens = AIClient._usage(body)
            await AIClient._emit_async(
                config, provider, "success", round((time.monotonic() - started) * 1000),
                scenario, prompt_tokens, completion_tokens,
            )
            return values
        except Exception as exc:
            logger.error("AI %s embeddings failed: %s", provider, type(exc).__name__)
            await AIClient._emit_async(
                config, provider, "failed", round((time.monotonic() - started) * 1000) if "started" in locals() else None,
                scenario, error_message=type(exc).__name__,
            )
            raise AIClient._error(provider_name, "embeddings", exc) from exc

    @staticmethod
    async def list_models(config, scenario: Optional[str] = None):
        provider = getattr(config, "model_type", "other") or "other"
        provider_name = provider_display_name(provider)
        extra = getattr(config, "provider_extra", None)
        api_version = extra.get("api_version") if isinstance(extra, dict) else None
        started = time.monotonic()
        try:
            url = build_url(getattr(config, "base_url", ""), "/models", provider, api_version)
            headers = build_headers(provider, getattr(config, "api_key", None), api_version)
            async with httpx.AsyncClient(timeout=TIMEOUT, http2=False) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                body = response.json()
            raw = body.get("data", []) if isinstance(body, dict) else body
            values = []
            for item in raw or []:
                value = item.get("id") or item.get("model") or item.get("name") if isinstance(item, dict) else item
                if value:
                    values.append(str(value))
            result = list(dict.fromkeys(values))
            await AIClient._emit_async(config, provider, "success", round((time.monotonic() - started) * 1000), scenario)
            return result
        except Exception as exc:
            logger.error("AI %s list_models failed: %s", provider, type(exc).__name__)
            await AIClient._emit_async(
                config, provider, "failed", round((time.monotonic() - started) * 1000),
                scenario, error_message=type(exc).__name__,
            )
            raise AIClient._error(provider_name, "list_models", exc) from exc

    @staticmethod
    def chat_sync(config, messages, max_tokens: int = None, scenario: Optional[str] = None) -> Dict[str, Any]:
        provider, provider_name, url, headers, data = AIClient._parts(config, messages, max_tokens, False)
        started = time.monotonic()
        try:
            with httpx.Client(timeout=TIMEOUT, http2=False) as client:
                response = client.post(url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
            prompt_tokens, completion_tokens = AIClient._usage(result)
            AIClient._emit(
                config, provider, "success", round((time.monotonic() - started) * 1000),
                scenario, prompt_tokens, completion_tokens,
            )
            return result
        except Exception as exc:
            logger.error("AI %s sync request failed: %s", provider, type(exc).__name__)
            AIClient._emit(
                config, provider, "failed", round((time.monotonic() - started) * 1000),
                scenario, error_message=type(exc).__name__,
            )
            raise AIClient._error(provider_name, "chat", exc) from exc

    @staticmethod
    def test_connection(config, timeout: int = 30) -> Dict[str, Any]:
        provider = getattr(config, "model_type", "other") or "other"
        provider_name = provider_display_name(provider)
        extra = getattr(config, "provider_extra", None)
        api_version = extra.get("api_version") if isinstance(extra, dict) else None
        started = time.monotonic()
        try:
            url = build_url(getattr(config, "base_url", ""), "/chat/completions", provider, api_version)
            headers = build_headers(provider, getattr(config, "api_key", None), api_version)
            payload = {
                "model": getattr(config, "model_name", ""),
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 16,
                "temperature": 0,
                "stream": False,
            }
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=timeout), http2=False) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
            prompt_tokens, completion_tokens = AIClient._usage(body)
            AIClient._emit(
                config, provider, "success", round((time.monotonic() - started) * 1000),
                "test_connection", prompt_tokens, completion_tokens,
            )
            return {"success": True, "message": "connection successful", "response": body}
        except Exception as exc:
            logger.error("AI %s connection test failed: %s", provider, type(exc).__name__)
            AIClient._emit(
                config, provider, "failed", round((time.monotonic() - started) * 1000),
                "test_connection", error_message=type(exc).__name__,
            )
            return {"success": False, "message": f"{provider_name} connection failed"}
