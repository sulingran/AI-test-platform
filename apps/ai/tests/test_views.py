from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.views import AiCallRecordViewSet


class AiUsageViewTests(SimpleTestCase):
    def test_stats_sums_tokens_and_cost(self):
        queryset = MagicMock()
        queryset.aggregate.return_value = {
            "total": 4,
            "failed": 1,
            "avg_latency": 12.5,
            "total_tokens": 900,
            "total_cost": Decimal("0.123456"),
        }
        queryset.filter.return_value.count.return_value = 2
        view = AiCallRecordViewSet()
        request = MagicMock()
        with patch.object(view, "get_queryset", return_value=queryset), patch.object(
            view, "filter_queryset", return_value=queryset
        ):
            response = view.stats(request)
        self.assertEqual(response.data["total_tokens"], 900)
        self.assertEqual(response.data["total_cost"], "0.123456")
        self.assertEqual(response.data["success_rate"], 0.75)
