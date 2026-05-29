import json
from pathlib import Path
from typing import Any, Dict, List, Union

from django.utils import timezone

from config import celery_app
from cutout.lib.des_cutout import DesCutout
from cutout.service.cutout_engine import create_cutout_engine
from cutout.service.models import Job


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


def _ensure_unpacked(files: list[str] | dict[str, list[str]] | None) -> list[str] | dict[str, list[str]] | None:
    """If any input paths point to compressed `.fz` archives, unpack them to a tmp location and
    return a structure of uncompressed paths suitable for engines like `astrocut`.

    Returns the same shape as `files` but with `.fits` paths.
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
            # log unpacked mapping
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
    # If inputs reference compressed archives, unpack them for engines that require `.fits` files.
    cutout_engine = create_cutout_engine(engine)
    unpacked = _ensure_unpacked(files)
    print(f"[tasks] image_cutout unpacked files={unpacked}")
    # validate the (possibly unpacked) input paths exist before running engine
    _validate_input_files(unpacked)

    try:
        print(f"[tasks] calling engine.run_cutout engine={engine} path={path}")
        result = cutout_engine.run_cutout(
            source_id=source_id,
            stencil=stencil,
            input_files=unpacked,
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


@celery_app.task()
def run_async_cutout_job(job_id: str, task_params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    job = Job.objects.get(pk=int(job_id))
    if job.phase == Job.ExecutionPhase.ABORTED:
        return []

    job.phase = Job.ExecutionPhase.EXECUTING
    job.start_time = timezone.now()
    job.end_time = None
    job.save(update_fields=["phase", "start_time", "end_time"])

    results: list[dict[str, Any]] = []

    try:
        job.results.all().delete()

        for task in task_params:
            result = fake_image_cutout(
                job_id=job_id,
                source_id=task["id"],
                stencil=task["stencil"],
                engine=task["engine"],
                band=task["band"],
                format=task["format"],
                path=task["path"],
                files=task.get("files"),
                color=task.get("color", False),
                rgb_bands=task.get("rgb_bands"),
                persist=task.get("persist", False),
            )
            result["url"] = f"/api/async/{job_id}/results/{result['result_id']}"
            results.append(result)

        for sequence, result in enumerate(results, start=1):
            job.results.create(
                result_id=result["result_id"],
                sequence=sequence,
                size=result.get("size") or 0,
                mime_type=result.get("mime_type"),
                url=result.get("url"),
                file_path=result.get("file_path"),
            )

        job.phase = Job.ExecutionPhase.COMPLETED
        job.end_time = timezone.now()
        job.save(update_fields=["phase", "end_time"])
        return results
    except Exception:
        job.phase = Job.ExecutionPhase.ERROR
        job.end_time = timezone.now()
        job.save(update_fields=["phase", "end_time"])
        raise


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
