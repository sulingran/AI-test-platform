from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import Http404
from django.test import SimpleTestCase
from rest_framework import serializers, status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ai.views import AiCallRecordViewSet
from apps.api_testing.access import can_access_api_project
from apps.api_testing.serializers import (
    ApiCollectionSerializer,
    ApiDocumentUploadSerializer,
    ApiRequestSerializer,
    EnvironmentSerializer,
)
from apps.api_testing.models import ApiProject
from apps.api_testing.views import ApiDocumentViewSet, ApiRequestViewSet


def make_user(user_id, *, is_staff=False, is_superuser=False):
    return SimpleNamespace(
        id=user_id,
        is_authenticated=True,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )


def make_project(project_id, owner_id, *, member_ids=()):
    members = MagicMock()
    members.filter.side_effect = lambda **kwargs: SimpleNamespace(
        exists=lambda: kwargs.get('id') in member_ids,
    )
    return SimpleNamespace(
        id=project_id,
        owner_id=owner_id,
        project_type='HTTP',
        members=members,
    )


class ProjectRelationIsolationTests(SimpleTestCase):
    def setUp(self):
        self.user = make_user(1)
        self.own_project = make_project(10, self.user.id)
        self.foreign_project = make_project(20, 2)
        self.request = SimpleNamespace(user=self.user)

    def test_project_access_accepts_owner_and_member_but_rejects_outsider(self):
        member_project = make_project(30, 2, member_ids=(self.user.id,))

        self.assertTrue(can_access_api_project(self.user, self.own_project))
        self.assertTrue(can_access_api_project(self.user, member_project))
        self.assertFalse(can_access_api_project(self.user, self.foreign_project))

    def test_collection_cannot_be_created_in_foreign_project(self):
        serializer = ApiCollectionSerializer(context={'request': self.request})

        with self.assertRaises(serializers.ValidationError):
            serializer.validate({'project': self.foreign_project, 'parent': None})

    def test_request_cannot_be_attached_to_foreign_collection(self):
        collection = SimpleNamespace(project=self.foreign_project)
        serializer = ApiRequestSerializer(context={'request': self.request})

        with self.assertRaises(serializers.ValidationError):
            serializer.validate_collection(collection)

    def test_local_environment_cannot_be_attached_to_foreign_project(self):
        serializer = EnvironmentSerializer(context={'request': self.request})

        with self.assertRaises(serializers.ValidationError):
            serializer.validate({'scope': 'LOCAL', 'project': self.foreign_project})

    def test_openapi_upload_cannot_target_foreign_project(self):
        serializer = ApiDocumentUploadSerializer(context={'request': self.request})

        with self.assertRaises(serializers.ValidationError):
            serializer.validate_project(self.foreign_project)


class ReadIsolationTests(SimpleTestCase):
    @patch('apps.api_testing.views.ApiRequest.objects.filter')
    @patch('apps.api_testing.views.ApiProject.objects.filter')
    def test_request_objects_use_project_scoped_queryset(
        self,
        project_filter,
        request_filter,
    ):
        user = make_user(1)
        allowed_projects = project_filter.return_value
        filtered_requests = request_filter.return_value
        view = ApiRequestViewSet()
        view.request = SimpleNamespace(user=user, query_params={})

        result = view.get_queryset()

        project_filter.assert_called_once()
        request_filter.assert_called_once()
        self.assertIs(result, filtered_requests.distinct.return_value)

    @patch('apps.api_testing.views.accessible_api_projects')
    def test_openapi_documents_are_scoped_to_current_projects(self, accessible_projects):
        allowed_projects = MagicMock(name='allowed_projects')
        accessible_projects.return_value = allowed_projects
        filtered = MagicMock()
        base_queryset = MagicMock()
        base_queryset.all.return_value = base_queryset
        base_queryset.filter.return_value = filtered
        view = ApiDocumentViewSet()
        view.queryset = base_queryset
        view.request = SimpleNamespace(user=make_user(1))

        result = view.get_queryset()

        base_queryset.filter.assert_called_once_with(project__in=allowed_projects)
        self.assertIs(result, filtered.distinct.return_value)

    def test_non_admin_cannot_read_ai_usage_or_costs(self):
        request = APIRequestFactory().get('/api/ai/call-records/')
        force_authenticate(request, user=make_user(1, is_staff=False))
        view = AiCallRecordViewSet.as_view({'get': 'list'})

        response = view(request)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.api_testing.views.accessible_environments')
    @patch('apps.api_testing.views.get_object_or_404')
    @patch('apps.api_testing.views.requests.request')
    def test_request_execution_rejects_inaccessible_environment_before_network_call(
        self,
        send_request,
        get_object,
        environment_queryset,
    ):
        user = make_user(1)
        request = SimpleNamespace(user=user, data={'environment_id': 99})
        view = ApiRequestViewSet()
        view.get_object = MagicMock(return_value=SimpleNamespace())
        get_object.side_effect = Http404

        with self.assertRaises(Http404):
            view.execute(request, pk=1)

        environment_queryset.assert_called_once_with(user)
        get_object.assert_called_once_with(environment_queryset.return_value, id=99)
        send_request.assert_not_called()

    @patch('apps.api_testing.views.accessible_api_projects')
    def test_openapi_import_rejects_foreign_target_project(self, accessible_projects):
        project_queryset = accessible_projects.return_value.filter.return_value
        project_queryset.distinct.return_value.get.side_effect = ApiProject.DoesNotExist
        request = SimpleNamespace(
            user=make_user(1),
            data={'project_id': 20, 'endpoint_keys': ['GET /private']},
        )
        view = ApiDocumentViewSet()
        view.get_object = MagicMock(return_value=SimpleNamespace(status='parsed'))

        response = view.import_document(request, pk=1)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
