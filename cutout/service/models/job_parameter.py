from django.db import models

from cutout.service.models import Job


class JobParameter(models.Model):
    """An input parameter to the job.
    https://www.ivoa.net/documents/UWS/20161024/REC-UWS-1.1-20161024.html
    """

    job = models.ForeignKey(Job, on_delete=models.CASCADE, verbose_name="Job", related_name="parameters")

    parameter = models.CharField(
        verbose_name="Parameter",
        help_text="Identifier of the parameter.",
        max_length=64,
    )

    value = models.TextField(verbose_name="Value", help_text="Value of the parameter.")

    is_post = models.BooleanField(
        verbose_name="Is Post", help_text="Whether the parameter was provided via POST.", default=False
    )

    class Meta:
        indexes = [
            models.Index(name="by_parameter", fields=["job", "parameter"]),
        ]
