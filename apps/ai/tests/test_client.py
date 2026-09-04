from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.client import AIClient


class ClientTests(SimpleTestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            model_type="deepseek",
            api_key="secret",
            base_url="https://api.example.com/v1",
            model_name="deepseek-chat",
            max_tokens=100,
            temperature=0.1,
            top_p=0.9,
            role="writer",
        )

    async def test_chat_delegates_to_httpx(self):
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "ok"}}]},
            raise_for_status=lambda: None,
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.post.return_value = response
        with patch("apps.ai.client.httpx.AsyncClient", return_value=client), patch(
            "apps.ai.client.AIClient._emit_async", new=AsyncMock()
        ) as emitted:
            result = await AIClient.chat(self.config, [{"role": "user", "content": "hi"}])
        self.assertEqual(result["choices"][0]["message"]["content"], "ok")
        client.post.assert_awaited_once()
        emitted.assert_awaited_once()
        self.assertEqual(emitted.await_args.args[2], "success")

    async def test_chat_records_usage_without_exposing_response(self):
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {
                "choices": [],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
            raise_for_status=lambda: None,
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.post.return_value = response
        with patch("apps.ai.client.httpx.AsyncClient", return_value=client), patch(
            "apps.ai.client.AIClient._emit_async", new=AsyncMock()
        ) as emitted:
            await AIClient.chat(self.config, [])
        self.assertEqual(emitted.await_args.args[5:7], (11, 7))

    async def test_chat_stream_yields_chunks_and_calls_callback(self):
        class StreamResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def aiter_lines(self):
                for line in (
                    'data: {"choices":[{"delta":{"content":"a"},"finish_reason":null}]}',
                    'data: {"choices":[{"delta":{"content":"b"},"finish_reason":"stop"}]}',
                    "data: [DONE]",
                ):
                    yield line

        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.stream = MagicMock(return_value=StreamResponse())
        callback = AsyncMock()
        with patch("apps.ai.client.httpx.AsyncClient", return_value=client):
            chunks = [chunk async for chunk in AIClient.chat_stream(self.config, [], callback=callback)]
        self.assertEqual(chunks, ["a", "b"])
        self.assertEqual(callback.await_count, 2)
