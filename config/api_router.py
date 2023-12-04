from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from rest_framework.routers import DefaultRouter, SimpleRouter

from cutout.service.api.views import CutoutView, JobRequestViewSet, SyncCutoutView
from cutout.users.api.views import UserViewSet

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

# router.register("users", UserViewSet)
# router.register("job", JobRequestViewSet)


app_name = "api"
urlpatterns = router.urls

urlpatterns += [
    # path("teste", hello_world, name="hello_world"),
    path("cutout", CutoutView.as_view(), name="cutout"),
    path("sync", SyncCutoutView.as_view(), name="sync_cutout"),
]
