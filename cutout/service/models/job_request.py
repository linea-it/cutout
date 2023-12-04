from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class JobStatus(models.IntegerChoices):
    IDLE = 1, "Idle"
    RUNNING = 2, "Running"
    COMPLETED = 3, "Completed"
    ABORTING = 7, "Aborting"
    ABORTED = 8, "Aborted"
    FAILED = 9, "Failed"


class JobRequest(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Owner", related_name="job_request")

    status = models.IntegerField(
        verbose_name="Status",
        default=JobStatus.IDLE,
        choices=JobStatus.choices,
    )

    # created = models.DateTimeField(auto_now_add=True)
    # updated = models.DateTimeField(auto_now=True)
