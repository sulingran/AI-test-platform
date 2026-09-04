from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AiCallRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(blank=True, default="", max_length=30)),
                ("model_name", models.CharField(blank=True, default="", max_length=200)),
                ("role", models.CharField(blank=True, default="", max_length=30)),
                ("scenario", models.CharField(blank=True, default="general", max_length=80)),
                ("config_id", models.IntegerField(blank=True, null=True)),
                ("created_by_id", models.IntegerField(blank=True, null=True)),
                ("status", models.CharField(choices=[("success", "Success"), ("failed", "Failed")], default="success", max_length=10)),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("prompt_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("completion_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("total_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("cost_estimate", models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "ai_call_records",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="AiModelPricing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=30)),
                ("model_keyword", models.CharField(blank=True, default="", max_length=100)),
                ("input_per_million", models.DecimalField(decimal_places=4, max_digits=10)),
                ("output_per_million", models.DecimalField(decimal_places=4, max_digits=10)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "ai_model_pricing",
                "ordering": ("provider", "model_keyword"),
            },
        ),
        migrations.AddIndex(
            model_name="aicallrecord",
            index=models.Index(fields=["created_at"], name="ai_call_created_idx"),
        ),
        migrations.AddIndex(
            model_name="aicallrecord",
            index=models.Index(fields=["role", "status"], name="ai_call_role_status_idx"),
        ),
        migrations.AddIndex(
            model_name="aicallrecord",
            index=models.Index(fields=["provider", "model_name"], name="ai_call_provider_model_idx"),
        ),
        migrations.AddConstraint(
            model_name="aimodelpricing",
            constraint=models.UniqueConstraint(
                fields=("provider", "model_keyword"),
                name="ai_pricing_provider_keyword_uniq",
            ),
        ),
    ]
