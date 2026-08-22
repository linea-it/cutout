"""UWS policy layer for image cutouts."""

from __future__ import annotations

# from dramatiq import Actor, Message
# from structlog.stdlib import BoundLogger
import logging
import re
from datetime import datetime
from pathlib import Path

from celery import chord as celery_chord

from cutout.service.cutout_parameters import CutoutParameters
from cutout.service.models import Task as SQLTask
from cutout.service.policies import LineaSurveyAccessPolicy
from cutout.service.tasks import finalize_job, perform_cutout_task
from cutout.service.uws.exceptions import MultiValuedParameterError, ParameterError, PermissionDeniedError
from cutout.service.uws.models import Job, JobParameter
from cutout.service.uws.policy import UWSPolicy
from cutout.users.models import User

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
        self._survey_access_policy = LineaSurveyAccessPolicy()

    def _job_owner(self, job: Job) -> User | None:
        if job.owner in (None, ""):
            return None
        return User.objects.filter(pk=job.owner).first()

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

    def _build_task_result_path(self, job: Job, task_params: dict, sequence: int, execution_mode: str) -> Path:
        base_path = self._build_result_path(job, task_params)
        filename = f"{base_path.stem}_{sequence}{base_path.suffix or '.fits'}"
        return Path("/data/results").joinpath(execution_mode, filename)

    def ensure_survey_access(self, user: User | None, params: list[JobParameter]) -> None:
        """Raise PermissionDeniedError if any task survey is not allowed for user.

        Must run before opening a DB transaction that writes Job/Task rows.
        """
        cutout_params = CutoutParameters.from_job_parameters(params)
        for t in self.convert_to_list_of_task_params(cutout_params):
            if not self._survey_access_policy.can_request_cutout(user=user, survey_id=t["id"]):
                raise PermissionDeniedError(f"User has no access to survey {t['id']}")

    def create_tasks_for_job(self, job: Job, params: list[JobParameter], execution_mode: str = "async") -> list:
        """Create one Task row per cutout execution unit (stencil × band × format × engine)."""
        cutout_params = CutoutParameters.from_job_parameters(params)
        task_dicts = self.convert_to_list_of_task_params(cutout_params)
        tasks = []
        for sequence, t in enumerate(task_dicts, start=1):
            if not self._survey_access_policy.can_request_cutout(user=self._job_owner(job), survey_id=t["id"]):
                raise PermissionDeniedError(f"User has no access to survey {t['id']}")
            output_path = str(self._build_task_result_path(job, t, sequence, execution_mode))
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
        cutout_sigs = [perform_cutout_task.s(job_id=job.job_id, task_id=str(task.id)) for task in db_tasks]
        result = celery_chord(cutout_sigs)(finalize_job.s(job_id=job.job_id).set(task_id=message_id))
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
