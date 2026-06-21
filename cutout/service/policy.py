"""UWS policy layer for image cutouts."""

from __future__ import annotations

# from dramatiq import Actor, Message
# from structlog.stdlib import BoundLogger
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List

from celery import chord as celery_chord

from cutout.service.cutout_parameters import CutoutParameters
from cutout.service.discovery import DesCsvFileLocator
from cutout.service.models import Task as SQLTask
from cutout.service.policies import DesPublicAccessPolicy
from cutout.service.tasks import finalize_job, image_cutout, run_cutout_for_pos
from cutout.service.uws.exceptions import MultiValuedParameterError, ParameterError, PermissionDeniedError
from cutout.service.uws.models import Job, JobParameter
from cutout.service.uws.policy import UWSPolicy

# from .actors import job_completed, job_failed
from .exceptions import InvalidCutoutParameterError

__all__ = ["ImageCutoutPolicy"]


class ImageCutoutPolicy(UWSPolicy):
    """Policy layer for dispatching and approving changes to UWS jobs.

    For now, rejects all changes to destruction and execution duration by
    returning their current values.

    Parameters
    ----------
    actor
         The actor to call for a job.  This simple mapping is temporary;
         eventually different types of cutouts will dispatch to different
         actors.
    logger
         Logger to use to report errors when dispatching the request.
    """

    # def __init__(self, actor: Actor, logger: BoundLogger) -> None:
    #     super().__init__()
    #     self._actor = actor
    #     self._logger = logger
    def __init__(self) -> None:
        self._survey_access_policy = DesPublicAccessPolicy()
        self._file_locator = DesCsvFileLocator()

    def _safe_token(self, value: str) -> str:
        """Normalize token for filesystem-safe filenames."""
        return re.sub(r"[^a-zA-Z0-9_.-]", "_", value)

    def _build_result_path(self, job: Job, task_params: dict) -> Path:
        output_format = str(task_params.get("format", "fits")).lower()
        extension = "png" if output_format == "png" else "fits"
        mode = "rgb" if task_params.get("color", False) else str(task_params.get("band", "mono"))

        survey_id = self._safe_token(str(task_params.get("id", "unknown")))
        engine = self._safe_token(str(task_params.get("engine", "engine")))
        mode_token = self._safe_token(mode)
        filename = f"job_{job.job_id}_{survey_id}_{engine}_{mode_token}.{extension}"

        return Path("/data/results").joinpath(filename)

    def _build_async_result_path(self, job: Job, task_params: dict, sequence: int) -> Path:
        base_path = self._build_result_path(job, task_params)
        filename = f"{base_path.stem}_{sequence}{base_path.suffix or '.fits'}"
        return Path("/data/results/async").joinpath(filename)

    def dispatch(self, job: Job):
        """Dispatch a cutout request to the backend.

        Parameters
        ----------
        job
            The submitted job description.

        Returns
        -------
        dramatiq.Message
            The dispatched message to the backend.

        Notes
        -----
        Currently, only one dataset ID and only one stencil are supported.
        This limitation is expected to be relaxed in a later version.
        """
        cutout_params = CutoutParameters.from_job_parameters(job.parameters)
        tasks_params = self.convert_to_list_of_task_params(cutout_params)

        # Celery tasks signature
        tasks = []

        for t in tasks_params:
            if not self._survey_access_policy.can_request_cutout(user_id=job.owner, survey_id=t["id"]):
                raise PermissionDeniedError(f"User has no access to survey {t['id']}")

            resultfile = self._build_result_path(job, t)
            # If color composition requested, collect files per RGB band
            if t.get("color"):
                # parse rgb_bands: accept 'gri', 'g,r,i' or 'g r i'
                raw = t.get("rgb_bands", "gri")
                if "," in raw:
                    bands = [b.strip() for b in raw.split(",") if b.strip()]
                elif " " in raw:
                    bands = [b.strip() for b in raw.split() if b.strip()]
                else:
                    bands = list(raw)

                files_map = {}
                for b in bands:
                    files_b = self._file_locator.find_files(survey_id=t["id"], stencil=t["stencil_obj"], band=b)
                    if not files_b:
                        raise ParameterError(f"No files found for band {b} in the requested region")
                    # keep only paths that exist on the current filesystem
                    candidate_paths = [str(f.file_path) for f in files_b if f.file_path]
                    existing = [p for p in candidate_paths if Path(p).exists()]
                    if not existing:
                        raise ParameterError(f"No available files on disk for band {b} in the requested region")
                    files_map[b] = existing

                # Debug logging: show files_map and existence
                print(f"[policy] dispatch: files_map for bands={bands}: {files_map}")
                for band_name, paths in files_map.items():
                    for p in paths:
                        print(f"[policy] file check: band={band_name} path={p} exists=True")

                tasks.append(
                    image_cutout.s(
                        job_id=job.job_id,
                        source_id=t["id"],
                        stencil=t["stencil"],
                        files=files_map,
                        engine=t["engine"],
                        band=t["band"],
                        format=t["format"],
                        path=str(resultfile),
                        color=t.get("color", False),
                        rgb_bands=t.get("rgb_bands"),
                        persist=t.get("persist", False),
                    )
                )
            else:
                files = self._file_locator.find_files(survey_id=t["id"], stencil=t["stencil_obj"], band=t["band"])
                if not files:
                    raise ParameterError("No files found for the requested region")
                candidate = [str(f.file_path) for f in files if f.file_path]
                existing = [p for p in candidate if Path(p).exists()]
                if not existing:
                    raise ParameterError("No available files on disk for the requested region")
                tasks.append(
                    image_cutout.s(
                        job_id=job.job_id,
                        source_id=t["id"],
                        stencil=t["stencil"],
                        files=existing,
                        engine=t["engine"],
                        band=t["band"],
                        format=t["format"],
                        path=str(resultfile),
                        color=False,
                        rgb_bands=t.get("rgb_bands"),
                        persist=t.get("persist", False),
                    )
                )

        if len(tasks) == 1:
            return tasks[0].apply_async()

        raise ParameterError("Only one cutout task is supported in sync mode")

    def create_tasks_for_job(self, job: Job, params: list[JobParameter]) -> list:
        """Create one Task row per cutout execution unit (stencil × band × format × engine)."""
        cutout_params = CutoutParameters.from_job_parameters(params)
        task_dicts = self.convert_to_list_of_task_params(cutout_params)
        tasks = []
        for sequence, t in enumerate(task_dicts, start=1):
            if not self._survey_access_policy.can_request_cutout(user_id=job.owner, survey_id=t["id"]):
                raise PermissionDeniedError(f"User has no access to survey {t['id']}")
            output_path = str(self._build_async_result_path(job, t, sequence))
            stencil_obj = t["stencil_obj"]
            stencil_dict = stencil_obj.to_dict()
            task = SQLTask.objects.create(
                job_id=int(job.job_id),
                sequence=sequence,
                survey_id=t["id"],
                stencil=stencil_dict,
                stencil_type=stencil_dict.get("type", "unknown"),
                band=t["band"],
                output_format=t["format"],
                engine=t["engine"],
                color=t.get("color", False),
                rgb_bands=t.get("rgb_bands", "gri"),
                persist=t.get("persist", False),
                output_path=output_path,
            )
            tasks.append(task)
        return tasks

    def dispatch_async(self, job: Job, message_id: str):
        logger = logging.getLogger("cutout")
        logger.info("[dispatch_async] job_id=%s message_id=%s", job.job_id, message_id)

        db_tasks = list(SQLTask.objects.filter(job_id=int(job.job_id)).order_by("sequence"))
        cutout_sigs = [
            run_cutout_for_pos.s(job_id=job.job_id, task_id=str(task.id))
            for task in db_tasks
        ]
        result = celery_chord(cutout_sigs)(
            finalize_job.s(job_id=job.job_id).set(task_id=message_id)
        )
        logger.info("[dispatch_async] chord dispatched: %d task(s), callback_id=%s", len(cutout_sigs), message_id)
        return result

    def validate_destruction(self, destruction: datetime, job: Job) -> datetime:
        return job.destruction_time

    def validate_execution_duration(self, execution_duration: int, job: Job) -> int:
        return job.execution_duration

    def validate_params(self, params: list[JobParameter]) -> None:
        try:
            cutout_params = CutoutParameters.from_job_parameters(params)
        except InvalidCutoutParameterError as e:
            raise ParameterError(str(e)) from e

        # For now, only support a single ID and stencil.
        if len(cutout_params.ids) != 1:
            raise MultiValuedParameterError("Only one ID supported")
        if len(cutout_params.stencils) != 1:
            raise MultiValuedParameterError("Only one stencil is supported")
        if len(cutout_params.engines) > 1:
            raise MultiValuedParameterError("Only one engine is supported")

    def convert_to_list_of_task_params(self, cutouts) -> list:
        params = []

        for id in cutouts.ids:
            for format in cutouts.formats:
                for band in cutouts.bands:
                    engines = cutouts.engines or ["astrocut"]
                    for engine in engines:
                        for stencil in cutouts.stencils:
                            params.append(
                                {
                                    "id": id,
                                    "stencil_obj": stencil,
                                    "stencil": stencil.to_dict(),
                                    "band": band,
                                    "format": format,
                                    "engine": engine,
                                    "color": (
                                        (cutouts.colors[0].lower() == "true")
                                        if getattr(cutouts, "colors", None)
                                        else False
                                    ),
                                    "rgb_bands": (
                                        cutouts.rgb_bands[0] if getattr(cutouts, "rgb_bands", None) else "gri"
                                    ),
                                    "persist": (
                                        (cutouts.persists[0].lower() == "true")
                                        if getattr(cutouts, "persists", None)
                                        else False
                                    ),
                                }
                            )
        return params
