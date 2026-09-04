from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.ai.auth import build_headers, build_url
from apps.ai.client import AIClient


class AuthAndClientTests(SimpleTestCase):
    def test_provider_headers(self):
        self.assertEqual(build_headers("deepseek", "secret"), {
            "Content-Type": "application/json",
            "Authorization": "Bearer secret",
        })
        self.assertEqual(build_headers("qwen", "secret"), {
            "Content-Type": "application/json",
            "api-key": "secret",
        })

    def test_url_normalization(self):
        self.assertEqual(
            build_url("https://api.example.com", "/chat/completions", "other"),
            "https://api.example.com/v1/chat/completions",
        )
        self.assertEqual(
            build_url("https://api.example.com/v4", "/models", "other"),
            "https://api.example.com/v4/models",
        )
        self.assertEqual(
            build_url("https://azure.example.com/openai/deployments/demo", "/chat/completions", "azure_openai", "2024-10-21"),
            "https://azure.example.com/openai/deployments/demo/v1/chat/completions?api-version=2024-10-21",
        )

    def test_request_parts_use_config_defaults(self):
        config = SimpleNamespace(
            model_type="deepseek",
            api_key="secret",
            base_url="https://api.example.com/v1/",
            model_name="deepseek-chat",
            max_tokens=123,
            temperature=0.2,
            top_p=0.8,
        )
        provider, _, url, headers, data = AIClient._parts(config, [{"role": "user", "content": "hi"}])
        self.assertEqual(provider, "deepseek")
        self.assertEqual(url, "https://api.example.com/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(data["max_tokens"], 123)
