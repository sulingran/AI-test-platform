import asyncio
import os

from django.test import SimpleTestCase

from apps.ui_automation.runtime_context import (
    REDACTED_VALUE,
    build_runtime_task_description,
    get_allowed_domains,
    normalize_openai_base_url,
    redact_sensitive_data,
    validate_http_url,
)


class RuntimeContextTests(SimpleTestCase):
    def test_windows_proactor_loop_supports_subprocesses(self):
        if os.name != 'nt' or not hasattr(asyncio, 'ProactorEventLoop'):
            self.skipTest('Windows Proactor event loop is not available')

        async def run_command():
            process = await asyncio.create_subprocess_exec('cmd', '/c', 'exit', '0')
            return await process.wait()

        loop = asyncio.ProactorEventLoop()
        try:
            self.assertEqual(loop.run_until_complete(run_command()), 0)
        finally:
            loop.close()

    def test_normalize_openai_base_url_strips_chat_completions_endpoint(self):
        self.assertEqual(
            normalize_openai_base_url(
                "http://intranet-ai.example.test:19096/v1/chat/completions"
            ),
            "http://intranet-ai.example.test:19096/v1",
        )

    def test_normalize_openai_base_url_preserves_or_adds_api_version(self):
        self.assertEqual(
            normalize_openai_base_url("https://api.example.test/v1/"),
            "https://api.example.test/v1",
        )
        self.assertEqual(
            normalize_openai_base_url("https://api.example.test"),
            "https://api.example.test/v1",
        )

    def test_validate_http_url_accepts_intranet_https_url(self):
        url = "https://192.0.2.10:9993/"

        self.assertEqual(validate_http_url(url), url)

    def test_validate_http_url_rejects_non_http_schemes(self):
        for url in ("javascript:alert(1)", "file:///C:/Windows/win.ini"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_http_url(url)

    def test_build_runtime_task_adds_one_time_context_without_mutating_original(self):
        original_task = "验证登录后的首页标题"

        runtime_task = build_runtime_task_description(
            original_task,
            target_url="https://intranet.example.test/",
            login_url="https://intranet.example.test/login",
            login_username="temporary-user",
            login_password="temporary-password",
        )

        self.assertEqual(original_task, "验证登录后的首页标题")
        self.assertIn(original_task, runtime_task)
        self.assertIn("https://intranet.example.test/login", runtime_task)
        self.assertNotIn("temporary-user", runtime_task)
        self.assertNotIn("temporary-password", runtime_task)
        self.assertIn("<secret>login_username</secret>", runtime_task)
        self.assertIn("<secret>login_password</secret>", runtime_task)

    def test_get_allowed_domains_deduplicates_target_hosts(self):
        domains = get_allowed_domains(
            "https://192.0.2.10:9993/",
            "https://192.0.2.10:9993/login",
        )

        self.assertEqual(domains, ["192.0.2.10"])

    def test_redact_sensitive_data_handles_nested_values_and_sensitive_keys(self):
        source = {
            "message": "login temporary-user with temporary-password",
            "nested": [
                "temporary-password",
                {"authorization": "Bearer token-value", "result": "temporary-user"},
            ],
            "password_hint": "must never be stored",
        }

        redacted = redact_sensitive_data(
            source,
            ("temporary-user", "temporary-password"),
        )

        self.assertEqual(
            redacted["message"],
            f"login {REDACTED_VALUE} with {REDACTED_VALUE}",
        )
        self.assertEqual(redacted["nested"][0], REDACTED_VALUE)
        self.assertEqual(redacted["nested"][1]["authorization"], REDACTED_VALUE)
        self.assertEqual(redacted["nested"][1]["result"], REDACTED_VALUE)
        self.assertEqual(redacted["password_hint"], REDACTED_VALUE)
