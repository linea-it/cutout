import logging
from collections.abc import Iterable
from pathlib import Path
from typing import List, Optional

from celery.exceptions import TimeoutError as CeleryTimeoutError
from django.http import FileResponse, HttpResponse
from django.urls import reverse
from django.utils.encoding import escape_uri_path
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from cutout.service.models import Job
from cutout.service.uws.exceptions import ParameterError, ServiceUnavailableError
from cutout.service.uws.models import JobParameter
from cutout.service.uws.service import JobService
from cutout.users.models import User

from .serializers import (
    AsyncJobDetailSerializer,
    AsyncJobSummarySerializer,
    JobParameterSerializer,
    JobResultSerializer,
)


def _request_items(data) -> Iterable[tuple[str, list[str]]]:
    if hasattr(data, "lists"):
        return [(key, [str(value) for value in values]) for key, values in data.lists()]

    normalized = []
    for key, value in data.items():
        if isinstance(value, list):
            normalized.append((key, [str(item) for item in value]))
        else:
            normalized.append((key, [str(value)]))
    return normalized


def _extract_job_request(data, *, is_post: bool) -> tuple[list[JobParameter], str | None, str | None]:
    params: list[JobParameter] = []
    run_id: str | None = None
    requested_phase: str | None = None

    for key, values in _request_items(data):
        lower_key = key.lower()
        for value in values:
            if lower_key == "runid":
                run_id = value
            elif lower_key == "phase":
                requested_phase = value
            elif value != "":
                params.append(JobParameter(parameter_id=lower_key, value=value, is_post=is_post))

    return params, run_id, requested_phase


def _job_location(request, job: Job) -> str:
    path = reverse("api:async_job_detail", kwargs={"job_id": job.id})
    return request.build_absolute_uri(path)


class CutoutView(APIView):
    def get(self, request, format=None):
        return Response({"message": "Hello, world!"})


cutout_schema = extend_schema(
    parameters=[
        OpenApiParameter(
            name="id",
            description=("Identifiers of images from which to make a cutout. This parameter is mandatory."),
            type=str,
            default="des_dr2",
            many=False,
        ),
        OpenApiParameter(
            name="pos",
            type=str,
            allow_blank=True,
            many=False,
            default="CIRCLE 36.30911 -10.18749 2",
            description=(
                "Positions to cut out. Supported parameters are RANGE followed"
                " by min and max ra and min and max dec; CIRCLE followed by"
                " ra, dec, and radius; and POLYGON followed by a list of"
                " ra/dec positions for vertices. Arguments must be separated"
                " by spaces and parameters are double-precision floating point"
                " numbers expressed as strings."
            ),
        ),
        OpenApiParameter(
            name="runid",
            type=str,
            allow_blank=True,
            many=False,
            description=(
                "An opaque string that is returned in the job metadata and"
                " job listings. Maybe used by the client to associate jobs"
                " with specific larger operations."
            ),
        ),
        OpenApiParameter(
            name="phase",
            type=str,
            allow_blank=True,
            many=False,
            default="RUN",
            description=("For async requests, defaults to RUN and dispatches the job immediately."),
        ),
        OpenApiParameter(
            name="format",
            type=str,
            allow_blank=False,
            many=False,
            default="fits",
            description=("fits or png"),
        ),
        OpenApiParameter(
            name="color",
            type=bool,
            allow_blank=True,
            many=False,
            default=False,
            description=("When true and format=png, produce an RGB PNG composed from `rgb_bands`."),
        ),
        OpenApiParameter(
            name="rgb_bands",
            type=str,
            allow_blank=True,
            many=False,
            default="gri",
            description=("Three-letter band composition for RGB (e.g. 'gri' or 'g,r,i' or 'g r i')."),
        ),
        OpenApiParameter(
            name="persist",
            type=bool,
            allow_blank=True,
            many=False,
            default=False,
            description=("When true, persist the generated file in /data/results and return it."),
        ),
        OpenApiParameter(
            name="band",
            type=str,
            allow_blank=False,
            many=False,
            description=("One of grizY"),
        ),
        OpenApiParameter(
            name="engine",
            type=str,
            allow_blank=False,
            many=False,
            default="astrocut",
            description=("Cutout backend engine. Supported values: astrocut, legacy"),
        ),
    ],
)


@extend_schema_view(get=cutout_schema, post=cutout_schema)
class SyncCutoutView(APIView):
    sync_timeout_seconds = 25

    def _mimetype_for_format(self, output_format: str) -> str:
        if output_format.lower() == "png":
            return "image/x-png"
        return "application/fits"

    def sync_cutout(self, user: User, params: list[JobParameter], run_id: str | None):
        job_service = JobService()
        job = job_service.create(user=user, params=params, run_id=run_id)
        async_result = job_service.start(user, job_id=job.id)

        output_format = "fits"
        for p in params:
            if p.parameter_id == "format":
                output_format = p.value
                break

        try:
            job_service.mark_executing(job.id)
            result_path = async_result.get(timeout=self.sync_timeout_seconds)
        except CeleryTimeoutError as exc:
            job_service.mark_error(job.id)
            raise ServiceUnavailableError("Sync cutout timed out") from exc
        except Exception as exc:
            job_service.mark_error(job.id)
            raise ParameterError(str(exc)) from exc

        result_file = Path(result_path)
        if not result_file.exists():
            job_service.mark_error(job.id)
            raise ServiceUnavailableError("Result file unavailable")

        job_service.mark_completed(job.id)
        fp = open(result_file, "rb")
        response = FileResponse(fp, content_type=self._mimetype_for_format(output_format), as_attachment=True)
        response["Content-Length"] = result_file.stat().st_size
        response["Content-Disposition"] = f"attachment; filename={escape_uri_path(result_file.name)}"
        return response

    def get(self, request, format=None):
        params, run_id, _ = _extract_job_request(request.query_params, is_post=False)
        return self.sync_cutout(user=request.user, params=params, run_id=run_id)


@extend_schema_view(get=extend_schema(parameters=[]), post=cutout_schema)
class AsyncCutoutView(APIView):
    def get(self, request, format=None):
        jobs = JobService().list_for_user(request.user)
        serializer = AsyncJobSummarySerializer(jobs, many=True, context={"request": request})
        return Response({"jobs": serializer.data})

    def post(self, request, format=None):
        logger = logging.getLogger("cutout")
        logger.info(f"[AsyncCutoutView.post] called with data={request.data}")
        params, run_id, requested_phase = _extract_job_request(request.data or request.query_params, is_post=True)
        logger.info(f"[AsyncCutoutView.post] params={params} run_id={run_id} requested_phase={requested_phase}")
        if not params:
            logger.error("[AsyncCutoutView.post] No params provided")
            raise ParameterError("At least one cutout parameter is required")

        phase = (requested_phase or "RUN").upper()
        if phase != "RUN":
            logger.error(f"[AsyncCutoutView.post] Invalid phase: {phase}")
            raise ParameterError("Only PHASE=RUN is supported when creating async jobs")

        job_service = JobService()
        job = job_service.create(user=request.user, params=params, run_id=run_id)
        logger.info(f"[AsyncCutoutView.post] Created job id={job.id}")
        job_service.start_async(request.user, job.id)
        logger.info(f"[AsyncCutoutView.post] Dispatched start_async for job id={job.id}")

        job.refresh_from_db()

        serializer = AsyncJobDetailSerializer(job, context={"request": request})
        response = Response(serializer.data, status=status.HTTP_303_SEE_OTHER)
        response["Location"] = _job_location(request, job)
        logger.info(f"[AsyncCutoutView.post] Returning response for job id={job.id}")

        return response


class AsyncJobDetailView(APIView):
    def get(self, request, job_id: int, format=None):
        job = JobService().get_for_user(request.user, job_id)
        serializer = AsyncJobDetailSerializer(job, context={"request": request})
        return Response(serializer.data)

    def delete(self, request, job_id: int, format=None):
        JobService().delete(request.user, job_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AsyncJobPhaseView(APIView):
    def get(self, request, job_id: int, format=None):
        job = JobService().get_for_user(request.user, job_id)
        return HttpResponse(job.phase, content_type="text/plain")

    def post(self, request, job_id: int, format=None):
        phase = str(request.data.get("PHASE") or request.data.get("phase") or "").upper()
        job_service = JobService()

        if phase == "RUN":
            job = job_service.get_for_user(request.user, job_id)
            if job.phase not in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
                raise ParameterError(f"Cannot run job in phase {job.phase}")
            job_service.start_async(request.user, job_id)
        elif phase == "ABORT":
            job_service.abort(request.user, job_id)
        else:
            raise ParameterError("PHASE must be RUN or ABORT")

        job = job_service.get_for_user(request.user, job_id)
        response = HttpResponse(job.phase, content_type="text/plain", status=status.HTTP_303_SEE_OTHER)
        response["Location"] = _job_location(request, job)
        return response


class AsyncJobParametersView(APIView):
    def get(self, request, job_id: int, format=None):
        parameters = JobService().get_parameters(request.user, job_id)
        serializer = JobParameterSerializer(parameters, many=True)
        return Response({"parameters": serializer.data})


class AsyncJobResultsView(APIView):
    def get(self, request, job_id: int, format=None):
        results = JobService().get_results(request.user, job_id)
        serializer = JobResultSerializer(results, many=True, context={"request": request})
        return Response({"results": serializer.data})


class AsyncJobResultView(APIView):
    def get(self, request, job_id: int, result_id: str, format=None):
        result = JobService().get_result(request.user, job_id, result_id)
        if not result.file_path:
            raise ServiceUnavailableError("Result file unavailable")

        result_file = Path(result.file_path)
        if not result_file.exists():
            raise ServiceUnavailableError("Result file unavailable")

        fp = open(result_file, "rb")
        response = FileResponse(fp, content_type=result.mime_type or "application/octet-stream", as_attachment=True)
        response["Content-Length"] = result_file.stat().st_size
        response["Content-Disposition"] = f"attachment; filename={escape_uri_path(result_file.name)}"
        return response
