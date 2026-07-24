from pathlib import Path

import pytest

from cutout.service import cutout_runner
from cutout.service.cutout_runner import perform_cutout
from cutout.service.discovery import FileDescriptor
from cutout.service.models import Job, Task
from cutout.service.uws.exceptions import ParameterError

pytestmark = pytest.mark.django_db

CIRCLE_STENCIL = {"type": "circle", "center": {"ra": 0.5, "dec": 0.017}, "radius": 0.016667}


def _create_job_and_task(user, output_path, **task_overrides):
    job = Job.objects.create(owner=user, phase=Job.ExecutionPhase.PENDING)
    fields = {
        "job": job,
        "sequence": 1,
        "survey_id": "des_dr2",
        "stencil": CIRCLE_STENCIL,
        "stencil_type": "circle",
        "band": "g",
        "output_format": "fits",
        "engine": "astrocut",
        "color": False,
        "rgb_bands": "gri",
        "persist": False,
        "output_path": str(output_path),
    }
    fields.update(task_overrides)
    task = Task.objects.create(**fields)
    return job, task


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
    def __init__(self, payload: bytes = b"fake fits data"):
        self.payload = payload
        self.calls: list[dict] = []

    def run_cutout(self, **kwargs):
        self.calls.append(kwargs)
        output_path = Path(kwargs["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.payload)
        return output_path


class _FailingEngine:
    def run_cutout(self, **kwargs):
        raise RuntimeError("engine exploded")


def _patch_runner(monkeypatch, tmp_path, engine=None, input_file="present"):
    if input_file == "present":
        input_file = tmp_path / "DES0002+0001_r4907p01_g.fits.fz"
        input_file.write_bytes(b"tile data")
    engine = engine or _FakeEngine()
    monkeypatch.setattr(cutout_runner, "DesCsvFileLocator", lambda: _FakeLocator(input_file))
    monkeypatch.setattr(cutout_runner, "create_cutout_engine", lambda name: engine)
    return engine


def test_perform_cutout_success_records_result_and_statuses(user, monkeypatch, tmp_path):
    engine = _patch_runner(monkeypatch, tmp_path)
    job, task = _create_job_and_task(user, tmp_path / "out" / "job_1_g.fits")

    result = perform_cutout(job.id, task.id)

    task.refresh_from_db()
    assert task.status == Task.Status.COMPLETED
    assert task.start_time is not None
    assert task.end_time is not None
    assert task.end_time >= task.start_time

    job.refresh_from_db()
    assert job.phase == Job.ExecutionPhase.EXECUTING
    assert job.start_time is not None
    assert job.end_time is None

    job_result = job.results.get()
    assert job_result.result_id == "job_1_g"
    assert job_result.sequence == task.sequence
    assert job_result.size == len(engine.payload)
    assert job_result.mime_type == "application/fits"
    assert job_result.file_path == task.output_path
    assert job_result.url == f"/api/async/{job.id}/results/job_1_g"

    assert result == {
        "task_id": task.id,
        "result_id": "job_1_g",
        "file_path": task.output_path,
        "size": job_result.size,
    }

    engine_kwargs = engine.calls[0]
    assert engine_kwargs["source_id"] == "des_dr2"
    assert engine_kwargs["stencil"] == CIRCLE_STENCIL
    assert engine_kwargs["band"] == "g"
    assert engine_kwargs["output_format"] == "fits"
    assert isinstance(engine_kwargs["input_files"], list)


def test_perform_cutout_color_passes_files_per_band(user, monkeypatch, tmp_path):
    engine = _patch_runner(monkeypatch, tmp_path)
    job, task = _create_job_and_task(
        user,
        tmp_path / "out" / "job_1_rgb.png",
        color=True,
        rgb_bands="gri",
        output_format="png",
    )

    perform_cutout(job.id, task.id)

    engine_kwargs = engine.calls[0]
    assert isinstance(engine_kwargs["input_files"], dict)
    assert sorted(engine_kwargs["input_files"].keys()) == ["g", "i", "r"]
    assert job.results.get().mime_type == "image/png"


def test_perform_cutout_is_idempotent_for_reruns(user, monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path)
    job, task = _create_job_and_task(user, tmp_path / "out" / "job_1_g.fits")

    perform_cutout(job.id, task.id)
    perform_cutout(job.id, task.id)

    assert job.results.count() == 1
    task.refresh_from_db()
    assert task.status == Task.Status.COMPLETED


def test_perform_cutout_engine_error_marks_task_and_job(user, monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path, engine=_FailingEngine())
    job, task = _create_job_and_task(user, tmp_path / "out" / "job_1_g.fits")

    with pytest.raises(RuntimeError, match="engine exploded"):
        perform_cutout(job.id, task.id)

    task.refresh_from_db()
    assert task.status == Task.Status.ERROR
    assert task.error_message == "engine exploded"
    assert task.end_time is not None

    job.refresh_from_db()
    assert job.phase == Job.ExecutionPhase.ERROR
    assert job.end_time is not None
    assert job.results.count() == 0


def test_perform_cutout_no_files_marks_error(user, monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path, input_file=None)
    job, task = _create_job_and_task(user, tmp_path / "out" / "job_1_g.fits")

    with pytest.raises(ParameterError, match="No files found"):
        perform_cutout(job.id, task.id)

    task.refresh_from_db()
    assert task.status == Task.Status.ERROR
    assert "No files found" in task.error_message

    job.refresh_from_db()
    assert job.phase == Job.ExecutionPhase.ERROR


def test_perform_cutout_skips_aborted_job(user, monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path)
    job, task = _create_job_and_task(user, tmp_path / "out" / "job_1_g.fits")
    job.phase = Job.ExecutionPhase.ABORTED
    job.save()

    result = perform_cutout(job.id, task.id)

    assert result == {}
    task.refresh_from_db()
    assert task.status == Task.Status.PENDING
    assert job.results.count() == 0


def test_perform_cutout_rejects_task_from_another_job(user, monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path)
    job_a, _ = _create_job_and_task(user, tmp_path / "out" / "job_a.fits")
    job_b, task_b = _create_job_and_task(user, tmp_path / "out" / "job_b.fits")

    with pytest.raises(ValueError, match="does not belong"):
        perform_cutout(job_a.id, task_b.id)

    task_b.refresh_from_db()
    assert task_b.status == Task.Status.PENDING
    job_a.refresh_from_db()
    assert job_a.phase == Job.ExecutionPhase.PENDING
