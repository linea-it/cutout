from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from cutout.service import cutout_runner
from cutout.service.discovery import FileDescriptor
from cutout.service.policy import ImageCutoutPolicy
from cutout.service.uws.models import JobParameter
from cutout.service.uws.service import JobService
from cutout.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _patch_async_result_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _fake_path(self, job, task_params, sequence, execution_mode):
        extension = "png" if str(task_params.get("format", "fits")).lower() == "png" else "fits"
        return tmp_path / execution_mode / f"job_{job.job_id}_{sequence}.{extension}"

    monkeypatch.setattr(ImageCutoutPolicy, "_build_task_result_path", _fake_path)


class _FakeLocator:
    def __init__(self, input_file: Path):
        self._input_file = input_file

    def find_files(self, *, survey_id, stencil, band=None):
        return [
            FileDescriptor(
                tile_id="DES0002+0001",
                archive_path="Y6A1/r4907/DES0002+0001/p01/coadd",
                file_path=self._input_file,
                band=band,
            )
        ]


class _FakeEngine:
    def run_cutout(self, **kwargs):
        output_path = Path(kwargs["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake fits data")
        return output_path


def _patch_cutout_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Replace file discovery and the cutout engine so perform_cutout runs without real tiles."""
    input_file = tmp_path / "DES0002+0001_r4907p01_g.fits.fz"
    input_file.write_bytes(b"tile data")
    monkeypatch.setattr(cutout_runner, "DesCsvFileLocator", lambda: _FakeLocator(input_file))
    monkeypatch.setattr(cutout_runner, "create_cutout_engine", lambda name: _FakeEngine())


def test_async_create_runs_job_and_persists_result(user, settings, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        reverse("api:async_cutout"),
        data={
            "id": "des_dr2",
            "pos": "CIRCLE 10 0 0.083333",
            "band": "g",
            "format": "fits",
        },
    )

    assert response.status_code == 303
    assert "Location" in response

    job_id = response.json()["job_id"]
    detail_response = client.get(reverse("api:async_job_detail", kwargs={"job_id": job_id}))
    assert detail_response.status_code == 200
    assert detail_response.json()["phase"] == "COMPLETED"
    assert len(detail_response.json()["results"]) == 1

    result_id = detail_response.json()["results"][0]["result_id"]

    results_response = client.get(reverse("api:async_job_results", kwargs={"job_id": job_id}))
    assert results_response.status_code == 200

    download_response = client.get(reverse("api:async_job_result", kwargs={"job_id": job_id, "result_id": result_id}))
    assert download_response.status_code == 200
    assert download_response["Content-Disposition"].startswith("attachment;")


def test_async_phase_run_starts_pending_job(user, settings, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    client = APIClient()
    client.force_authenticate(user=user)

    service = JobService()
    job = service.create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 0.083333"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )

    response = client.post(reverse("api:async_job_phase", kwargs={"job_id": job.id}), data={"PHASE": "RUN"})

    assert response.status_code == 303
    job.refresh_from_db()
    assert job.phase == "COMPLETED"
    assert job.results.count() == 1


def test_async_job_detail_enforces_owner(user):
    job = JobService().create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 0.083333"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )
    other_user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=other_user)

    response = client.get(reverse("api:async_job_detail", kwargs={"job_id": job.id}))

    assert response.status_code == 403


def test_async_rejects_radius_above_30_arcmin(user, monkeypatch, tmp_path):
    """Async endpoint also rejects radii >= 30 arcmin."""
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        reverse("api:async_cutout"),
        data={
            "id": "des_dr2",
            "pos": "CIRCLE 0.5 2.15 0.5",
            "band": "r",
            "format": "fits",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "exceeds the maximum allowed" in detail
    assert "30 arcmin" in detail


def test_async_phase_abort_marks_job_aborted(user):
    client = APIClient()
    client.force_authenticate(user=user)
    service = JobService()
    job = service.create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 0.083333"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )

    response = client.post(reverse("api:async_job_phase", kwargs={"job_id": job.id}), data={"PHASE": "ABORT"})

    assert response.status_code == 303
    job.refresh_from_db()
    assert job.phase == "ABORTED"
