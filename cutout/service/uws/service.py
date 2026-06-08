import logging
from pathlib import Path
from typing import List, Optional

from celery import uuid
from django.db import transaction
from django.utils import timezone

from config import celery_app
from cutout.service.models import Job
from cutout.service.policy import ImageCutoutPolicy
from cutout.service.uws.exceptions import InvalidPhaseError, PermissionDeniedError
from cutout.service.uws.models import JobParameter, _convert_job
from cutout.users.models import User


class JobService:
    def __init__(self) -> None:
        # TODO: Setup Settings, Logging
        self._policy = ImageCutoutPolicy()

    def create(self, user: User, params: list[JobParameter], run_id: str | None = None) -> Job:
        """Create a pending job.

        This does not start execution of the job.  That must be done
        separately with `start`."""
        self._policy.validate_params(params)

        job = Job(
            owner=user,
            run_id=run_id,
            phase=Job.ExecutionPhase.PENDING,
        )
        job.save()
        for p in params:
            job.parameters.create(parameter=p.parameter_id, value=p.value, is_post=p.is_post)

        return job

    def list_for_user(self, user: User):
        return Job.objects.filter(owner=user).order_by("-creation_time")

    def get_for_user(self, user: User, job_id: int) -> Job:
        job = Job.objects.get(pk=job_id)
        if job.owner != user:
            raise PermissionDeniedError(f"Access to job {job_id} denied")
        return job

    def start(self, user: User, job_id: int):
        """Start execution of a job."""
        sqljob = self.get_for_user(user, job_id)
        if sqljob.phase not in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
            raise InvalidPhaseError("Cannot start job in phase {job.phase}")

        job = _convert_job(sqljob)
        message = self._policy.dispatch(job)

        # TODO: Marcar o job como QUEUED
        self.mark_queued(job_id, message.id)
        return message

    def start_async(self, user: User, job_id: int):
        """Start async execution using the fake worker pipeline."""
        logger = logging.getLogger("cutout")

        logger.info(f"[JobService.start_async] called with user={user} job_id={job_id}")
        sqljob = self.get_for_user(user, job_id)

        logger.info(f"[JobService.start_async] sqljob.phase={sqljob.phase}")
        if sqljob.phase not in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
            logger.error(f"[JobService.start_async] Invalid phase: {sqljob.phase}")
            raise InvalidPhaseError(f"Cannot start job in phase {sqljob.phase}")

        job = _convert_job(sqljob)
        message_id = uuid()
        logger.info(f"[JobService.start_async] mark_queued with message_id={message_id}")
        self.mark_queued(job_id, message_id)
        logger.info(
            f"[JobService.start_async] calling policy.dispatch_async with job_id={job.job_id} message_id={message_id}"
        )
        message = self._policy.dispatch_async(job, message_id=message_id)
        logger.info(f"[JobService.start_async] policy.dispatch_async returned: {message}")
        return message

    def mark_queued(self, job_id: int, message_id: str) -> None:
        """Mark a job as queued for processing."""
        job = Job.objects.get(pk=job_id)
        job.message_id = message_id

        if job.phase in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
            job.phase = Job.ExecutionPhase.QUEUED

        job.save()

    def mark_executing(self, job_id: int) -> None:
        job = Job.objects.get(pk=job_id)
        job.phase = Job.ExecutionPhase.EXECUTING
        job.start_time = timezone.now()
        job.save()

    def mark_completed(self, job_id: int) -> None:
        job = Job.objects.get(pk=job_id)
        job.phase = Job.ExecutionPhase.COMPLETED
        job.end_time = timezone.now()
        job.save()

    def mark_error(self, job_id: int) -> None:
        job = Job.objects.get(pk=job_id)
        job.phase = Job.ExecutionPhase.ERROR
        job.end_time = timezone.now()
        job.save()

    def mark_aborted(self, job_id: int) -> None:
        job = Job.objects.get(pk=job_id)
        job.phase = Job.ExecutionPhase.ABORTED
        job.end_time = timezone.now()
        job.save()

    def abort(self, user: User, job_id: int) -> Job:
        job = self.get_for_user(user, job_id)
        if job.phase in (Job.ExecutionPhase.COMPLETED, Job.ExecutionPhase.ERROR, Job.ExecutionPhase.ABORTED):
            return job

        if job.message_id:
            celery_app.control.revoke(job.message_id, terminate=False)

        self.mark_aborted(job_id)
        job.refresh_from_db()
        return job

    def delete(self, user: User, job_id: int) -> None:
        job = self.get_for_user(user, job_id)
        if job.phase not in (Job.ExecutionPhase.COMPLETED, Job.ExecutionPhase.ERROR, Job.ExecutionPhase.ABORTED):
            job = self.abort(user, job_id)

        result_paths = [result.file_path for result in job.results.all() if result.file_path]
        job.delete()

        for file_path in result_paths:
            path = Path(file_path)
            if path.exists():
                path.unlink()

    def get_parameters(self, user: User, job_id: int):
        job = self.get_for_user(user, job_id)
        return job.parameters.order_by("id")

    def get_results(self, user: User, job_id: int):
        job = self.get_for_user(user, job_id)
        return job.results.order_by("sequence")

    def get_result(self, user: User, job_id: int, result_id: str):
        job = self.get_for_user(user, job_id)
        return job.results.get(result_id=result_id)

    @transaction.atomic
    def register_results(self, job_id: int, results: list[dict]) -> None:
        job = Job.objects.select_for_update().get(pk=job_id)
        job.results.all().delete()

        for sequence, result in enumerate(results, start=1):
            job.results.create(
                result_id=result["result_id"],
                sequence=sequence,
                size=result.get("size") or 0,
                mime_type=result.get("mime_type"),
                url=result.get("url"),
                file_path=result.get("file_path"),
            )
