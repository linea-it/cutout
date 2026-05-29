from config import celery_app


@celery_app.task()
def ping(x):
    return f"pong:{x}"
