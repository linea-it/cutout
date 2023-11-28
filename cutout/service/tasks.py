from pathlib import Path

from django.contrib.auth import get_user_model

from config import celery_app
from cutout.service.des_cutout import DesCutout

User = get_user_model()


@celery_app.task()
def des_cutout_circle(**kwargs) -> str:
    dc = DesCutout()
    result = dc.cutout_circle(**kwargs)
    return str(result)
