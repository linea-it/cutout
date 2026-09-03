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
    monkeypatch.setattr("cutout.service.bands.get_results_root", lambda: tmp_path)


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
    monkeypatch.setattr(cutout_runner, "get_file_locator", lambda survey_id: _FakeLocator(input_file))
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


def test_async_create_allows_anonymous_des_dr2(settings, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    client = APIClient()

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
    from cutout.service.models import Job

    job = Job.objects.get(pk=response.json()["job_id"])
    assert job.owner is None
    assert job.session_key
    assert job.destruction_time is not None

    detail_response = client.get(reverse("api:async_job_detail", kwargs={"job_id": job.id}))
    assert detail_response.status_code == 200
    assert detail_response.json()["phase"] == "COMPLETED"


def test_async_anonymous_job_not_world_readable(settings, monkeypatch, tmp_path):
    """owner=NULL must not imply public access — wrong session gets 403."""
    _patch_async_result_path(monkeypatch, tmp_path)
    _patch_cutout_execution(monkeypatch, tmp_path)
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

    owner_client = APIClient()
    create = owner_client.post(
        reverse("api:async_cutout"),
        data={
            "id": "des_dr2",
            "pos": "CIRCLE 10 0 0.083333",
            "band": "g",
            "format": "fits",
        },
    )
    assert create.status_code == 303
    job_id = create.json()["job_id"]

    other_client = APIClient()
    # Different browser session ⇒ different _cutout_job_session token.
    other_client.get(reverse("api:async_cutout"))
    denied = other_client.get(reverse("api:async_job_detail", kwargs={"job_id": job_id}))
    assert denied.status_code == 403

    allowed = owner_client.get(reverse("api:async_job_detail", kwargs={"job_id": job_id}))
    assert allowed.status_code == 200


def test_cleanup_expired_jobs(settings, monkeypatch, tmp_path, user):
    from datetime import timedelta
    from unittest.mock import patch

    from django.utils import timezone

    from cutout.service.models import Job

    _patch_async_result_path(monkeypatch, tmp_path)
    settings.CUTOUT_JOB_MAX_AGE_DAYS = 7
    settings.CUTOUT_JOB_ACTIVE_GRACE_HOURS = 6

    service = JobService()

    # Authenticated terminal job with result + orphan task output_path
    owned = service.create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 0.083333"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )
    assert owned.destruction_time is not None
    result_file = tmp_path / "async" / "owned.fits"
    orphan_file = tmp_path / "async" / "orphan_task.fits"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_bytes(b"owned result")
    orphan_file.write_bytes(b"orphan task output")
    owned.results.create(
        result_id="r1",
        sequence=1,
        size=result_file.stat().st_size,
        mime_type="application/fits",
        file_path=str(result_file),
    )
    task = owned.tasks.get()
    task.output_path = str(orphan_file)
    task.save(update_fields=["output_path"])
    owned.phase = Job.ExecutionPhase.COMPLETED
    owned.destruction_time = timezone.now() - timedelta(minutes=1)
    owned.save(update_fields=["phase", "destruction_time"])

    # Anonymous job still within retention — must survive
    fresh = service.create(
        user=None,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 0.083333"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
        session_key="session-abc",
    )

    # Active expired job: aborted and deferred, not deleted yet
    active = service.create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 11 0 0.083333"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )
    active.phase = Job.ExecutionPhase.QUEUED
    active.message_id = "celery-msg-1"
    active.destruction_time = timezone.now() - timedelta(minutes=1)
    active.save(update_fields=["phase", "message_id", "destruction_time"])

    with patch("cutout.service.uws.service.celery_app.control.revoke") as revoke:
        deleted = service.cleanup_expired_jobs()

    assert deleted == 1
    assert not Job.objects.filter(pk=owned.id).exists()
    assert not result_file.exists()
    assert not orphan_file.exists()
    assert Job.objects.filter(pk=fresh.id).exists()

    active.refresh_from_db()
    assert active.phase == Job.ExecutionPhase.ABORTED
    assert active.destruction_time > timezone.now()
    revoke.assert_called_once_with("celery-msg-1", terminate=False)

    # After grace expires, active (now aborted) job is removed
    active.destruction_time = timezone.now() - timedelta(minutes=1)
    active.save(update_fields=["destruction_time"])
    assert service.cleanup_expired_jobs() == 1
    assert not Job.objects.filter(pk=active.id).exists()


def test_cleanup_expired_jobs_continues_after_unlink_error(settings, monkeypatch, tmp_path, user):
    from datetime import timedelta
    from pathlib import Path
    from unittest.mock import patch

    from django.utils import timezone

    from cutout.service.models import Job

    _patch_async_result_path(monkeypatch, tmp_path)
    settings.CUTOUT_JOB_MAX_AGE_DAYS = 7

    service = JobService()
    blocked = service.create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 0.083333"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )
    blocked_file = tmp_path / "async" / "blocked.fits"
    blocked_file.parent.mkdir(parents=True, exist_ok=True)
    blocked_file.write_bytes(b"blocked")
    blocked.results.create(
        result_id="b1",
        sequence=1,
        size=1,
        mime_type="application/fits",
        file_path=str(blocked_file),
    )
    blocked.phase = Job.ExecutionPhase.COMPLETED
    blocked.destruction_time = timezone.now() - timedelta(minutes=1)
    blocked.save(update_fields=["phase", "destruction_time"])

    ok = service.create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 12 0 0.083333"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )
    ok_file = tmp_path / "async" / "ok.fits"
    ok_file.write_bytes(b"ok")
    ok.results.create(
        result_id="o1",
        sequence=1,
        size=1,
        mime_type="application/fits",
        file_path=str(ok_file),
    )
    ok.phase = Job.ExecutionPhase.COMPLETED
    ok.destruction_time = timezone.now() - timedelta(minutes=1)
    ok.save(update_fields=["phase", "destruction_time"])

    real_unlink = Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.name == "blocked.fits":
            raise PermissionError("denied")
        return real_unlink(self, *args, **kwargs)

    with patch.object(Path, "unlink", flaky_unlink):
        deleted = service.cleanup_expired_jobs()

    assert deleted == 1
    assert Job.objects.filter(pk=blocked.id).exists()
    assert not Job.objects.filter(pk=ok.id).exists()
    assert not ok_file.exists()


def test_async_rejects_anonymous_private_survey():
    client = APIClient()
    response = client.post(
        reverse("api:async_cutout"),
        data={
            "id": "lsst_dp1",
            "pos": "CIRCLE 10 0 0.083333",
            "band": "g",
            "format": "fits",
        },
    )
    assert response.status_code == 403


def test_async_download_rejects_file_path_outside_results_root(user, monkeypatch, tmp_path):
    """Poisoned JobResult.file_path must not be served even if the owner can see the job."""
    _patch_async_result_path(monkeypatch, tmp_path)

    outside = tmp_path.parent / "secret_tile.fits"
    outside.write_bytes(b"private survey bytes")

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
    job.results.create(
        result_id="poisoned",
        sequence=1,
        size=outside.stat().st_size,
        mime_type="application/fits",
        file_path=str(outside),
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(
        reverse("api:async_job_result", kwargs={"job_id": job.id, "result_id": "poisoned"}),
    )

    assert response.status_code == 503
    assert b"private survey bytes" not in response.content


def test_job_delete_refuses_unlink_outside_results_root(user, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)

    outside = tmp_path.parent / "do_not_delete.fits"
    outside.write_bytes(b"keep me")

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
    job.phase = "COMPLETED"
    job.save(update_fields=["phase"])
    job.results.create(
        result_id="poisoned",
        sequence=1,
        size=outside.stat().st_size,
        mime_type="application/fits",
        file_path=str(outside),
    )

    service.delete(user, job.id)

    assert outside.exists()
    assert outside.read_bytes() == b"keep me"


def test_job_delete_retains_job_when_unlink_fails(user, monkeypatch, tmp_path):
    from pathlib import Path
    from unittest.mock import patch

    from cutout.service.models import Job
    from cutout.service.uws.exceptions import ServiceUnavailableError

    _patch_async_result_path(monkeypatch, tmp_path)
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
    result_file = tmp_path / "async" / "blocked-delete.fits"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_bytes(b"blocked")
    job.results.create(
        result_id="blocked",
        sequence=1,
        size=result_file.stat().st_size,
        mime_type="application/fits",
        file_path=str(result_file),
    )
    job.phase = Job.ExecutionPhase.COMPLETED
    job.save(update_fields=["phase"])

    with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
        with pytest.raises(ServiceUnavailableError):
            service.delete(user, job.id)

    assert Job.objects.filter(pk=job.id).exists()
    assert result_file.exists()
