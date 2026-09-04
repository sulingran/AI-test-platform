"""Create only the missing OpenAPI import table/columns on legacy databases."""

from django.core.management.base import BaseCommand
from django.db import connections

from apps.api_testing.models import ApiDocument, ApiRequest


REQUEST_FIELDS = (
    'request_schema',
    'response_schemas',
    'path_params',
    'response_examples',
    'deprecated',
    'openapi_path',
)


class Command(BaseCommand):
    help = 'Add missing OpenAPI import schema without deleting or rewriting existing data'

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default')
        parser.add_argument('--check', action='store_true', help='Only report missing table/columns')

    def handle(self, *args, **options):
        connection = connections[options['database']]
        existing_tables = set(connection.introspection.table_names())
        request_table = ApiRequest._meta.db_table
        missing_fields = []
        if request_table in existing_tables:
            with connection.cursor() as cursor:
                columns = {
                    item.name
                    for item in connection.introspection.get_table_description(cursor, request_table)
                }
            missing_fields = [
                name for name in REQUEST_FIELDS
                if ApiRequest._meta.get_field(name).column not in columns
            ]
        missing_document_table = ApiDocument._meta.db_table not in existing_tables

        if options['check']:
            if request_table not in existing_tables:
                self.stdout.write(f'missing prerequisite table: {request_table}')
            for name in missing_fields:
                self.stdout.write(f'missing column: {request_table}.{name}')
            if missing_document_table:
                self.stdout.write(f'missing table: {ApiDocument._meta.db_table}')
            if request_table in existing_tables and not missing_fields and not missing_document_table:
                self.stdout.write(self.style.SUCCESS('OpenAPI import schema is ready'))
            return

        if request_table not in existing_tables:
            raise RuntimeError(
                f'基础表 {request_table} 不存在，请先完成项目原有数据库初始化，未执行任何修改。'
            )

        changes = []
        with connection.schema_editor() as schema_editor:
            for name in missing_fields:
                schema_editor.add_field(ApiRequest, ApiRequest._meta.get_field(name))
                changes.append(f'added column {request_table}.{name}')
            if missing_document_table:
                schema_editor.create_model(ApiDocument)
                changes.append(f'created table {ApiDocument._meta.db_table}')

        if changes:
            self.stdout.write(self.style.SUCCESS('; '.join(changes)))
        else:
            self.stdout.write(self.style.SUCCESS('OpenAPI import schema is already ready'))
