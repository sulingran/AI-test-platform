from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase

from apps.requirement_analysis.models import AIModelService


class GatewayAdapterTests(SimpleTestCase):
    async def test_chat_adapter_preserves_public_signature(self):
        config = SimpleNamespace(model_name="demo")
        expected = {"choices": []}
        with patch("apps.requirement_analysis.models.AIClient.chat", new=AsyncMock(return_value=expected)) as mocked:
            result = await AIModelService.call_openai_compatible_api(config, [{"role": "user", "content": "hi"}], 8)
        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with(config, [{"role": "user", "content": "hi"}], max_tokens=8, scenario="requirement_analysis")

    async def test_stream_adapter_forwards_chunks(self):
        async def fake_stream(*args, **kwargs):
            yield "one"
            yield "two"

        config = SimpleNamespace(model_name="demo")
        with patch("apps.requirement_analysis.models.AIClient.chat_stream", side_effect=fake_stream) as mocked:
            result = [chunk async for chunk in AIModelService.call_openai_compatible_api_stream(config, [])]
        self.assertEqual(result, ["one", "two"])
        mocked.assert_called_once()
