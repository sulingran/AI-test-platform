from django.contrib import admin

from .models import AiCallRecord, AiModelPricing


@admin.register(AiCallRecord)
class AiCallRecordAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "provider", "model_name", "role", "scenario",
        "status", "latency_ms", "total_tokens", "cost_estimate",
    )
    list_filter = ("provider", "role", "scenario", "status")
    search_fields = ("provider", "model_name", "role", "scenario")
    readonly_fields = tuple(field.name for field in AiCallRecord._meta.fields)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AiModelPricing)
class AiModelPricingAdmin(admin.ModelAdmin):
    list_display = ("provider", "model_keyword", "input_per_million", "output_per_million", "updated_at")
    list_filter = ("provider",)
    search_fields = ("provider", "model_keyword")
