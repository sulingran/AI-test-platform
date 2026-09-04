from django.db.models import Avg, Count, Sum, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import AiCallRecord
from .serializers import AiCallRecordSerializer


class AiCallRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only AI usage records and aggregate statistics for administrators."""

    queryset = AiCallRecord.objects.all()
    serializer_class = AiCallRecordSerializer
    permission_classes = (IsAdminUser,)
    filterset_fields = ("provider", "role", "scenario", "status", "config_id")
    ordering_fields = ("created_at", "latency_ms", "total_tokens", "cost_estimate")
    ordering = ("-created_at",)

    @action(detail=False, methods=("get",))
    def stats(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        aggregate = queryset.aggregate(
            total=Count("id"),
            failed=Count("id", filter=Q(status="failed")),
            avg_latency=Avg("latency_ms"),
            total_tokens=Sum("total_tokens"),
            total_cost=Sum("cost_estimate"),
        )
        total = aggregate["total"] or 0
        failed = aggregate["failed"] or 0
        try:
            today_count = queryset.filter(created_at__date=timezone.localdate()).count()
        except Exception:
            today_count = 0
        return Response({
            "total": total,
            "success": total - failed,
            "failed": failed,
            "success_rate": round((total - failed) / total, 4) if total else 1.0,
            "avg_latency_ms": round(float(aggregate["avg_latency"]), 1) if aggregate["avg_latency"] is not None else None,
            "total_tokens": aggregate["total_tokens"] or 0,
            "total_cost": str(aggregate["total_cost"]) if aggregate["total_cost"] is not None else "0.000000",
            "today_count": today_count,
        })
