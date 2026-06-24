import json
import logging
from pathlib import Path
from typing import Any

from django.utils import timezone

from config import celery_app
from cutout.lib.des_cutout import DesCutout
from cutout.service.cutout_engine import create_cutout_engine
from cutout.service.models import Job, Task


def _validate_input_files(files: list[str] | dict[str, list[str]] | None) -> None:
    if not files:
        return

    # normalize to list of paths for existence check
    paths: list[str] = []
    if isinstance(files, dict):
        for v in files.values():
            paths.extend(v or [])
    else:
        paths = list(files)

    missing = [f for f in paths if not Path(f).exists()]
    if missing:
        msg = "Input file unavailable: " + ", ".join(missing)
        raise FileNotFoundError(msg)


def _ensure_unpacked(
    files: list[str] | dict[str, list[str]] | None,
) -> list[str] | dict[str, list[str]] | None:
    """If any input paths point to compressed ``.fz`` archives, unpack them to a tmp location and
    return a structure of uncompressed paths suitable for engines that require ``.fits`` files.

    .. note::

       ``fits_cut`` from astrocut handles ``.fz`` natively via ``.section``, so this helper
       is currently **not used** by ``image_cutout``.  It is kept as a legacy utility for
       engines or ad-hoc scripts that need uncompressed files on disk.
    """
    if not files:
        return files

    dc = DesCutout()

    def _unpack_path(p: str) -> str:
        pth = Path(p)
        if pth.suffix == ".fz":
            out_name = pth.name.rsplit(".fz", 1)[0]
            out_path = dc.tmp_path.joinpath(out_name)
            if not out_path.exists():
                try:
                    dc.funpack(pth, out_path)
                except Exception:
                    # let downstream code fail with clearer message if unpack fails
                    pass
            return str(out_path)
        return str(p)

    if isinstance(files, dict):
        out: dict[str, list[str]] = {}
        for k, lst in files.items():
            out[k] = [_unpack_path(p) for p in (lst or [])]
            print(f"[tasks] _ensure_unpacked: band={k} unpacked_paths={out[k]}")
        return out

    return [_unpack_path(p) for p in files]


@celery_app.task()
def des_cutout_circle(**kwargs) -> str:
    dc = DesCutout()
    result = dc.cutout_circle(**kwargs)
    return str(result)


@celery_app.task()
def image_cutout(
    job_id: str,
    source_id: str,
    stencil: dict[str, Any],
    engine: str,
    band: str,
    format: str,
    path: str,
    files: list[str] | None = None,
    color: bool = False,
    rgb_bands: str | None = None,
    persist: bool = False,
) -> str:
    print(
        "[tasks] image_cutout START "
        f"job_id={job_id} engine={engine} band={band} format={format} "
        f"color={color} rgb_bands={rgb_bands}"
    )
    print(f"[tasks] image_cutout initial files={files}")
    cutout_engine = create_cutout_engine(engine)
    _validate_input_files(files)

    try:
        print(f"[tasks] calling engine.run_cutout engine={engine} path={path}")
        result = cutout_engine.run_cutout(
            source_id=source_id,
            stencil=stencil,
            input_files=files,
            band=band,
            output_format=format,
            output_path=path,
            color=color,
            rgb_bands=rgb_bands,
            persist=persist,
        )
        print(f"[tasks] engine.run_cutout completed result={result}")
    except Exception as e:
        print(f"[tasks] engine.run_cutout raised: {type(e).__name__}: {e}")
        raise
    return str(result)


def fake_image_cutout(
    job_id: str,
    source_id: str,
    stencil: dict[str, Any],
    engine: str,
    band: str,
    format: str,
    path: str,
    files: list[str] | None = None,
    color: bool = False,
    rgb_bands: str | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    result_path = Path(path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": job_id,
        "source_id": source_id,
        "stencil": stencil,
        "engine": engine,
        "band": band,
        "format": format,
        "path": path,
        "files": files or [],
        "color": color,
        "rgb_bands": rgb_bands,
        "persist": persist,
        "mode": "fake_async_result",
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    mime_type = "image/png" if str(format).lower() == "png" else "application/fits"
    return {
        "result_id": result_path.stem,
        "file_path": str(result_path),
        "mime_type": mime_type,
        "size": result_path.stat().st_size,
    }


@celery_app.task(
    bind=True,
    autoretry_for=(Job.DoesNotExist, Task.DoesNotExist),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def run_cutout_for_pos(self, job_id: str, task_id: str) -> dict[str, Any]:
    """Execute a single cutout unit. Reads all parameters from the Task row in DB."""
    logger = logging.getLogger("cutout")
    job_pk = int(str(job_id).strip())
    task_pk = int(str(task_id).strip())

    logger.info(
        "[run_cutout_for_pos] celery_task_id=%s retries=%s job_id=%r task_id=%r",
        self.request.id,
        self.request.retries,
        job_id,
        task_id,
    )

    job = Job.objects.get(pk=job_pk)
    task = Task.objects.get(pk=task_pk)

    if job.phase == Job.ExecutionPhase.ABORTED:
        logger.info("[run_cutout_for_pos] Job %r is ABORTED, skipping", job_id)
        return {}

    # First task to run transitions QUEUED → EXECUTING (idempotent under concurrency)
    Job.objects.filter(pk=job_pk, phase=Job.ExecutionPhase.QUEUED).update(
        phase=Job.ExecutionPhase.EXECUTING,
        start_time=timezone.now(),
    )

    # PENDING → EXECUTING (idempotent — only first call wins if multi-band)
    Task.objects.filter(pk=task_pk, status=Task.Status.PENDING).update(
        status=Task.Status.EXECUTING,
        start_time=timezone.now(),
    )

    try:
        result = fake_image_cutout(
            job_id=job_id,
            source_id=task.survey_id,
            stencil=task.stencil,
            engine=task.engine,
            band=task.band,
            format=task.output_format,
            path=task.output_path,
            color=task.color,
            rgb_bands=task.rgb_bands,
            persist=task.persist,
        )

        job.results.create(
            result_id=result["result_id"],
            sequence=task.sequence,
            size=result.get("size") or 0,
            mime_type=result.get("mime_type"),
            url=f"/api/async/{job_id}/results/{result['result_id']}",
            file_path=result.get("file_path"),
        )

        Task.objects.filter(pk=task_pk).update(
            status=Task.Status.COMPLETED,
            end_time=timezone.now(),
        )

        logger.info("[run_cutout_for_pos] completed task_id=%r result_id=%s", task_id, result.get("result_id"))
        return {"task_id": task_pk, "result_id": result["result_id"]}

    except Exception as exc:
        Job.objects.filter(pk=job_pk).update(
            phase=Job.ExecutionPhase.ERROR,
            end_time=timezone.now(),
        )
        Task.objects.filter(pk=task_pk).update(
            status=Task.Status.ERROR,
            end_time=timezone.now(),
            error_message=str(exc),
        )
        raise


@celery_app.task
def finalize_job(_results: list[dict[str, Any]], job_id: str) -> None:
    """Chord callback: runs when all run_cutout_for_pos tasks for a job complete.

    JobResults and Task statuses are already set by each individual worker task.
    This callback only transitions the Job to COMPLETED.
    """
    logger = logging.getLogger("cutout")
    job_pk = int(str(job_id).strip())

    try:
        job = Job.objects.get(pk=job_pk)
    except Job.DoesNotExist:
        logger.error("[finalize_job] Job %r not found", job_id)
        return

    if job.phase in (Job.ExecutionPhase.ABORTED, Job.ExecutionPhase.ERROR):
        logger.info("[finalize_job] job_id=%r phase=%s — skipping COMPLETED transition", job_id, job.phase)
        return

    job.phase = Job.ExecutionPhase.COMPLETED
    job.end_time = timezone.now()
    job.save(update_fields=["phase", "end_time"])
    logger.info("[finalize_job] job_id=%r marked COMPLETED", job_id)


# @celery_app.task()
# def on_success_cutout(job_id: str, ) -> str:
#     return str(result)


@celery_app.task(bind=True)
# def job_completed(job_id: str, results) -> str:
def job_completed(result, **kwargs) -> str:
    print(result)
    print(kwargs)
    return f"TESTE: {result}"
    # uws_job_completed(job_id=job_id, results=results)


@celery_app.task()
def on_success(retval, task_id, args, kwargs) -> str:
    return f"ON SUCCESS {task_id}"


@celery_app.task()
def task_completed() -> str:
    return "Completed"


@celery_app.task()
def task_1(x, **kwargs):
    s = f"Task 1: {x}"
    print(s)
    return s


@celery_app.task()
def ping(x):
    return f"pong:{x}"
