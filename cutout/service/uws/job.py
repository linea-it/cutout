from datetime import datetime
from typing import Any

from cutout.service.models import Job


def uws_job_completed(
    job_id: str,
    results: list[dict[str, Any]],
) -> None:
    """Mark a UWS job as successfully complete.

    Parameters
    ----------
    job_id
        The identifier of the job that was started.
    result
        The results of the job.  This must be a list of dict representations
        of `~vocutouts.uws.models.JobResult` objects.
    """
    job = Job.objects.get(pk=job_id)
    job.phase = Job.ExecutionPhase.COMPLETED
    job.end_time = datetime.utcnow()
    job.save()

    return results
    # TODO: Log


# def uws_job_failed(
#     job_id: str,
#     exception: dict[str, str],
#     session: scoped_session,
#     logger: BoundLogger,
# ) -> None:
#     """Mark a UWS job as failed.

#     Parameters
#     ----------
#     job_id
#         The identifier of the job that was started.
#     exception
#         Exception information as passed to a Dramatiq ``on_failure`` callback.
#     session
#         A synchronous session to the UWS database.
#     logger
#         Logger for any messages.
#     """
#     storage = WorkerJobStore(session)
#     error = TaskError.from_callback(exception).to_job_error()
#     try:
#         storage.mark_errored(job_id, error)
#         logger.info(
#             "Marked job as failed",
#             job_id=job_id,
#             error_type=error.error_type.value,
#             error_code=error.error_code.value,
#             message=error.message,
#             detail=error.detail,
#         )
#     except UnknownJobError:
#         pass
