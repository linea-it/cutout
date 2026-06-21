from django.db import models

from cutout.service.models.job import Job


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        EXECUTING = "EXECUTING"
        COMPLETED = "COMPLETED"
        ERROR = "ERROR"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="tasks")
    sequence = models.PositiveSmallIntegerField()

    survey_id = models.CharField(max_length=64)
    stencil = models.JSONField()
    stencil_type = models.CharField(max_length=16)
    band = models.CharField(max_length=8)
    output_format = models.CharField(max_length=16)
    engine = models.CharField(max_length=32)
    color = models.BooleanField(default=False)
    rgb_bands = models.CharField(max_length=16, default="gri")
    persist = models.BooleanField(default=False)
    output_path = models.TextField()

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    start_time = models.DateTimeField(null=True, blank=True, default=None)
    end_time = models.DateTimeField(null=True, blank=True, default=None)
    error_message = models.TextField(null=True, blank=True, default=None)

    class Meta:
        unique_together = [["job", "sequence"]]
        indexes = [
            models.Index(name="task_by_job", fields=["job", "sequence"]),
            models.Index(name="task_by_job_status", fields=["job", "status"]),
        ]
