"""Policy layer for changes to UWS jobs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .models import Job, JobParameter

__all__ = ["UWSPolicy"]


class UWSPolicy(ABC):
    """Abstract interface for the application-provided policy layer.

    This class encapsulates functions to make policy decisions about UWS
    actions specific to a particular service.  Examples include dispatching
    work to a backend worker, validating parameters when the user attempts to
    change them after job creation, or deciding whether to accept a new
    execution duration or destruction time.

    Applications that use UWS should create an implementation of this abstract
    base class and then pass it into
    `~vocutouts.uws.dependencies.UWSDepencency` ``initialize`` method.
    """

    @abstractmethod
    def create_tasks_for_job(self, job: Job, params: list[JobParameter], execution_mode: str = "async") -> list:
        """Create the Task rows for a job, one per cutout execution unit.

        Parameters
        ----------
        job
            The job the tasks belong to.
        params
            The job parameters.
        execution_mode
            "sync" or "async"; selects the results directory for the
            generated files.

        Returns
        -------
        list
            The created Task rows.
        """

    @abstractmethod
    def dispatch_async(self, job: Job, message_id: str):
        """Dispatch the job's tasks to the backend workers.

        Parameters
        ----------
        job
            The job to start.
        message_id
            Identifier used to track the dispatched work.

        Returns
        -------
        celery.result.AsyncResult
            The result handle of the dispatched workflow.
        """

    @abstractmethod
    def validate_destruction(self, destruction: datetime, job: Job) -> datetime:
        """Validate a new destruction time for a job.

        Parameters
        ----------
        destruction
           New date at which the job outputs and its metadata will be
           deleted to recover resources.
        job
            The existing job.

        Returns
        -------
        datetime.datetime
            The new destruction time for the job, which should be
            ``job.destruction_time`` if the policy layer doesn't want to allow
            any change.
        """

    @abstractmethod
    def validate_execution_duration(self, execution_duration: int, job: Job) -> int:
        """Validate a new execution duration for a job.

        Parameters
        ----------
        execution_duration
            New desired maximum execution time for the job in wall clock
            seconds.
        job
            The existing job.

        Returns
        -------
        int
            The new execution duration for the job, which should be
            ``job.execution_duration`` if the policy layer doesn't want to
            allow any change.
        """

    @abstractmethod
    def validate_params(self, params: list[JobParameter]) -> None:
        """Validate parameters for a job.

        Parameters
        ----------
        params
            The new parameters.

        Raises
        ------
        vocutouts.uws.exceptions.ParameterError
            If one of the new parameters was invalid.
        """
