from django.db import models

from .models import ApiProject, Environment


def can_access_api_project(user, project):
    """Return whether a user may access resources owned by an API project."""
    user_id = getattr(user, 'id', None)
    if not user_id or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False) or project.owner_id == user_id:
        return True
    return project.members.filter(id=user_id).exists()


def accessible_api_projects(user):
    queryset = ApiProject.objects.all()
    if getattr(user, 'is_superuser', False):
        return queryset
    return queryset.filter(
        models.Q(owner=user) | models.Q(members=user)
    ).distinct()


def accessible_environments(user):
    queryset = Environment.objects.all()
    if getattr(user, 'is_superuser', False):
        return queryset
    return queryset.filter(
        models.Q(scope='GLOBAL')
        | models.Q(scope='LOCAL', project__in=accessible_api_projects(user))
    ).distinct()
