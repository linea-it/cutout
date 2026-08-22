# Generated manually for cutout job retention / cleanup

from datetime import timedelta

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_destruction_time(apps, schema_editor):
    Job = apps.get_model("service", "Job")
    max_age_days = int(getattr(settings, "CUTOUT_JOB_MAX_AGE_DAYS", 7))
    for job in Job.objects.filter(destruction_time__isnull=True).iterator():
        base = job.creation_time or timezone.now()
        job.destruction_time = base + timedelta(days=max_age_days)
        job.save(update_fields=["destruction_time"])


def create_cleanup_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = IntervalSchedule.objects.get_or_create(every=1, period="hours")
    PeriodicTask.objects.update_or_create(
        name="cleanup-expired-cutout-jobs",
        defaults={
            "task": "cutout.service.tasks.cleanup_expired_jobs",
            "interval": schedule,
            "crontab": None,
            "solar": None,
            "clocked": None,
            "enabled": True,
            "one_off": False,
        },
    )


def remove_cleanup_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="cleanup-expired-cutout-jobs").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("service", "0006_job_session_key"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="job",
            index=models.Index(fields=["destruction_time"], name="by_destruction_time"),
        ),
        migrations.RunPython(backfill_destruction_time, migrations.RunPython.noop),
        migrations.RunPython(create_cleanup_periodic_task, remove_cleanup_periodic_task),
    ]
