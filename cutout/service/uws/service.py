from datetime import datetime
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model

from cutout.service.cutout_parameters import CutoutParameters
from cutout.service.models import Job
from cutout.service.policy import ImageCutoutPolicy
from cutout.service.uws.exceptions import InvalidPhaseError, PermissionDeniedError
from cutout.service.uws.models import JobParameter, _convert_job
from cutout.service.uws.policy import UWSPolicy

User = get_user_model()


class JobService:
    def __init__(self) -> None:
        # TODO: Setup Settings, Logging
        self._policy = ImageCutoutPolicy()

    def create(self, user: User, params: List[JobParameter], run_id: Optional[str] = None) -> Job:
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

    def start(self, user: User, job_id: int):
        """Start execution of a job."""
        sqljob = Job.objects.get(pk=job_id)
        if sqljob.owner != user:
            raise PermissionDeniedError(f"Access to job {job_id} denied")
        if sqljob.phase not in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
            raise InvalidPhaseError("Cannot start job in phase {job.phase}")

        job = _convert_job(sqljob)
        message = self._policy.dispatch(job)

        # TODO: Marcar o job como QUEUED
        self.mark_queued(job_id, message.id)

    def mark_queued(self, job_id: int, message_id: str) -> None:
        """Mark a job as queued for processing."""
        job = Job.objects.get(pk=job_id)
        job.message_id = message_id

        if job.phase in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
            job.phase = Job.ExecutionPhase.QUEUED

        job.save()
