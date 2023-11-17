from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from cutout.service.api.views import JobRequestViewSet
from cutout.users.api.views import UserViewSet

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

router.register("users", UserViewSet)
router.register("job", JobRequestViewSet)


app_name = "api"
urlpatterns = router.urls
