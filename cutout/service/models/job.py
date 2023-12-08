from tabnanny import verbose

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class Job(models.Model):
    """Implementacao da especificação IVOA UWS
    https://www.ivoa.net/documents/UWS/20161024/REC-UWS-1.1-20161024.html
    """

    class ExecutionPhase(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        QUEUED = "QUEUED", _("Queued")
        EXECUTING = "EXECUTING", _("Executing")
        COMPLETED = "COMPLETED", _("Completed")
        ERROR = "ERROR", _("Error")
        ABORTED = "ABORTED", _("Aborted")
        UNKNOWN = "UNKNOWN", _("Unknown")
        HELD = "HELD", _("Held")
        SUSPENDED = "SUSPENDED", _("Suspended")
        ARCHIVED = "ARCHIVED", _("Archived")

    message_id = models.CharField(
        verbose_name="Message ID",
        help_text="Internal message identifier for the work queuing system.",
        null=True,
        blank=True,
        default=None,
        max_length=36,
    )
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Owner", related_name="jobs")

    phase = models.CharField(
        verbose_name="Execution Phase",
        default=ExecutionPhase.PENDING,
        choices=ExecutionPhase.choices,
        help_text="Execution phase of the job.",
    )

    run_id = models.CharField(
        verbose_name="Run ID",
        help_text="Optional opaque string provided by the client.",
        null=True,
        blank=True,
        default=None,
        max_length=255,
    )

    creation_time = models.DateTimeField(
        verbose_name="Creation Time", help_text="When the job was created.", null=False, auto_now_add=True
    )

    start_time = models.DateTimeField(
        verbose_name="Start Time",
        help_text="When the job started executing (if it has started).",
        null=True,
        blank=True,
        default=None,
    )

    end_time = models.DateTimeField(
        verbose_name="End Time",
        help_text="When the job stopped executing (if it has stopped).",
        null=True,
        blank=True,
        default=None,
    )

    destruction_time = models.DateTimeField(
        verbose_name="Destruction Time",
        help_text="Time at which the job should be destroyed.",
        null=True,
        blank=True,
        default=None,
    )

    execution_duration = models.DurationField(
        verbose_name="Execution Duration",
        help_text="Allowed maximum execution duration in seconds.",
        null=True,
        blank=True,
        default=None,
    )

    quote = models.DateTimeField(
        verbose_name="Destruction Time",
        help_text="Expected completion time of the job if it were started now.",
        null=True,
        blank=True,
        default=None,
    )

    class Meta:
        indexes = [
            models.Index(name="by_owner_phase", fields=["owner", "phase", "creation_time"]),
            models.Index(name="by_owner_time", fields=["owner", "creation_time"]),
        ]
