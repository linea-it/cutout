"""UWS policy layer for image cutouts."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from cutout.service.cutout_parameters import CutoutParameters
from cutout.service.discovery import DesCsvFileLocator
from cutout.service.policies import DesPublicAccessPolicy
from cutout.service.tasks import image_cutout
from cutout.service.uws.exceptions import MultiValuedParameterError, ParameterError, PermissionDeniedError
from cutout.service.uws.models import Job, JobParameter
from cutout.service.uws.policy import UWSPolicy

# from .actors import job_completed, job_failed
from .exceptions import InvalidCutoutParameterError

# from dramatiq import Actor, Message
# from structlog.stdlib import BoundLogger


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

            filename = "teste.fits"
            resultfile = Path("/data/results").joinpath(filename)
            files = self._file_locator.find_files(survey_id=t["id"], stencil=t["stencil_obj"], band=t["band"])
            if not files:
                raise ParameterError("No files found for the requested region")
            tasks.append(
                image_cutout.s(
                    job_id=job.job_id,
                    source_id=t["id"],
                    stencil=t["stencil"],
                    files=[str(f.file_path) for f in files if f.file_path],
                    engine=t["engine"],
                    band=t["band"],
                    format=t["format"],
                    path=str(resultfile),
                )
            )

        if len(tasks) == 1:
            return tasks[0].apply_async()

        raise ParameterError("Only one cutout task is supported in sync mode")

        # return self._actor.send_with_options(
        #     args=(
        #         job.job_id,
        #         cutout_params.ids,
        #         [s.to_dict() for s in cutout_params.stencils],
        #     ),
        #     time_limit=job.execution_duration * 1000,
        #     on_success=job_completed,
        #     on_failure=job_failed,
        # )

        # https://github.com/celery/celery/issues/1813
        # Task ID before execute
        # >>> from celery import uuid
        # >>> task_id = uuid()
        # >>> task_id
        # 'c7f388e9-d688-4f1d-be22-fb043b93c725'
        # >>> add.apply_async((2, 2), task_id=task_id)
        # <AsyncResult: c7f388e9-d688-4f1d-be22-fb043b93c725>

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

    def convert_to_list_of_task_params(self, cutouts) -> List:
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
                                    "color": (cutouts.colors[0].lower() == "true") if getattr(cutouts, 'colors', None) else False,
                                    "rgb_bands": cutouts.rgb_bands[0] if getattr(cutouts, 'rgb_bands', None) else "gri",
                                    "persist": (cutouts.persists[0].lower() == "true") if getattr(cutouts, 'persists', None) else False,
                                }
                            )
        return params
