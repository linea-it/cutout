import logging
from typing import Any

from django.utils import timezone

from config import celery_app
from cutout.service.cutout_runner import perform_cutout
from cutout.service.models import Job, Task


@celery_app.task(
    bind=True,
    autoretry_for=(Job.DoesNotExist, Task.DoesNotExist),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def perform_cutout_task(self, job_id: str, task_id: str) -> dict[str, Any]:
    """Celery wrapper for `perform_cutout`. All parameters are read from the Task row in DB."""
    logger = logging.getLogger("cutout")
    logger.info(
        "[perform_cutout_task] celery_task_id=%s retries=%s job_id=%r task_id=%r",
        self.request.id,
        self.request.retries,
        job_id,
        task_id,
    )
    return perform_cutout(job_id, task_id)


@celery_app.task
def finalize_job(_results: list[dict[str, Any]], job_id: str) -> None:
    """Chord callback: runs when all run_cutout_for_pos tasks for a job complete.

    JobResults and Task statuses are already set by each individual worker task.
    This callback only transitions the Job to COMPLETED.
    """
    logger = logging.getLogger("cutout")
    job_pk = int(str(job_id).strip())

    try:
        job = Job.objects.get(pk=job_pk)
    except Job.DoesNotExist:
        logger.error("[finalize_job] Job %r not found", job_id)
        return

    if job.phase in (Job.ExecutionPhase.ABORTED, Job.ExecutionPhase.ERROR):
        logger.info("[finalize_job] job_id=%r phase=%s — skipping COMPLETED transition", job_id, job.phase)
        return

    job.phase = Job.ExecutionPhase.COMPLETED
    job.end_time = timezone.now()
    job.save(update_fields=["phase", "end_time"])
    logger.info("[finalize_job] job_id=%r marked COMPLETED", job_id)


@celery_app.task(bind=True)
def job_completed(result, **kwargs) -> str:
    print(result)
    print(kwargs)
    return f"TESTE: {result}"


@celery_app.task()
def on_success(retval, task_id, args, kwargs) -> str:
    return f"ON SUCCESS {task_id}"


@celery_app.task()
def task_completed() -> str:
    return "Completed"


@celery_app.task()
def task_1(x, **kwargs):
    s = f"Task 1: {x}"
    print(s)
    return s


@celery_app.task()
def ping(x):
    return f"pong:{x}"
