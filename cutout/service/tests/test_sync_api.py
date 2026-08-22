from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from cutout.service import cutout_runner
from cutout.service.discovery import FileDescriptor
from cutout.service.models import Job, Task
from cutout.service.policy import ImageCutoutPolicy

pytestmark = pytest.mark.django_db

FAKE_PAYLOAD = b"fake fits data"


def _patch_async_result_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _fake_path(self, job, task_params, sequence, execution_mode):
        extension = "png" if str(task_params.get("format", "fits")).lower() == "png" else "fits"
        return tmp_path / execution_mode / f"job_{job.job_id}_{sequence}.{extension}"

    monkeypatch.setattr(ImageCutoutPolicy, "_build_task_result_path", _fake_path)
    monkeypatch.setattr("cutout.service.bands.get_results_root", lambda: tmp_path)


class _FakeLocator:
    def __init__(self, input_file: Path | None):
        self._input_file = input_file

    def find_files(self, *, survey_id, stencil, band=None):
        if self._input_file is None:
            return []
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
        output_path.write_bytes(FAKE_PAYLOAD)
        return output_path


def _patch_cutout_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, with_files: bool = True) -> None:
    input_file = None
    if with_files:
        input_file = tmp_path / "DES0002+0001_r4907p01_g.fits.fz"
        input_file.write_bytes(b"tile data")
    monkeypatch.setattr(cutout_runner, "DesCsvFileLocator", lambda: _FakeLocator(input_file))
    monkeypatch.setattr(cutout_runner, "create_cutout_engine", lambda name: _FakeEngine())


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_sync_get_runs_cutout_and_returns_file(user, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = _client(user).get(
        reverse("api:sync_cutout"),
        {"id": "des_dr2", "pos": "CIRCLE 10 0 0.016667", "band": "g", "format": "fits"},
    )

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["Content-Type"] == "application/fits"
    assert int(response["Content-Length"]) == len(FAKE_PAYLOAD)

    job = Job.objects.get()
    assert job.phase == Job.ExecutionPhase.COMPLETED
    assert job.start_time is not None
    assert job.end_time is not None

    task = job.tasks.get()
    assert task.status == Task.Status.COMPLETED
    assert task.start_time is not None
    assert task.end_time is not None

    job_result = job.results.get()
    assert job_result.size == len(FAKE_PAYLOAD)
    assert job_result.mime_type == "application/fits"
    assert Path(job_result.file_path).exists()
    assert "/sync/" in job_result.file_path


# transaction=True: on error responses DRF's exception handler calls set_rollback, which would
# poison the test's wrapping atomic block (production uses non_atomic_requests on this route).
@pytest.mark.django_db(transaction=True)
def test_sync_get_no_files_marks_error_and_returns_422(user, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path, with_files=False)

    response = _client(user).get(
        reverse("api:sync_cutout"),
        {"id": "des_dr2", "pos": "CIRCLE 10 0 0.016667", "band": "g", "format": "fits"},
    )

    assert response.status_code == 422
    assert "No files found" in response.json()["detail"]

    job = Job.objects.get()
    assert job.phase == Job.ExecutionPhase.ERROR
    assert job.end_time is not None

    task = job.tasks.get()
    assert task.status == Task.Status.ERROR
    assert "No files found" in task.error_message
    assert job.results.count() == 0


@pytest.mark.django_db(transaction=True)
def test_sync_get_rejects_multiple_tasks(user, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = _client(user).get(
        reverse("api:sync_cutout"),
        {"id": "des_dr2", "pos": "CIRCLE 10 0 1", "band": ["g", "r"], "format": "fits"},
    )

    assert response.status_code == 422
    assert "Only one cutout task" in response.json()["detail"]

    job = Job.objects.get()
    assert job.phase == Job.ExecutionPhase.ERROR
    assert job.tasks.count() == 2
    assert all(task.status == Task.Status.PENDING for task in job.tasks.all())


@pytest.mark.django_db(transaction=True)
def test_sync_get_rejects_large_radius(user, monkeypatch, tmp_path):
    """Radii > 10 arcmin must use async — sync returns 422 with guidance."""
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = _client(user).get(
        reverse("api:sync_cutout"),
        {"id": "des_dr2", "pos": "CIRCLE 0.5 2.15 0.25", "band": "r", "format": "fits"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "exceeds the synchronous limit" in detail
    assert "POST /api/async" in detail
    assert "10 arcmin" in detail

    job = Job.objects.get()
    assert job.phase == Job.ExecutionPhase.ERROR
    task = job.tasks.get()
    assert task.status == Task.Status.ERROR
    assert "exceeds the synchronous limit" in task.error_message


@pytest.mark.django_db(transaction=True)
def test_sync_get_allows_exact_10_arcmin(user, monkeypatch, tmp_path):
    """Radii exactly at the 10 arcmin sync limit are accepted."""
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = _client(user).get(
        reverse("api:sync_cutout"),
        {"id": "des_dr2", "pos": "CIRCLE 0.5 2.15 0.16666666666666666", "band": "r", "format": "fits"},
    )

    assert response.status_code == 200
    job = Job.objects.get()
    assert job.phase == Job.ExecutionPhase.COMPLETED


@pytest.mark.django_db(transaction=True)
def test_sync_get_allows_small_radius(user, monkeypatch, tmp_path):
    """Radii below 10 arcmin proceed normally."""
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = _client(user).get(
        reverse("api:sync_cutout"),
        {"id": "des_dr2", "pos": "CIRCLE 0.5 2.15 0.083333", "band": "r", "format": "fits"},
    )

    assert response.status_code == 200
    job = Job.objects.get()
    assert job.phase == Job.ExecutionPhase.COMPLETED


@pytest.mark.django_db(transaction=True)
def test_sync_rejects_radius_above_30_arcmin(user, monkeypatch, tmp_path):
    """Radii >= 30 arcmin are rejected regardless of mode."""
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = _client(user).get(
        reverse("api:sync_cutout"),
        {"id": "des_dr2", "pos": "CIRCLE 0.5 2.15 0.5", "band": "r", "format": "fits"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "exceeds the maximum allowed" in detail
    assert "30 arcmin" in detail


@pytest.mark.django_db(transaction=True)
def test_sync_get_rejects_private_survey_without_group(user, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = _client(user).get(
        reverse("api:sync_cutout"),
        {"id": "lsst_dp1", "pos": "CIRCLE 10 0 0.016667", "band": "g", "format": "fits"},
    )

    assert response.status_code == 403
    assert Job.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_sync_get_allows_anonymous_des_dr2(monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = APIClient().get(
        reverse("api:sync_cutout"),
        {"id": "des_dr2", "pos": "CIRCLE 10 0 0.016667", "band": "g", "format": "fits"},
    )

    assert response.status_code == 200
    job = Job.objects.get()
    assert job.owner is None
    assert job.phase == Job.ExecutionPhase.COMPLETED


@pytest.mark.django_db(transaction=True)
def test_sync_get_rejects_anonymous_private_survey(monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)

    response = APIClient().get(
        reverse("api:sync_cutout"),
        {"id": "lsst_dp1", "pos": "CIRCLE 10 0 0.016667", "band": "g", "format": "fits"},
    )

    assert response.status_code == 403
    assert Job.objects.count() == 0
