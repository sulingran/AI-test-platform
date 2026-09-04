"""Lazy model configuration resolver compatible with the existing model."""

from typing import Optional, Sequence


class ConfigResolver:
    EMBEDDING_ROLE_PRIORITY = ("tokenizer", "embedding", "writer")

    @staticmethod
    def active(role: str, model_type: Optional[str] = None, user=None, scope: str = "global"):
        from apps.requirement_analysis.models import AIModelConfig

        queryset = AIModelConfig.objects.filter(role=role, is_active=True)
        if model_type:
            queryset = queryset.filter(model_type=model_type)

        # Newer model variants may have scope; this project does not, so keep
        # user filtering based on the existing created_by relation.
        field_names = {field.name for field in AIModelConfig._meta.get_fields()}
        if scope and scope != "global" and user is not None:
            if "scope" in field_names:
                queryset = queryset.filter(scope=scope, created_by=user)
            else:
                queryset = queryset.filter(created_by=user)
        order_fields = ["-updated_at"] if "updated_at" in field_names else ["-pk"]
        return queryset.order_by(*order_fields).first()

    @staticmethod
    def active_by_priority(roles: Sequence[str], user=None):
        for role in roles or ():
            config = ConfigResolver.active(role, user=user)
            if config:
                return config
        return None
