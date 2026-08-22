"""Job access and lifecycle for authenticated and anonymous (session-bound) callers."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import uuid
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from config import celery_app
from cutout.service.bands import assert_result_path
from cutout.service.models import Job
from cutout.service.policy import ImageCutoutPolicy
from cutout.service.uws.exceptions import InvalidPhaseError, PermissionDeniedError, ServiceUnavailableError
from cutout.service.uws.models import JobParameter, _convert_job
from cutout.users.models import User

logger = logging.getLogger("cutout")

_ACTIVE_PHASES = frozenset(
    {
        Job.ExecutionPhase.PENDING,
        Job.ExecutionPhase.QUEUED,
        Job.ExecutionPhase.EXECUTING,
        Job.ExecutionPhase.HELD,
        Job.ExecutionPhase.SUSPENDED,
        Job.ExecutionPhase.UNKNOWN,
    }
)


def _is_authenticated(user) -> bool:
    return user is not None and getattr(user, "is_authenticated", False)


def _job_max_age_days() -> int:
    return int(getattr(settings, "CUTOUT_JOB_MAX_AGE_DAYS", 7))


def _active_grace() -> timedelta:
    hours = int(getattr(settings, "CUTOUT_JOB_ACTIVE_GRACE_HOURS", 6))
    return timedelta(hours=hours)


class JobService:
    def __init__(self) -> None:
        self._policy = ImageCutoutPolicy()

    def create(
        self,
        user: User,
        params: list[JobParameter],
        run_id: str | None = None,
        execution_mode: str = "async",
        session_key: str | None = None,
    ) -> Job:
        """Create a pending job with its Task rows.

        Authenticated jobs are owned by ``user``. Anonymous jobs require a
        non-empty ``session_key`` and must never be treated as world-readable.
        """
        self._policy.validate_params(params)
        owner = user if _is_authenticated(user) else None
        if owner is None and not session_key:
            raise PermissionDeniedError("Anonymous cutouts require a browser session")

        # Survey ACL before any DB writes — raising inside atomic() after save()
        # leaves ATOMIC_REQUESTS broken and session middleware returns 500.
        self.ensure_survey_access(user=owner, params=params)

        destruction_time = timezone.now() + timedelta(days=_job_max_age_days())

        with transaction.atomic():
            job = Job(
                owner=owner,
                session_key=None if owner is not None else session_key,
                run_id=run_id,
                phase=Job.ExecutionPhase.PENDING,
                destruction_time=destruction_time,
            )
            job.save()
            for p in params:
                job.parameters.create(parameter=p.parameter_id, value=p.value, is_post=p.is_post)

            self._policy.create_tasks_for_job(_convert_job(job), params, execution_mode=execution_mode)

        return job

    def ensure_survey_access(self, user, params: list[JobParameter]) -> None:
        self._policy.ensure_survey_access(user=user, params=params)

    def _job_accessible(self, job: Job, user, session_key: str | None) -> bool:
        """Authorize job access. Never allow solely because owner is NULL."""
        if job.owner_id:
            return _is_authenticated(user) and job.owner_id == user.pk
        return bool(session_key) and job.session_key == session_key

    def list_for_user(self, user: User, session_key: str | None = None):
        if _is_authenticated(user):
            query = Q(owner=user)
            if session_key:
                query |= Q(owner__isnull=True, session_key=session_key)
            return Job.objects.filter(query).order_by("-creation_time")
        if not session_key:
            return Job.objects.none()
        return Job.objects.filter(owner__isnull=True, session_key=session_key).order_by("-creation_time")

    def get_for_user(self, user: User, job_id: int, session_key: str | None = None) -> Job:
        job = Job.objects.get(pk=job_id)
        if not self._job_accessible(job, user, session_key):
            raise PermissionDeniedError(f"Access to job {job_id} denied")
        return job

    def start_async(self, user: User, job_id: int, session_key: str | None = None):
        """Dispatch the job's tasks to the Celery workers."""
        logger.info("[JobService.start_async] called with user=%s job_id=%s", user, job_id)
        sqljob = self.get_for_user(user, job_id, session_key=session_key)

        logger.info("[JobService.start_async] sqljob.phase=%s", sqljob.phase)
        if sqljob.phase not in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
            logger.error("[JobService.start_async] Invalid phase: %s", sqljob.phase)
            raise InvalidPhaseError(f"Cannot start job in phase {sqljob.phase}")

        job = _convert_job(sqljob)
        message_id = uuid()

        logger.info("[JobService.start_async] mark_queued with message_id=%s", message_id)
        self.mark_queued(job_id, message_id)

        logger.info(
            "[JobService.start_async] calling policy.dispatch_async with job_id=%s message_id=%s",
            job.job_id,
            message_id,
        )
        message = self._policy.dispatch_async(job, message_id=message_id)
        logger.info("[JobService.start_async] policy.dispatch_async returned: %s", message)
        return message

    def mark_queued(self, job_id: int, message_id: str) -> None:
        job = Job.objects.get(pk=job_id)
        job.message_id = message_id
        if job.phase in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
            job.phase = Job.ExecutionPhase.QUEUED
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

    def abort(self, user: User, job_id: int, session_key: str | None = None) -> Job:
        job = self.get_for_user(user, job_id, session_key=session_key)
        if job.phase in (Job.ExecutionPhase.COMPLETED, Job.ExecutionPhase.ERROR, Job.ExecutionPhase.ABORTED):
            return job

        if job.message_id:
            celery_app.control.revoke(job.message_id, terminate=False)

        self.mark_aborted(job_id)
        job.refresh_from_db()
        return job

    def delete(self, user: User, job_id: int, session_key: str | None = None) -> None:
        job = self.get_for_user(user, job_id, session_key=session_key)
        if job.phase not in (Job.ExecutionPhase.COMPLETED, Job.ExecutionPhase.ERROR, Job.ExecutionPhase.ABORTED):
            job = self.abort(user, job_id, session_key=session_key)

        file_paths = self._collect_job_file_paths(job)
        if not self._unlink_result_paths(file_paths, context=f"delete job_id={job_id}"):
            raise ServiceUnavailableError("Job files could not be removed; deletion can be retried")
        job.delete()

    def get_parameters(self, user: User, job_id: int, session_key: str | None = None):
        job = self.get_for_user(user, job_id, session_key=session_key)
        return job.parameters.order_by("id")

    def get_results(self, user: User, job_id: int, session_key: str | None = None):
        job = self.get_for_user(user, job_id, session_key=session_key)
        return job.results.order_by("sequence")

    def get_result(self, user: User, job_id: int, result_id: str, session_key: str | None = None):
        job = self.get_for_user(user, job_id, session_key=session_key)
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

    @staticmethod
    def _collect_job_file_paths(job: Job) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        for result in job.results.all():
            if result.file_path and result.file_path not in seen:
                seen.add(result.file_path)
                paths.append(result.file_path)
        for task in job.tasks.all():
            if task.output_path and task.output_path not in seen:
                seen.add(task.output_path)
                paths.append(task.output_path)
        return paths

    @staticmethod
    def _unlink_result_paths(file_paths: list[str], *, context: str) -> bool:
        unlink_failed = False
        for file_path in file_paths:
            try:
                path = assert_result_path(file_path)
            except ValueError:
                logger.warning("[%s] refusing unlink outside results root: %s", context, file_path)
                continue
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                unlink_failed = True
                logger.warning("[%s] unlink failed for %s: %s", context, file_path, exc)
        return not unlink_failed

    def _abort_job_for_cleanup(self, job: Job) -> None:
        if job.phase not in _ACTIVE_PHASES:
            return
        if job.message_id:
            try:
                celery_app.control.revoke(job.message_id, terminate=False)
            except Exception as exc:  # noqa: BLE001 — cleanup must not abort the batch
                logger.warning("[cleanup_expired_jobs] revoke failed job_id=%s: %s", job.id, exc)
        now = timezone.now()
        # Push deletion past the active grace window so workers can wind down.
        job.phase = Job.ExecutionPhase.ABORTED
        job.end_time = now
        job.destruction_time = max(job.destruction_time or now, now) + _active_grace()
        job.save(update_fields=["phase", "end_time", "destruction_time"])

    def cleanup_expired_jobs(self) -> int:
        """Delete expired jobs (any owner) and unlink safe result/output files.

        Active jobs past ``destruction_time`` are revoked/aborted and have their
        ``destruction_time`` extended by ``CUTOUT_JOB_ACTIVE_GRACE_HOURS``.
        Terminal jobs are removed once ``destruction_time`` has passed.
        """
        now = timezone.now()
        expired = Job.objects.filter(destruction_time__isnull=False, destruction_time__lte=now).order_by(
            "destruction_time"
        )
        deleted = 0
        for job in expired.iterator():
            try:
                if job.phase in _ACTIVE_PHASES:
                    self._abort_job_for_cleanup(job)
                    logger.info(
                        "[cleanup_expired_jobs] aborted active job_id=%s; delete deferred to %s",
                        job.id,
                        job.destruction_time,
                    )
                    continue

                file_paths = self._collect_job_file_paths(job)
                job_id = job.id
                # Unlink before delete so a permanent OSError can be retried
                # while the DB row still references the paths.
                unlink_failed = False
                for file_path in file_paths:
                    try:
                        path = assert_result_path(file_path)
                    except ValueError:
                        logger.warning(
                            "[cleanup_expired_jobs] refusing unlink outside results: %s (job %s)",
                            file_path,
                            job_id,
                        )
                        continue
                    try:
                        if path.exists():
                            path.unlink()
                    except OSError as exc:
                        unlink_failed = True
                        logger.warning(
                            "[cleanup_expired_jobs] unlink failed job_id=%s path=%s: %s",
                            job_id,
                            file_path,
                            exc,
                        )
                if unlink_failed:
                    continue

                job.delete()
                deleted += 1
            except Exception as exc:  # noqa: BLE001 — one bad job must not stop the batch
                logger.exception("[cleanup_expired_jobs] failed job_id=%s: %s", getattr(job, "id", None), exc)
        return deleted
