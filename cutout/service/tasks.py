from pathlib import Path
from typing import Any, Dict, List, Union

from config import celery_app
from cutout.lib.des_cutout import DesCutout
from cutout.service.cutout_engine import create_cutout_engine


def _validate_input_files(files: List[str] | Dict[str, List[str]] | None) -> None:
    if not files:
        return

    # normalize to list of paths for existence check
    paths: List[str] = []
    if isinstance(files, dict):
        for v in files.values():
            paths.extend(v or [])
    else:
        paths = list(files)

    missing = [f for f in paths if not Path(f).exists()]
    if missing:
        msg = "Input file unavailable: " + ", ".join(missing)
        raise FileNotFoundError(msg)


def _ensure_unpacked(files: List[str] | Dict[str, List[str]] | None) -> Union[List[str], Dict[str, List[str]], None]:
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
            out_name = pth.name.rsplit('.fz', 1)[0]
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
        out: Dict[str, List[str]] = {}
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
    stencil: Dict[str, Any],
    engine: str,
    band: str,
    format: str,
    path: str,
    files: List[str] | None = None,
    color: bool = False,
    rgb_bands: str | None = None,
    persist: bool = False,
) -> str:
    print(f"[tasks] image_cutout START job_id={job_id} engine={engine} band={band} format={format} color={color} rgb_bands={rgb_bands}")
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
    return f"Completed"


@celery_app.task()
def task_1(x, **kwargs):
    s = f"Task 1: {x}"
    print(s)
    return s
