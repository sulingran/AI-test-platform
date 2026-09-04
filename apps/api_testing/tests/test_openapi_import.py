from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.api_testing.openapi_import import (
    OpenAPIImporter,
    OpenAPIParseError,
    OpenAPISpecParser,
    endpoint_to_request_data,
)
from apps.api_testing.utils import _params_to_dict, _replace_path_params, request_body_kwargs


OPENAPI_SPEC = """
openapi: 3.0.3
info:
  title: Pet API
  version: 1.0.0
servers:
  - url: https://api.example.com/{version}
    variables:
      version:
        default: v1
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    PetInput:
      type: object
      required: [name, password]
      properties:
        name:
          type: string
          example: Momo
        password:
          type: string
          example: should-not-be-stored
paths:
  /pets/{petId}:
    get:
      summary: Get pet
      tags: [Pets]
      security:
        - bearerAuth: []
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: integer
            minimum: 1
        - name: verbose
          in: query
          schema:
            type: boolean
            default: false
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {type: integer}
  /pets:
    post:
      summary: Create pet
      tags: [Pets]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PetInput'
      responses:
        '201':
          description: created
"""


SWAGGER_SPEC = """
swagger: '2.0'
info: {title: Form API, version: '1'}
host: example.test
basePath: /v2
schemes: [https]
paths:
  /upload:
    post:
      consumes: [multipart/form-data]
      parameters:
        - {name: title, in: formData, required: true, type: string}
        - {name: file, in: formData, required: true, type: file}
      responses:
        '200': {description: ok}
"""


class OpenAPISpecParserTests(SimpleTestCase):
    def test_parses_openapi_contract_and_redacts_credential_examples(self):
        result = OpenAPISpecParser().parse_content(OPENAPI_SPEC)

        self.assertEqual(result['spec_version'], 'openapi_3.0')
        self.assertEqual(result['base_url'], 'https://api.example.com/v1')
        self.assertEqual(result['endpoint_count'], 2)
        create = next(item for item in result['endpoints'] if item['method'] == 'POST')
        self.assertEqual(
            create['request_body']['schema']['properties']['password']['example'],
            '{{password}}',
        )
        self.assertEqual(create['request_body']['example']['password'], '{{password}}')

        get = next(item for item in result['endpoints'] if item['method'] == 'GET')
        self.assertEqual(get['auth_headers'][0]['value'], 'Bearer {{token}}')
        self.assertIn('200', get['response_schemas'])

    def test_parses_swagger_form_data(self):
        result = OpenAPISpecParser().parse_content(SWAGGER_SPEC)
        endpoint = result['endpoints'][0]

        self.assertEqual(result['spec_version'], 'swagger_2.0')
        self.assertEqual(result['base_url'], 'https://example.test/v2')
        self.assertEqual(endpoint['request_body']['content_type'], 'multipart/form-data')
        self.assertEqual(endpoint['request_body']['schema']['required'], ['title', 'file'])

    def test_rejects_external_references(self):
        content = OPENAPI_SPEC.replace(
            "$ref: '#/components/schemas/PetInput'",
            "$ref: 'file:///etc/passwd'",
        )
        with self.assertRaisesRegex(OpenAPIParseError, '仅支持文档内部'):
            OpenAPISpecParser().parse_content(content)

    def test_converter_preserves_path_and_query_metadata(self):
        endpoint = OpenAPISpecParser().parse_content(OPENAPI_SPEC)['endpoints'][0]
        data = endpoint_to_request_data(endpoint, 'https://override.example/v1')

        self.assertEqual(data['url'], 'https://override.example/v1/pets/{petId}')
        self.assertEqual(data['path_params'][0]['key'], 'petId')
        self.assertTrue(data['path_params'][0]['required'])
        self.assertEqual(data['params'][0]['key'], 'verbose')
        self.assertEqual(data['headers'][0]['value'], 'Bearer {{token}}')


class ImportedRequestExecutionTests(SimpleTestCase):
    def test_query_rows_execute_as_enabled_key_value_pairs(self):
        rows = [
            {'key': 'enabled', 'value': 'yes', 'enabled': True},
            {'key': 'disabled', 'value': 'no', 'enabled': False},
        ]
        self.assertEqual(_params_to_dict(rows), {'enabled': 'yes'})

    def test_path_params_do_not_replace_double_brace_variables(self):
        resolver = SimpleNamespace(resolve=lambda value: value)
        result = _replace_path_params(
            '{{base_url}}/pets/{petId}',
            [{'key': 'petId', 'value': '42', 'enabled': True}],
            {},
            resolver,
        )
        self.assertEqual(result, '{{base_url}}/pets/42')

    def test_form_data_uses_multipart_transport(self):
        kwargs = request_body_kwargs(
            'form-data',
            [{'key': 'title', 'value': 'demo', 'enabled': True}],
        )
        self.assertEqual(kwargs, {'files': {'title': (None, 'demo')}})


class OpenAPIImporterTests(SimpleTestCase):
    @patch('apps.api_testing.openapi_import.transaction.atomic')
    @patch('apps.api_testing.openapi_import.ApiRequest.objects.create')
    @patch('apps.api_testing.openapi_import.ApiCollection.objects.get_or_create')
    @patch.object(OpenAPIImporter, '_create_root_collection')
    @patch.object(OpenAPIImporter, '_find_existing')
    def test_only_selected_endpoints_are_created(
        self,
        find_existing,
        create_root,
        get_or_create,
        create_request,
        atomic,
    ):
        endpoints = OpenAPISpecParser().parse_content(OPENAPI_SPEC)['endpoints']
        selected = endpoints[0]['key']
        project = SimpleNamespace(id=11)
        root = SimpleNamespace(id=21)
        tag_collection = SimpleNamespace(id=22)
        find_existing.return_value = None
        create_root.return_value = root
        get_or_create.return_value = (tag_collection, True)
        atomic.return_value.__enter__ = MagicMock()
        atomic.return_value.__exit__ = MagicMock(return_value=False)

        result = OpenAPIImporter.import_selected(
            project=project,
            endpoints=endpoints,
            endpoint_keys=[selected],
            user=SimpleNamespace(id=1),
            document_title='Pet API',
            by_tag=True,
        )

        self.assertEqual(result['created_count'], 1)
        self.assertEqual(result['selected_count'], 1)
        create_request.assert_called_once()
        self.assertEqual(create_request.call_args.kwargs['openapi_path'], endpoints[0]['path'])

    @patch('apps.api_testing.openapi_import.transaction.atomic')
    @patch.object(OpenAPIImporter, '_create_root_collection')
    @patch.object(OpenAPIImporter, '_find_existing')
    def test_update_preserves_assertions_and_scripts(self, find_existing, create_root, atomic):
        endpoint = OpenAPISpecParser().parse_content(OPENAPI_SPEC)['endpoints'][0]
        existing = SimpleNamespace(
            assertions=[{'type': 'status_code', 'expected': 200}],
            pre_request_script='keep-before',
            post_request_script='keep-after',
            save=MagicMock(),
        )
        find_existing.return_value = existing
        atomic.return_value.__enter__ = MagicMock()
        atomic.return_value.__exit__ = MagicMock(return_value=False)

        result = OpenAPIImporter.import_selected(
            project=SimpleNamespace(id=11),
            endpoints=[endpoint],
            endpoint_keys=[endpoint['key']],
            user=SimpleNamespace(id=1),
            document_title='Pet API',
            duplicate_strategy='update',
        )

        self.assertEqual(result['updated_count'], 1)
        self.assertEqual(existing.assertions[0]['expected'], 200)
        self.assertEqual(existing.pre_request_script, 'keep-before')
        self.assertEqual(existing.post_request_script, 'keep-after')
        create_root.assert_not_called()
        updated_fields = existing.save.call_args.kwargs['update_fields']
        self.assertNotIn('assertions', updated_fields)
        self.assertNotIn('pre_request_script', updated_fields)

    def test_unknown_selection_is_rejected(self):
        endpoint = OpenAPISpecParser().parse_content(OPENAPI_SPEC)['endpoints'][0]
        with self.assertRaisesRegex(OpenAPIParseError, '无法识别'):
            OpenAPIImporter.import_selected(
                project=SimpleNamespace(id=11),
                endpoints=[endpoint],
                endpoint_keys=['DELETE /not-in-document'],
                user=SimpleNamespace(id=1),
                document_title='Pet API',
            )
