"""Validate source-controlled prompt seeds without database access."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.ai.prompt_registry import validate_registry


class Command(BaseCommand):
    help = "Validate file-backed prompt versions and print their hashes"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        results = validate_registry()
        if options.get("as_json"):
            self.stdout.write(json.dumps(results, ensure_ascii=True, sort_keys=True))
        else:
            for prompt_type, result in results.items():
                if result.get("ok"):
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[{prompt_type}] v{result['version']} {result['source']} sha256={result['sha256']}"
                        )
                    )
                else:
                    self.stdout.write(self.style.ERROR(f"[{prompt_type}] invalid: {result.get('error', 'empty')}"))
        if not all(result.get("ok") for result in results.values()):
            raise CommandError("Prompt registry validation failed")
