from rest_framework.routers import DefaultRouter

from .views import AiCallRecordViewSet


router = DefaultRouter()
router.register(r"call-records", AiCallRecordViewSet, basename="ai-call-record")

urlpatterns = router.urls
