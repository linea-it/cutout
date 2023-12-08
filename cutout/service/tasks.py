from pathlib import Path
from typing import Any, Dict

from config import celery_app
from cutout.lib.cutout import Cutout
from cutout.lib.des_cutout import DesCutout
from cutout.service.uws.job import uws_job_completed


@celery_app.task()
def des_cutout_circle(**kwargs) -> str:
    dc = DesCutout()
    result = dc.cutout_circle(**kwargs)
    return str(result)


@celery_app.task()
def image_cutout(job_id: str, source_id: str, stencil: Dict[str, Any], band: str, format: str, path: str) -> str:
    ct = Cutout(source_id, stencil, band, format)
    result = ct.create(path)
    # return str(result)
    return "Resultado do cutout 1"


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
