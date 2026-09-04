"""Database models for non-invasive AI call observability."""

from django.db import models


class AiCallRecord(models.Model):
    """One request sent to an AI provider.

    ``created_by_id`` and ``config_id`` are plain IDs on purpose. The existing
    project has no complete migration graph for its user/config apps, so this
    feature must not introduce cross-app foreign-key dependencies.
    """

    STATUS_CHOICES = (
        ("success", "Success"),
        ("failed", "Failed"),
    )

    provider = models.CharField(max_length=30, blank=True, default="")
    model_name = models.CharField(max_length=200, blank=True, default="")
    role = models.CharField(max_length=30, blank=True, default="")
    scenario = models.CharField(max_length=80, blank=True, default="general")
    config_id = models.IntegerField(null=True, blank=True)
    created_by_id = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="success")
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)
    cost_estimate = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_call_records"
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=("created_at",), name="ai_call_created_idx"),
            models.Index(fields=("role", "status"), name="ai_call_role_status_idx"),
            models.Index(fields=("provider", "model_name"), name="ai_call_provider_model_idx"),
        )

    def __str__(self):
        return f"{self.provider}/{self.model_name} {self.status}"


class AiModelPricing(models.Model):
    """Optional USD pricing per one million input/output tokens."""

    provider = models.CharField(max_length=30)
    model_keyword = models.CharField(max_length=100, blank=True, default="")
    input_per_million = models.DecimalField(max_digits=10, decimal_places=4)
    output_per_million = models.DecimalField(max_digits=10, decimal_places=4)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_model_pricing"
        ordering = ("provider", "model_keyword")
        constraints = (
            models.UniqueConstraint(
                fields=("provider", "model_keyword"),
                name="ai_pricing_provider_keyword_uniq",
            ),
        )

    def __str__(self):
        return f"{self.provider}/{self.model_keyword or '*'}"
