"""Single entry point for executing one cutout unit (a Task row) end to end.

Reads every execution parameter from the database, discovers the input files,
runs the cutout engine and records the result and status transitions.  Used as
a direct call by the sync flow and wrapped in a Celery task for the async flow
(``cutout.service.tasks.perform_cutout_task``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.utils import timezone

from cutout.service.bands import assert_result_path, assert_safe_band, parse_rgb_band_list
from cutout.service.cutout_engine import create_cutout_engine
from cutout.service.discovery import DesCsvFileLocator
from cutout.service.models import Job, JobResult, Task
from cutout.service.policies import LineaSurveyAccessPolicy
from cutout.service.stencils import Stencil
from cutout.service.uws.exceptions import ParameterError, PermissionDeniedError

logger = logging.getLogger("cutout")

InputFiles = list[str] | dict[str, list[str]]


def _parse_rgb_bands(raw: str) -> list[str]:
    """Parse rgb_bands accepting 'gri', 'g,r,i' or 'g r i'."""
    return parse_rgb_band_list(raw)


def _validate_input_files(files: InputFiles | None) -> None:
    if not files:
        return

    paths: list[str] = []
    if isinstance(files, dict):
        for v in files.values():
            paths.extend(v or [])
    else:
        paths = list(files)

    missing = [f for f in paths if not Path(f).exists()]
    if missing:
        msg = "Input file unavailable: " + ", ".join(missing)
        raise FileNotFoundError(msg)


def _find_existing_files(locator: DesCsvFileLocator, task: Task, stencil: Stencil, band: str) -> list[str]:
    try:
        assert_safe_band(band)
    except ValueError as exc:
        raise ParameterError(str(exc)) from exc

    descriptors = locator.find_files(survey_id=task.survey_id, stencil=stencil, band=band)
    if not descriptors:
        raise ParameterError(f"No files found for band {band} in the requested region")

    candidates = [str(d.file_path) for d in descriptors if d.file_path]
    existing = [p for p in candidates if Path(p).exists()]
    if not existing:
        raise ParameterError(f"No available files on disk for band {band} in the requested region")
    return existing


def _discover_input_files(task: Task) -> InputFiles:
    """Locate the input tiles for a task, per band when color composition is requested."""
    stencil = Stencil.from_dict(task.stencil)
    locator = DesCsvFileLocator()

    if task.color:
        bands = _parse_rgb_bands(task.rgb_bands or "gri")
        files_map = {band: _find_existing_files(locator, task, stencil, band) for band in bands}
        logger.info("[perform_cutout] task_id=%s color bands=%s files=%s", task.id, bands, files_map)
        return files_map

    files = _find_existing_files(locator, task, stencil, task.band)
    logger.info("[perform_cutout] task_id=%s band=%s files=%s", task.id, task.band, files)
    return files


def _mime_type_for_format(output_format: str) -> str:
    return "image/png" if str(output_format).lower() == "png" else "application/fits"


def _assert_survey_access(job: Job, task: Task) -> None:
    """Re-check survey policy at execution time (defense in depth vs create-time only)."""
    if not LineaSurveyAccessPolicy().can_request_cutout(user=job.owner, survey_id=task.survey_id):
        raise PermissionDeniedError(f"User has no access to survey {task.survey_id}")


def perform_cutout(job_id: int | str, task_id: int | str) -> dict[str, Any]:
    """Execute one cutout Task end to end, reading everything from the database.

    Loads the Job and Task rows, transitions their states, discovers the input
    files, runs the cutout engine and registers the JobResult.  Marking the Job
    as COMPLETED is the caller's responsibility (chord callback in async mode).
    """
    job_pk = int(str(job_id).strip())
    task_pk = int(str(task_id).strip())

    job = Job.objects.get(pk=job_pk)
    task = Task.objects.get(pk=task_pk)

    if task.job_id != job.pk:
        raise ValueError(f"Task {task_pk} does not belong to job {job_pk}")

    if job.phase == Job.ExecutionPhase.ABORTED:
        logger.info("[perform_cutout] job_id=%s is ABORTED, skipping task_id=%s", job_pk, task_pk)
        return {}

    logger.info(
        "[perform_cutout] START job_id=%s task_id=%s survey_id=%s stencil_type=%s band=%s "
        "format=%s engine=%s color=%s rgb_bands=%s",
        job_pk,
        task_pk,
        task.survey_id,
        task.stencil_type,
        task.band,
        task.output_format,
        task.engine,
        task.color,
        task.rgb_bands,
    )

    # First task to run transitions the job to EXECUTING (idempotent under concurrency).
    # PENDING is accepted besides QUEUED so the function can run standalone, without dispatch.
    Job.objects.filter(pk=job_pk, phase__in=(Job.ExecutionPhase.PENDING, Job.ExecutionPhase.QUEUED)).update(
        phase=Job.ExecutionPhase.EXECUTING,
        start_time=timezone.now(),
    )

    Task.objects.filter(pk=task_pk, status=Task.Status.PENDING).update(
        status=Task.Status.EXECUTING,
        start_time=timezone.now(),
    )

    try:
        _assert_survey_access(job, task)

        files = _discover_input_files(task)
        _validate_input_files(files)

        try:
            output_path = assert_result_path(task.output_path)
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc

        engine = create_cutout_engine(task.engine)
        result_path = Path(
            engine.run_cutout(
                source_id=task.survey_id,
                stencil=task.stencil,
                input_files=files,
                band=task.band,
                output_format=task.output_format,
                output_path=str(output_path),
                color=task.color,
                rgb_bands=task.rgb_bands,
                persist=task.persist,
            )
        )

        try:
            result_path = assert_result_path(result_path)
        except ValueError as exc:
            raise ParameterError(str(exc)) from exc

        if not result_path.exists():
            raise FileNotFoundError(f"Engine did not produce result file {result_path}")

        result_id = result_path.stem
        size = result_path.stat().st_size

        JobResult.objects.update_or_create(
            job=job,
            sequence=task.sequence,
            defaults={
                "result_id": result_id,
                "size": size,
                "mime_type": _mime_type_for_format(task.output_format),
                "url": f"/api/async/{job_pk}/results/{result_id}",
                "file_path": str(result_path),
            },
        )

        Task.objects.filter(pk=task_pk).update(
            status=Task.Status.COMPLETED,
            end_time=timezone.now(),
        )

        logger.info(
            "[perform_cutout] COMPLETED job_id=%s task_id=%s result_id=%s size=%s path=%s",
            job_pk,
            task_pk,
            result_id,
            size,
            result_path,
        )
        return {
            "task_id": task_pk,
            "result_id": result_id,
            "file_path": str(result_path),
            "size": size,
        }

    except Exception as exc:
        logger.exception("[perform_cutout] ERROR job_id=%s task_id=%s: %s", job_pk, task_pk, exc)
        Task.objects.filter(pk=task_pk).update(
            status=Task.Status.ERROR,
            end_time=timezone.now(),
            error_message=str(exc),
        )
        Job.objects.filter(pk=job_pk).update(
            phase=Job.ExecutionPhase.ERROR,
            end_time=timezone.now(),
        )
        raise
