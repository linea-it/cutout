"""UWS policy layer for image cutouts."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from celery import chord, group
from numpy import source

from cutout.service.cutout_parameters import CutoutParameters
from cutout.service.stencils import RangeStencil
from cutout.service.tasks import image_cutout, job_completed, on_success
from cutout.service.uws.exceptions import MultiValuedParameterError, ParameterError
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
        print(tasks_params)

        # Celery tasks signature
        headers = []

        for t in tasks_params:
            filename = "teste.fits"
            resultfile = Path("/data/results").joinpath(filename)
            headers.append(
                image_cutout.s(
                    job_id=job.job_id,
                    source_id=t["id"],
                    stencil=t["stencil"],
                    band=t["band"],
                    format=t["format"],
                    path=str(resultfile),
                )
            )

        callback = job_completed.s()
        # job_group = group(headers)
        # gresult = job_group.apply_async()

        # c = chord(group(headers), on_success.s())
        # res = c.apply_async()
        # print(res)
        # job_group.link(job_completed.s(args=))

        res = chord(headers[0])(callback)
        return res

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

        # For now, range stencils are not supported.
        stencil = cutout_params.stencils[0]
        if isinstance(stencil, RangeStencil):
            raise ParameterError("RANGE stencils are not supported")

    def convert_to_list_of_task_params(self, cutouts) -> List:
        params = []

        for id in cutouts.ids:
            for format in cutouts.formats:
                for band in cutouts.bands:
                    for stencil in cutouts.stencils:
                        params.append(
                            {
                                "id": id,
                                "stencil": stencil.to_dict(),
                                "band": band,
                                "format": format,
                            }
                        )
        return params
