from django.test import SimpleTestCase

from apps.ai.prompt_registry import available_versions, content_for, content_hash, get_prompt, validate_registry


class PromptRegistryTests(SimpleTestCase):
    def test_legacy_prompts_are_exposed_as_v1(self):
        self.assertEqual(available_versions("writer"), [1])
        self.assertEqual(available_versions("reviewer"), [1])
        writer = get_prompt("writer")
        self.assertEqual(writer["version"], 1)
        self.assertEqual(writer["source"], "docs/tester.md")
        self.assertTrue(writer["content"].strip())

    def test_hash_is_deterministic(self):
        content = content_for("writer")
        self.assertEqual(content_hash(content), get_prompt("writer")["sha256"])
        self.assertEqual(content, content_for("writer", version=1))

    def test_registry_validation_is_file_only(self):
        result = validate_registry()
        self.assertTrue(result["writer"]["ok"])
        self.assertTrue(result["reviewer"]["ok"])

    def test_load_defaults_uses_registered_versions(self):
        from apps.requirement_analysis.views import PromptConfigViewSet

        response = PromptConfigViewSet().load_defaults(request=None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["metadata"]["writer"]["version"], 1)
        self.assertEqual(response.data["metadata"]["reviewer"]["source"], "docs/tester_pro.md")
        self.assertTrue(response.data["defaults"]["writer"].strip())
