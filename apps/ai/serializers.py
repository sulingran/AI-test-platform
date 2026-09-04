from rest_framework import serializers

from .models import AiCallRecord
from .providers import provider_display_name


class AiCallRecordSerializer(serializers.ModelSerializer):
    provider_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AiCallRecord
        fields = (
            "id", "provider", "provider_display", "model_name", "role", "scenario",
            "status", "status_display", "latency_ms", "prompt_tokens",
            "completion_tokens", "total_tokens", "cost_estimate", "error_message",
            "config_id", "created_by_id", "created_at",
        )
        read_only_fields = fields

    def get_provider_display(self, obj):
        return provider_display_name(obj.provider)
