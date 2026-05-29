from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from cutout.service.api.views import (
    AsyncCutoutView,
    AsyncJobDetailView,
    AsyncJobParametersView,
    AsyncJobPhaseView,
    AsyncJobResultsView,
    AsyncJobResultView,
    CutoutView,
    SyncCutoutView,
)

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

# router.register("users", UserViewSet)
# router.register("job", JobRequestViewSet)


app_name = "api"
urlpatterns = router.urls

urlpatterns += [
    path("cutout", CutoutView.as_view(), name="cutout"),
    path("sync", SyncCutoutView.as_view(), name="sync_cutout"),
    path("async", AsyncCutoutView.as_view(), name="async_cutout"),
    path("async/<int:job_id>", AsyncJobDetailView.as_view(), name="async_job_detail"),
    path("async/<int:job_id>/phase", AsyncJobPhaseView.as_view(), name="async_job_phase"),
    path("async/<int:job_id>/parameters", AsyncJobParametersView.as_view(), name="async_job_parameters"),
    path("async/<int:job_id>/results", AsyncJobResultsView.as_view(), name="async_job_results"),
    path("async/<int:job_id>/results/<str:result_id>", AsyncJobResultView.as_view(), name="async_job_result"),
]
