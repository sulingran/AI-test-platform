from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.observability import estimate_cost, emit, get_scenario, reset_scenario, set_scenario


class ObservabilityTests(SimpleTestCase):
    def test_emit_is_non_blocking_when_storage_is_unavailable(self):
        with patch("apps.ai.observability.AiCallRecord.objects.create", side_effect=RuntimeError("db unavailable")):
            emit(provider="deepseek", model_name="demo", status="success")

    def test_estimate_cost_uses_model_keyword_and_decimal_math(self):
        pricing = SimpleNamespace(
            model_keyword="demo",
            input_per_million=Decimal("2.5"),
            output_per_million=Decimal("5"),
        )
        manager = MagicMock()
        manager.filter.return_value = [pricing]
        with patch("apps.ai.models.AiModelPricing.objects", manager):
            result = estimate_cost("deepseek", "demo-large", 1000, 2000)
        self.assertEqual(result, Decimal("0.012500"))

    def test_scenario_context_can_be_reset(self):
        token = set_scenario("requirement_analysis")
        try:
            self.assertEqual(get_scenario(), "requirement_analysis")
        finally:
            reset_scenario(token)
        self.assertIsNone(get_scenario())
