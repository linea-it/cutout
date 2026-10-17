import os

from celery import Celery
from celery.signals import worker_process_init

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("cutout")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@worker_process_init.connect
def preload_discovery_indexes(**kwargs):
    from cutout.service.discovery.registry import preload_file_indexes

    preload_file_indexes()
