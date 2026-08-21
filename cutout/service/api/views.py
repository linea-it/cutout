import logging
import secrets
from collections.abc import Iterable
from pathlib import Path

from django.http import FileResponse, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import escape_uri_path
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from cutout.service.bands import assert_result_path
from cutout.service.cutout_runner import perform_cutout
from cutout.service.models import Job
from cutout.service.models.task import Task
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

# Cutouts with radius > 10 arcmin must use the async endpoint.
# Sync processing would take 60s+ and hit gateway/proxy timeouts.
_SYNC_RADIUS_LIMIT_DEG = 10 / 60  # 10 arcmin in degrees
_SYNC_RADIUS_MESSAGE = (
    "Cutout radius {radius:.1f} arcmin exceeds the synchronous limit "
    "of 10 arcmin. Please use POST /api/async instead. "
    "Expected processing time is {estimated}s."
)

# Absolute maximum cutout radius for any endpoint (sync or async).
_MAX_RADIUS_LIMIT_DEG = 0.5  # 30 arcmin in degrees
_MAX_RADIUS_MESSAGE = "Cutout radius {radius:.1f} arcmin exceeds the maximum allowed " "of 30 arcmin."


def _extract_radius_deg(params: list[JobParameter]) -> float | None:
    """Extract the effective radius in degrees from the 'pos' parameter.

    CIRCLE -> radius directly.
    RANGE  -> half the max of RA and Dec spans.
    POLYGON -> None (not yet supported).
    """
    pos_param = next((p.value for p in params if p.parameter_id == "pos"), None)
    if not pos_param:
        return None

    parts = pos_param.strip().split()
    if len(parts) < 1:
        return None

    stencil_type = parts[0].upper()

    if stencil_type == "CIRCLE" and len(parts) >= 4:
        return float(parts[3])

    if stencil_type == "RANGE" and len(parts) >= 5:
        ra_span = abs(float(parts[3]) - float(parts[1])) / 2
        dec_span = abs(float(parts[4]) - float(parts[2])) / 2
        return max(ra_span, dec_span)

    return None


def _check_max_radius(radius_deg: float) -> None:
    """Raise ParameterError if the radius exceeds the absolute maximum."""
    if radius_deg >= _MAX_RADIUS_LIMIT_DEG:
        raise ParameterError(_MAX_RADIUS_MESSAGE.format(radius=radius_deg * 60))


def _access_context(request) -> tuple:
    """Return (user, session_key) for job auth.

    Authenticated callers authorize via owner FK. Anonymous callers must match
    the opaque token stored in the Django session (``_cutout_job_session``).
    Never treat owner=NULL as world-readable.

    The token is written into session *data* only (no mid-request
    ``session.save()``), so ATOMIC_REQUESTS rollbacks do not orphan the cookie.
    """
    token_key = "_cutout_job_session"
    if token_key not in request.session:
        request.session[token_key] = secrets.token_hex(16)
    return request.user, request.session[token_key]


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
            description=("Cutout backend engine. Supported values: astrocut"),
        ),
    ],
)


@extend_schema_view(get=cutout_schema, post=cutout_schema)
class SyncCutoutView(APIView):
    permission_classes = [AllowAny]

    def _mimetype_for_format(self, output_format: str) -> str:
        if output_format.lower() == "png":
            return "image/x-png"
        return "application/fits"

    def _check_sync_radius(self, params: list[JobParameter], task) -> None:
        """Raise ParameterError if the cutout radius exceeds the sync threshold."""
        radius_deg = _extract_radius_deg(params)
        if radius_deg is None:
            return

        radius_arcmin = radius_deg * 60
        # Compare in arcmin at 0.1' precision so 0.166667° (≈10') is accepted.
        if round(radius_arcmin, 1) > 10:
            # Rough estimate: FITS ~radius², PNG ~3x
            is_png = task.output_format == "png"
            is_color = any(p.parameter_id == "color" and str(p.value).lower() == "true" for p in params)
            base_seconds = (radius_deg / _SYNC_RADIUS_LIMIT_DEG) ** 2 * 25
            estimated = int(base_seconds * (3 if (is_png and is_color) else 1))
            raise ParameterError(_SYNC_RADIUS_MESSAGE.format(radius=radius_arcmin, estimated=estimated))

    def sync_cutout(
        self,
        user: User,
        params: list[JobParameter],
        run_id: str | None,
        session_key: str | None = None,
    ):
        """Run a cutout synchronously inside the request.

        Database flow is identical to the async pipeline (Job + Task rows,
        status transitions and JobResult recorded by `perform_cutout`), but
        execution happens inline and the result file is returned directly.
        """
        logger = logging.getLogger("cutout")
        job_service = JobService()

        job = job_service.create(
            user=user,
            params=params,
            run_id=run_id,
            execution_mode="sync",
            session_key=session_key,
        )
        logger.info("[SyncCutoutView] created job_id=%s", job.id)

        tasks = list(job.tasks.order_by("sequence"))
        if len(tasks) != 1:
            job_service.mark_error(job.id)
            raise ParameterError("Only one cutout task is supported in sync mode")
        task = tasks[0]

        radius_deg = _extract_radius_deg(params)
        if radius_deg is not None:
            _check_max_radius(radius_deg)

        try:
            self._check_sync_radius(params, task)
        except ParameterError as exc:
            Task.objects.filter(pk=task.id).update(
                status=Task.Status.ERROR,
                end_time=timezone.now(),
                error_message=str(exc),
            )
            job_service.mark_error(job.id)
            raise exc

        try:
            result = perform_cutout(job.id, task.id)
        except APIException:
            # Task and Job are already marked ERROR by perform_cutout
            raise
        except Exception as exc:
            raise ParameterError(str(exc)) from exc

        result_file = Path(result["file_path"])
        try:
            result_file = assert_result_path(result_file)
        except ValueError as exc:
            job_service.mark_error(job.id)
            raise ServiceUnavailableError("Result file unavailable") from exc
        if not result_file.exists():
            job_service.mark_error(job.id)
            raise ServiceUnavailableError("Result file unavailable")

        job_service.mark_completed(job.id)
        logger.info("[SyncCutoutView] job_id=%s completed result_id=%s", job.id, result["result_id"])

        fp = open(result_file, "rb")
        response = FileResponse(fp, content_type=self._mimetype_for_format(task.output_format), as_attachment=True)
        response["Content-Length"] = result_file.stat().st_size
        response["Content-Disposition"] = f"attachment; filename={escape_uri_path(result_file.name)}"
        return response

    def get(self, request, format=None):
        params, run_id, _ = _extract_job_request(request.query_params, is_post=False)
        job_service = JobService()
        owner = request.user if getattr(request.user, "is_authenticated", False) else None
        job_service.ensure_survey_access(user=owner, params=params)
        user, session_key = _access_context(request)
        return self.sync_cutout(user=user, params=params, run_id=run_id, session_key=session_key)

    def post(self, request, format=None):
        params, run_id, _ = _extract_job_request(request.data or request.query_params, is_post=True)
        job_service = JobService()
        owner = request.user if getattr(request.user, "is_authenticated", False) else None
        job_service.ensure_survey_access(user=owner, params=params)
        user, session_key = _access_context(request)
        return self.sync_cutout(user=user, params=params, run_id=run_id, session_key=session_key)


@extend_schema_view(get=extend_schema(parameters=[]), post=cutout_schema)
class AsyncCutoutView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, format=None):
        user, session_key = _access_context(request)
        jobs = JobService().list_for_user(user, session_key=session_key)
        serializer = AsyncJobSummarySerializer(
            jobs,
            many=True,
            context={"request": request},
        )
        return Response({"jobs": serializer.data})

    def post(self, request, format=None):
        logger = logging.getLogger("cutout")
        logger.info(f"[AsyncCutoutView.post] called with data={request.data}")

        params, run_id, requested_phase = _extract_job_request(
            request.data or request.query_params,
            is_post=True,
        )
        logger.info(f"[AsyncCutoutView.post] params={params} run_id={run_id} " f"requested_phase={requested_phase}")
        if not params:
            logger.error("[AsyncCutoutView.post] No params provided")
            raise ParameterError("At least one cutout parameter is required")

        radius_deg = _extract_radius_deg(params)
        if radius_deg is not None:
            _check_max_radius(radius_deg)

        phase = (requested_phase or "RUN").upper()
        if phase != "RUN":
            logger.error(f"[AsyncCutoutView.post] Invalid phase: {phase}")
            raise ParameterError("Only PHASE=RUN is supported when creating async jobs")

        # ACL before touching the session — avoids 500 when session middleware
        # tries to persist a token after a denied request under ATOMIC_REQUESTS.
        job_service = JobService()
        owner = request.user if getattr(request.user, "is_authenticated", False) else None
        job_service.ensure_survey_access(user=owner, params=params)

        user, session_key = _access_context(request)
        job = job_service.create(
            user=user,
            params=params,
            run_id=run_id,
            session_key=session_key,
        )
        logger.info(f"[AsyncCutoutView.post] Created job id={job.id}")

        job_service.start_async(user, job.id, session_key=session_key)
        logger.info(f"[AsyncCutoutView.post] Dispatched start_async for job id={job.id}")

        job.refresh_from_db()

        serializer = AsyncJobDetailSerializer(job, context={"request": request})
        response = Response(serializer.data, status=status.HTTP_303_SEE_OTHER)
        response["Location"] = _job_location(request, job)
        logger.info(f"[AsyncCutoutView.post] Returning response for job id={job.id}")

        return response


class AsyncJobDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, job_id: int, format=None):
        user, session_key = _access_context(request)
        job = JobService().get_for_user(user, job_id, session_key=session_key)
        serializer = AsyncJobDetailSerializer(job, context={"request": request})
        return Response(serializer.data)

    def delete(self, request, job_id: int, format=None):
        user, session_key = _access_context(request)
        JobService().delete(user, job_id, session_key=session_key)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AsyncJobPhaseView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, job_id: int, format=None):
        user, session_key = _access_context(request)
        job = JobService().get_for_user(user, job_id, session_key=session_key)
        return HttpResponse(job.phase, content_type="text/plain")

    def post(self, request, job_id: int, format=None):
        phase = str(request.data.get("PHASE") or request.data.get("phase") or "").upper()
        job_service = JobService()
        user, session_key = _access_context(request)

        if phase == "RUN":
            job = job_service.get_for_user(user, job_id, session_key=session_key)
            if job.phase not in (Job.ExecutionPhase.PENDING, Job.ExecutionPhase.HELD):
                raise ParameterError(f"Cannot run job in phase {job.phase}")
            job_service.start_async(user, job_id, session_key=session_key)
        elif phase == "ABORT":
            job_service.abort(user, job_id, session_key=session_key)
        else:
            raise ParameterError("PHASE must be RUN or ABORT")

        job = job_service.get_for_user(user, job_id, session_key=session_key)
        response = HttpResponse(job.phase, content_type="text/plain", status=status.HTTP_303_SEE_OTHER)
        response["Location"] = _job_location(request, job)
        return response


class AsyncJobParametersView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, job_id: int, format=None):
        user, session_key = _access_context(request)
        parameters = JobService().get_parameters(user, job_id, session_key=session_key)
        serializer = JobParameterSerializer(parameters, many=True)
        return Response({"parameters": serializer.data})


class AsyncJobResultsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, job_id: int, format=None):
        user, session_key = _access_context(request)
        results = JobService().get_results(user, job_id, session_key=session_key)
        serializer = JobResultSerializer(results, many=True, context={"request": request})
        return Response({"results": serializer.data})


class AsyncJobResultView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, job_id: int, result_id: str, format=None):
        user, session_key = _access_context(request)
        result = JobService().get_result(user, job_id, result_id, session_key=session_key)
        if not result.file_path:
            raise ServiceUnavailableError("Result file unavailable")

        try:
            result_file = assert_result_path(result.file_path)
        except ValueError as exc:
            raise ServiceUnavailableError("Result file unavailable") from exc

        if not result_file.exists():
            raise ServiceUnavailableError("Result file unavailable")

        fp = open(result_file, "rb")
        response = FileResponse(fp, content_type=result.mime_type or "application/octet-stream", as_attachment=True)
        response["Content-Length"] = result_file.stat().st_size
        response["Content-Disposition"] = f"attachment; filename={escape_uri_path(result_file.name)}"
        return response
