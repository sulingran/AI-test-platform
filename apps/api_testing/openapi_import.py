"""Safe OpenAPI/Swagger parsing and transactional import services."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

import yaml
from django.db import transaction
from django.db.models import Q

from .models import ApiCollection, ApiRequest


HTTP_METHODS = {'get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'trace'}
MAX_DOCUMENT_NODES = 200_000
MAX_DOCUMENT_DEPTH = 100
MAX_REF_DEPTH = 12


class OpenAPIParseError(ValueError):
    """Raised when an uploaded API description cannot be imported safely."""


def endpoint_key(method: str, path: str) -> str:
    return f'{method.upper()} {path}'


def _sensitive_placeholder(key: str) -> str | None:
    normalized = re.sub(r'[^a-z0-9]', '', str(key).lower())
    if normalized in {'password', 'passwd', 'pwd'} or normalized.endswith('password'):
        return '{{password}}'
    if 'apikey' in normalized:
        return '{{api_key}}'
    if normalized in {'authorization', 'accesstoken', 'refreshtoken', 'idtoken', 'token'} or normalized.endswith('token'):
        return '{{token}}'
    if normalized in {'clientsecret', 'secret'} or normalized.endswith('secret'):
        return '{{secret}}'
    return None


def sanitize_example(value: Any, key_hint: str = '') -> Any:
    """Replace credential-like example values before persistence."""
    placeholder = _sensitive_placeholder(key_hint)
    if placeholder is not None:
        return placeholder
    if isinstance(value, dict):
        return {key: sanitize_example(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_example(item, key_hint) for item in value]
    return value


def sanitize_schema(schema: Any, property_name: str = '') -> Any:
    """Keep JSON Schema structure while redacting credential examples/defaults."""
    if isinstance(schema, list):
        return [sanitize_schema(item, property_name) for item in schema]
    if not isinstance(schema, dict):
        return schema

    result = {}
    sensitive = _sensitive_placeholder(property_name)
    for key, value in schema.items():
        if sensitive and key in {'example', 'default', 'const'}:
            result[key] = sensitive
        elif sensitive and key == 'enum' and isinstance(value, list):
            result[key] = [sensitive]
        elif key == 'properties' and isinstance(value, dict):
            result[key] = {
                prop_name: sanitize_schema(prop_schema, prop_name)
                for prop_name, prop_schema in value.items()
            }
        else:
            result[key] = sanitize_schema(value, property_name)
    return result


class OpenAPISpecParser:
    """Parse OpenAPI 3.x and Swagger 2.0 without resolving external references."""

    def parse_file(self, field_file) -> dict:
        field_file.open('rb')
        try:
            content = field_file.read()
        finally:
            field_file.close()
        return self.parse_content(content)

    def parse_content(self, content: str | bytes) -> dict:
        if isinstance(content, bytes):
            try:
                content = content.decode('utf-8-sig')
            except UnicodeDecodeError as exc:
                raise OpenAPIParseError('文档必须使用 UTF-8 编码') from exc
        if not isinstance(content, str) or not content.strip():
            raise OpenAPIParseError('文档内容为空')

        try:
            if content.lstrip().startswith(('{', '[')):
                spec = json.loads(content)
            else:
                spec = yaml.safe_load(content)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise OpenAPIParseError(f'JSON/YAML 格式错误: {exc}') from exc

        if not isinstance(spec, dict):
            raise OpenAPIParseError('文档根节点必须是对象')
        self._validate_document_shape(spec)

        spec_version = self._detect_version(spec)
        endpoints = self._extract_endpoints(spec)
        if not endpoints:
            raise OpenAPIParseError('文档中没有可导入的 HTTP 接口')

        info = spec.get('info') if isinstance(spec.get('info'), dict) else {}
        base_url = self._extract_base_url(spec)
        groups = defaultdict(list)
        for item in endpoints:
            groups[(item.get('tags') or ['未分组'])[0]].append(item)

        return {
            'spec_version': spec_version,
            'title': str(info.get('title') or 'Imported API')[:200],
            'version': str(info.get('version') or ''),
            'base_url': base_url,
            'endpoint_count': len(endpoints),
            'tags': sorted(groups),
            'endpoints': endpoints,
            'groups': [{'tag': tag, 'endpoints': items} for tag, items in groups.items()],
        }

    def _validate_document_shape(self, spec: dict) -> None:
        if 'openapi' not in spec and 'swagger' not in spec:
            raise OpenAPIParseError('缺少 openapi 或 swagger 版本字段')
        if not isinstance(spec.get('paths'), dict):
            raise OpenAPIParseError('paths 必须是对象')

        node_count = 0
        seen_objects = set()
        stack = [(spec, 0)]
        while stack:
            value, depth = stack.pop()
            if depth > MAX_DOCUMENT_DEPTH:
                raise OpenAPIParseError('文档嵌套层级过深')
            if isinstance(value, (dict, list)):
                marker = id(value)
                if marker in seen_objects:
                    continue
                seen_objects.add(marker)
                node_count += 1
                if node_count > MAX_DOCUMENT_NODES:
                    raise OpenAPIParseError('文档结构过大')
            if isinstance(value, dict):
                ref = value.get('$ref')
                if ref is not None and (not isinstance(ref, str) or not ref.startswith('#/')):
                    raise OpenAPIParseError('为防止读取服务器文件或远程地址，仅支持文档内部 $ref')
                stack.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                stack.extend((item, depth + 1) for item in value)

    @staticmethod
    def _detect_version(spec: dict) -> str:
        if 'openapi' in spec:
            version = str(spec['openapi'])
            if version.startswith('3.1'):
                return 'openapi_3.1'
            if version.startswith('3.0'):
                return 'openapi_3.0'
            raise OpenAPIParseError(f'暂不支持 OpenAPI {version}')
        version = str(spec.get('swagger', ''))
        if version.startswith('2.0'):
            return 'swagger_2.0'
        raise OpenAPIParseError(f'暂不支持 Swagger {version}')

    @staticmethod
    def _resolve_pointer(spec: dict, ref: str) -> Any:
        current: Any = spec
        for part in ref[2:].split('/'):
            part = part.replace('~1', '/').replace('~0', '~')
            if not isinstance(current, dict) or part not in current:
                raise OpenAPIParseError(f'无法解析引用: {ref}')
            current = current[part]
        return current

    def _resolve_node(
        self,
        spec: dict,
        value: Any,
        depth: int = 0,
        active_refs: frozenset[str] = frozenset(),
    ) -> Any:
        if depth > MAX_REF_DEPTH:
            return {'type': 'object', 'x-ref-depth-limited': True}
        if isinstance(value, list):
            return [self._resolve_node(spec, item, depth + 1, active_refs) for item in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            ref = value['$ref']
            if ref in active_refs:
                return {'type': 'object', 'x-recursive-ref': ref}
            target = self._resolve_pointer(spec, ref)
            resolved = self._resolve_node(spec, target, depth + 1, active_refs | {ref})
            if isinstance(resolved, dict):
                siblings = {key: item for key, item in value.items() if key != '$ref'}
                if siblings:
                    resolved = {**resolved, **self._resolve_node(spec, siblings, depth + 1, active_refs)}
            return resolved
        return {
            key: self._resolve_node(spec, item, depth + 1, active_refs)
            for key, item in value.items()
        }

    @staticmethod
    def _media_entry(content: Any) -> tuple[str, dict] | tuple[None, None]:
        if not isinstance(content, dict) or not content:
            return None, None
        preferred = ('application/json', 'application/*+json', '*/*',
                     'application/x-www-form-urlencoded', 'multipart/form-data')
        for media_type in preferred:
            if media_type in content and isinstance(content[media_type], dict):
                return media_type, content[media_type]
        for media_type, entry in content.items():
            if isinstance(entry, dict):
                return str(media_type), entry
        return None, None

    def _example_from_schema(self, schema: Any, depth: int = 0, key_hint: str = '') -> Any:
        if depth > MAX_REF_DEPTH or not isinstance(schema, dict):
            return None
        placeholder = _sensitive_placeholder(key_hint)
        if placeholder:
            return placeholder
        for key in ('example', 'default', 'const'):
            if key in schema:
                return sanitize_example(schema[key], key_hint)
        if isinstance(schema.get('enum'), list) and schema['enum']:
            return sanitize_example(schema['enum'][0], key_hint)
        for union_key in ('oneOf', 'anyOf'):
            options = schema.get(union_key)
            if isinstance(options, list) and options:
                return self._example_from_schema(options[0], depth + 1, key_hint)
        if isinstance(schema.get('allOf'), list):
            merged = {}
            for item in schema['allOf']:
                generated = self._example_from_schema(item, depth + 1, key_hint)
                if isinstance(generated, dict):
                    merged.update(generated)
            if merged:
                return merged

        schema_type = schema.get('type')
        if not schema_type and 'properties' in schema:
            schema_type = 'object'
        if schema_type == 'object':
            return {
                name: self._example_from_schema(prop, depth + 1, str(name))
                for name, prop in (schema.get('properties') or {}).items()
            }
        if schema_type == 'array':
            item = self._example_from_schema(schema.get('items') or {}, depth + 1, key_hint)
            return [] if item is None else [item]
        if schema_type == 'integer':
            return schema.get('minimum', 0)
        if schema_type == 'number':
            return schema.get('minimum', 0)
        if schema_type == 'boolean':
            return False
        if schema_type == 'string' or not schema_type:
            formats = {
                'date': '2024-01-01',
                'date-time': '2024-01-01T00:00:00Z',
                'email': 'user@example.com',
                'uri': 'https://example.com',
                'uuid': '550e8400-e29b-41d4-a716-446655440000',
                'password': '{{password}}',
            }
            return formats.get(schema.get('format'), '')
        return None

    @staticmethod
    def _named_example(examples: Any) -> Any:
        if not isinstance(examples, dict):
            return None
        for item in examples.values():
            if isinstance(item, dict) and 'value' in item:
                return item['value']
            return item
        return None

    def _entry_example(self, entry: dict, schema: dict) -> Any:
        if entry.get('example') is not None:
            return sanitize_example(entry['example'])
        named = self._named_example(entry.get('examples'))
        if named is not None:
            return sanitize_example(named)
        return sanitize_example(self._example_from_schema(schema))

    def _extract_parameters(self, spec: dict, parameters: list) -> list[dict]:
        extracted = []
        for raw in parameters:
            param = self._resolve_node(spec, raw)
            if not isinstance(param, dict) or param.get('in') in {'body', 'formData'}:
                continue
            schema_source = param.get('schema') or {
                key: param[key]
                for key in ('type', 'format', 'enum', 'default', 'minimum', 'maximum', 'items')
                if key in param
            }
            schema = sanitize_schema(self._resolve_node(spec, schema_source), str(param.get('name', '')))
            example = param.get('example')
            if example is None:
                example = param.get('x-example')
            if example is None:
                example = self._named_example(param.get('examples'))
            if example is None:
                example = self._example_from_schema(schema, key_hint=str(param.get('name', '')))
            extracted.append({
                'name': str(param.get('name') or ''),
                'in': str(param.get('in') or 'query'),
                'required': bool(param.get('required')),
                'description': str(param.get('description') or ''),
                'schema': schema,
                'type': str(schema.get('type') or param.get('type') or ''),
                'example': sanitize_example(example, str(param.get('name', ''))),
            })
        return extracted

    def _extract_request_body(self, spec: dict, operation: dict) -> dict | None:
        request_body = operation.get('requestBody')
        if request_body:
            request_body = self._resolve_node(spec, request_body)
            media_type, entry = self._media_entry(request_body.get('content'))
            if not entry:
                return None
            schema = sanitize_schema(self._resolve_node(spec, entry.get('schema') or {}))
            return {
                'content_type': media_type,
                'schema': schema,
                'example': self._entry_example(entry, schema),
                'required': bool(request_body.get('required')),
                'description': str(request_body.get('description') or ''),
            }

        swagger_params = [
            self._resolve_node(spec, item)
            for item in (operation.get('parameters') or [])
            if isinstance(item, dict)
        ]
        body_param = next((item for item in swagger_params if item.get('in') == 'body'), None)
        if body_param:
            schema = sanitize_schema(self._resolve_node(spec, body_param.get('schema') or {}))
            example = body_param.get('x-example', body_param.get('example'))
            if example is None:
                example = self._example_from_schema(schema)
            return {
                'content_type': 'application/json',
                'schema': schema,
                'example': sanitize_example(example),
                'required': bool(body_param.get('required')),
                'description': str(body_param.get('description') or ''),
            }

        form_params = [item for item in swagger_params if item.get('in') == 'formData']
        if not form_params:
            return None
        properties = {}
        required = []
        for param in form_params:
            name = str(param.get('name') or '')
            properties[name] = sanitize_schema({
                key: param[key]
                for key in ('type', 'format', 'enum', 'default', 'x-example')
                if key in param
            }, name)
            if param.get('required'):
                required.append(name)
        schema = {'type': 'object', 'properties': properties}
        if required:
            schema['required'] = required
        consumes = operation.get('consumes') or spec.get('consumes') or []
        media_type = 'multipart/form-data' if any('multipart' in str(item) for item in consumes) else 'application/x-www-form-urlencoded'
        return {
            'content_type': media_type,
            'schema': schema,
            'example': self._example_from_schema(schema),
            'required': bool(required),
            'description': '',
        }

    def _extract_responses(self, spec: dict, operation: dict) -> tuple[dict, dict]:
        schemas = {}
        examples = {}
        for status_code, raw_response in (operation.get('responses') or {}).items():
            response = self._resolve_node(spec, raw_response)
            if not isinstance(response, dict):
                continue
            media_type, entry = self._media_entry(response.get('content'))
            if entry:
                schema = sanitize_schema(self._resolve_node(spec, entry.get('schema') or {}))
                example = self._entry_example(entry, schema)
            else:
                schema = sanitize_schema(self._resolve_node(spec, response.get('schema') or {}))
                example = self._named_example(response.get('examples'))
                if example is None and schema:
                    example = self._example_from_schema(schema)
                example = sanitize_example(example)
            if schema:
                schemas[str(status_code)] = schema
            if example is not None:
                examples[str(status_code)] = example
        return schemas, examples

    def _extract_security(self, spec: dict, operation: dict) -> tuple[list, list, dict]:
        schemes = (spec.get('components') or {}).get('securitySchemes') or spec.get('securityDefinitions') or {}
        requirements = operation['security'] if 'security' in operation else spec.get('security', [])
        if not requirements or not isinstance(requirements, list):
            return [], [], {}

        selected = requirements[0] if requirements else {}
        headers = []
        query = []
        metadata = []
        for scheme_name in selected:
            raw_scheme = schemes.get(scheme_name)
            if not isinstance(raw_scheme, dict):
                continue
            scheme = self._resolve_node(spec, raw_scheme)
            scheme_type = scheme.get('type', '')
            location = 'header'
            header_name = 'Authorization'
            placeholder = 'Bearer {{token}}'
            if scheme_type == 'apiKey':
                location = scheme.get('in', 'header')
                header_name = scheme.get('name') or 'X-API-Key'
                placeholder = '{{api_key}}'
            elif scheme_type == 'basic' or (scheme_type == 'http' and scheme.get('scheme') == 'basic'):
                placeholder = 'Basic {{basic_auth}}'
            elif scheme_type not in {'http', 'oauth2', 'openIdConnect'}:
                continue

            row = {
                'key': header_name,
                'value': placeholder,
                'enabled': True,
                'description': f'{scheme_name} ({scheme_type})',
                'required': True,
                'param_type': 'string',
            }
            if location == 'query':
                query.append(row)
            else:
                headers.append(row)
            metadata.append({
                'name': str(scheme_name),
                'type': str(scheme_type),
                'in': str(location),
                'key': str(header_name),
                'placeholder': placeholder,
            })
        return headers, query, {'schemes': metadata} if metadata else {}

    def _extract_endpoints(self, spec: dict) -> list[dict]:
        endpoints = []
        for path, path_item in spec.get('paths', {}).items():
            path_item = self._resolve_node(spec, path_item)
            if not isinstance(path_item, dict):
                continue
            shared_params = path_item.get('parameters') or []
            for method, operation in path_item.items():
                if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                operation = self._resolve_node(spec, operation)
                merged_params = {}
                for item in list(shared_params) + list(operation.get('parameters') or []):
                    resolved = self._resolve_node(spec, item)
                    if isinstance(resolved, dict):
                        merged_params[(resolved.get('name'), resolved.get('in'))] = resolved
                parameters = self._extract_parameters(spec, list(merged_params.values()))
                auth_headers, auth_query, auth = self._extract_security(spec, operation)
                parameters.extend({
                    'name': item['key'],
                    'in': 'query',
                    'required': True,
                    'description': item['description'],
                    'schema': {'type': 'string'},
                    'type': 'string',
                    'example': item['value'],
                } for item in auth_query)
                response_schemas, response_examples = self._extract_responses(spec, operation)
                method_upper = method.upper()
                summary = str(operation.get('summary') or '')
                operation_id = str(operation.get('operationId') or '')
                endpoints.append({
                    'key': endpoint_key(method_upper, str(path)),
                    'path': str(path),
                    'method': method_upper,
                    'summary': summary,
                    'description': str(operation.get('description') or ''),
                    'operation_id': operation_id,
                    'tags': [str(item)[:200] for item in (operation.get('tags') or [])],
                    'deprecated': bool(operation.get('deprecated')),
                    'name': (summary or operation_id or f'{method_upper} {path}')[:200],
                    'parameters': parameters,
                    'request_body': self._extract_request_body(spec, operation),
                    'response_schemas': response_schemas,
                    'response_examples': response_examples,
                    'auth_headers': auth_headers,
                    'auth': auth,
                })
        return endpoints

    @staticmethod
    def _extract_base_url(spec: dict) -> str:
        servers = spec.get('servers') or []
        if servers and isinstance(servers[0], dict):
            server = servers[0]
            url = str(server.get('url') or '')
            for name, config in (server.get('variables') or {}).items():
                default = config.get('default', '') if isinstance(config, dict) else ''
                url = url.replace('{' + str(name) + '}', str(default))
            return url
        host = spec.get('host')
        if host:
            scheme = str((spec.get('schemes') or ['https'])[0])
            return f"{scheme}://{host}{spec.get('basePath') or ''}"
        return ''


def endpoint_to_request_data(endpoint: dict, base_url: str = '') -> dict:
    path = str(endpoint.get('path') or '')
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}" if base_url else f'{{{{base_url}}}}/{path.lstrip("/")}'
    headers = list(endpoint.get('auth_headers') or [])
    params = []
    path_params = []
    for param in endpoint.get('parameters') or []:
        row = {
            'key': param.get('name', ''),
            'value': '' if param.get('example') is None else str(param.get('example')),
            'enabled': bool(param.get('required')),
            'description': param.get('description', ''),
            'param_type': param.get('type', ''),
            'required': bool(param.get('required')),
        }
        if param.get('in') == 'query':
            params.append(row)
        elif param.get('in') == 'path':
            row['enabled'] = True
            path_params.append(row)
        elif param.get('in') == 'header':
            headers.append(row)

    request_body = endpoint.get('request_body') or {}
    content_type = request_body.get('content_type', '')
    if content_type and not any(item.get('key', '').lower() == 'content-type' for item in headers):
        headers.append({
            'key': 'Content-Type',
            'value': content_type,
            'enabled': True,
            'description': 'OpenAPI request body content type',
            'param_type': 'string',
            'required': True,
        })
    if not any(item.get('key', '').lower() == 'accept' for item in headers):
        headers.append({
            'key': 'Accept', 'value': 'application/json', 'enabled': True,
            'description': '', 'param_type': 'string', 'required': False,
        })

    example = request_body.get('example')
    if not request_body:
        body = {'type': 'none', 'data': None}
    elif 'json' in content_type:
        body = {'type': 'json', 'data': example if example is not None else {}}
    elif content_type == 'multipart/form-data':
        body = {'type': 'form-data', 'data': _example_to_rows(example)}
    elif content_type == 'application/x-www-form-urlencoded':
        body = {'type': 'x-www-form-urlencoded', 'data': _example_to_rows(example)}
    else:
        body = {'type': 'raw', 'data': example if example is not None else ''}

    description = '\n'.join(filter(None, [endpoint.get('summary'), endpoint.get('description')]))
    return {
        'name': endpoint.get('name') or endpoint_key(endpoint.get('method', 'GET'), path),
        'description': description,
        'request_type': 'HTTP',
        'method': endpoint.get('method', 'GET'),
        'url': url,
        'headers': headers,
        'params': params,
        'body': body,
        'auth': endpoint.get('auth') or {},
        'request_schema': request_body.get('schema') or {},
        'response_schemas': endpoint.get('response_schemas') or {},
        'path_params': path_params,
        'response_examples': endpoint.get('response_examples') or {},
        'deprecated': bool(endpoint.get('deprecated')),
        'openapi_path': path,
    }


def _example_to_rows(example: Any) -> list[dict]:
    if not isinstance(example, dict):
        return []
    return [
        {
            'key': str(key),
            'value': json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value),
            'enabled': True,
            'description': '',
            'type': 'text',
        }
        for key, value in example.items()
    ]


class OpenAPIImporter:
    """Import selected endpoints while preserving existing user assertions/scripts."""

    CONTRACT_FIELDS = (
        'name', 'description', 'request_type', 'method', 'url', 'headers', 'params',
        'body', 'auth', 'request_schema', 'response_schemas', 'path_params',
        'response_examples', 'deprecated', 'openapi_path',
    )

    @classmethod
    def import_selected(
        cls,
        *,
        project,
        endpoints: list[dict],
        endpoint_keys: list[str],
        user,
        document_title: str,
        base_url: str = '',
        by_tag: bool = True,
        duplicate_strategy: str = 'skip',
        root_collection=None,
    ) -> dict:
        selected_keys = set(endpoint_keys)
        selected = [item for item in endpoints if item.get('key') in selected_keys]
        found_keys = {item.get('key') for item in selected}
        unknown = selected_keys - found_keys
        if unknown:
            raise OpenAPIParseError(f'包含无法识别的端点: {sorted(unknown)[0]}')

        created_count = 0
        updated_count = 0
        skipped_count = 0
        tag_collections = {}

        with transaction.atomic():
            for endpoint in selected:
                data = endpoint_to_request_data(endpoint, base_url)
                existing = cls._find_existing(project, data)
                if existing and duplicate_strategy == 'skip':
                    skipped_count += 1
                    continue
                if existing:
                    for field in cls.CONTRACT_FIELDS:
                        setattr(existing, field, data[field])
                    existing.save(update_fields=[*cls.CONTRACT_FIELDS, 'updated_at'])
                    updated_count += 1
                    continue

                if root_collection is None:
                    root_collection = cls._create_root_collection(project, document_title)
                target = root_collection
                if by_tag:
                    tag = str((endpoint.get('tags') or ['未分组'])[0])[:200]
                    if tag not in tag_collections:
                        tag_collections[tag], _ = ApiCollection.objects.get_or_create(
                            project=project,
                            parent=root_collection,
                            name=tag,
                            defaults={'description': f'OpenAPI Tag: {tag}'},
                        )
                    target = tag_collections[tag]
                ApiRequest.objects.create(
                    collection=target,
                    created_by=user,
                    order=created_count,
                    **data,
                )
                created_count += 1

        return {
            'created_count': created_count,
            'updated_count': updated_count,
            'skipped_count': skipped_count,
            'selected_count': len(selected),
            'collection_id': root_collection.id if root_collection else None,
        }

    @staticmethod
    def _find_existing(project, data: dict):
        candidates = ApiRequest.objects.filter(
            collection__project=project,
            method=data['method'],
        )
        return candidates.filter(
            Q(openapi_path=data['openapi_path']) | Q(openapi_path='', url=data['url'])
        ).first()

    @staticmethod
    def _create_root_collection(project, title: str):
        base_name = (title or 'Imported API')[:200]
        name = base_name
        suffix = 2
        while ApiCollection.objects.filter(project=project, parent__isnull=True, name=name).exists():
            marker = f' ({suffix})'
            name = f'{base_name[:200 - len(marker)]}{marker}'
            suffix += 1
        return ApiCollection.objects.create(
            project=project,
            name=name,
            description='由 OpenAPI/Swagger 文档导入',
        )
