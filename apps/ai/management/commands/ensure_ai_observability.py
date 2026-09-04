"""Create only missing AI observability tables for legacy installations."""

from django.core.management.base import BaseCommand
from django.db import connections

from apps.ai.models import AiCallRecord, AiModelPricing


class Command(BaseCommand):
    help = "Create missing AI observability tables without altering existing tables"

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument("--check", action="store_true", help="Only report missing tables")

    def handle(self, *args, **options):
        connection = connections[options["database"]]
        models = (AiCallRecord, AiModelPricing)
        existing = set(connection.introspection.table_names())
        missing = [model for model in models if model._meta.db_table not in existing]

        if options.get("check"):
            if missing:
                for model in missing:
                    self.stdout.write(f"missing: {model._meta.db_table}")
                return
            self.stdout.write(self.style.SUCCESS("AI observability tables are ready"))
            return

        if not missing:
            self.stdout.write(self.style.SUCCESS("AI observability tables are already ready"))
            return

        created = []
        with connection.schema_editor() as schema_editor:
            for model in missing:
                schema_editor.create_model(model)
                created.append(model._meta.db_table)
        self.stdout.write(self.style.SUCCESS(f"created: {', '.join(created)}"))
