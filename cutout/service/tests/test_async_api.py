from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from cutout.service.policy import ImageCutoutPolicy
from cutout.service.uws.models import JobParameter
from cutout.service.uws.service import JobService
from cutout.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _patch_async_result_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _fake_path(self, job, task_params, sequence):
        extension = "png" if str(task_params.get("format", "fits")).lower() == "png" else "fits"
        return tmp_path / f"job_{job.job_id}_{sequence}.{extension}"

    monkeypatch.setattr(ImageCutoutPolicy, "_build_async_result_path", _fake_path)


def test_async_create_runs_job_and_persists_result(user, settings, monkeypatch, tmp_path):
    _patch_async_result_path(monkeypatch, tmp_path)
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        reverse("api:async_cutout"),
        data={
            "id": "des_dr2",
            "pos": "CIRCLE 10 0 1",
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
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    client = APIClient()
    client.force_authenticate(user=user)

    service = JobService()
    job = service.create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
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
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )
    other_user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=other_user)

    response = client.get(reverse("api:async_job_detail", kwargs={"job_id": job.id}))

    assert response.status_code == 403


def test_async_phase_abort_marks_job_aborted(user):
    client = APIClient()
    client.force_authenticate(user=user)
    service = JobService()
    job = service.create(
        user=user,
        params=[
            JobParameter(parameter_id="id", value="des_dr2"),
            JobParameter(parameter_id="pos", value="CIRCLE 10 0 1"),
            JobParameter(parameter_id="band", value="g"),
            JobParameter(parameter_id="format", value="fits"),
        ],
    )

    response = client.post(reverse("api:async_job_phase", kwargs={"job_id": job.id}), data={"PHASE": "ABORT"})

    assert response.status_code == 303
    job.refresh_from_db()
    assert job.phase == "ABORTED"
