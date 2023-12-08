from enum import unique
from tabnanny import verbose

from django.db import models

from cutout.service.models import Job


class JobResult(models.Model):
    """A single result from the job.
    https://www.ivoa.net/documents/UWS/20161024/REC-UWS-1.1-20161024.html
    """

    job = models.ForeignKey(Job, on_delete=models.CASCADE, verbose_name="Job", related_name="results")

    result_id = models.CharField(
        verbose_name="Identifier",
        help_text="Identifier for the result.",
        max_length=64,
    )

    sequence = models.PositiveIntegerField(verbose_name="Sequence", null=False, blank=False)

    size = models.PositiveIntegerField(
        verbose_name="Size", help_text="Size of the result in bytes.", null=True, blank=True, default=0
    )

    mime_type = models.CharField(
        verbose_name="Mime Type",
        help_text="MIME type of the result.",
        null=True,
        blank=True,
        default=None,
        max_length=64,
    )

    class Meta:
        indexes = [
            models.Index(name="by_sequence", fields=["job", "sequence"]),
            models.Index(name="by_result_id", fields=["job", "result_id"]),
        ]

        unique_together = [["job", "sequence"], ["job", "result_id"]]
