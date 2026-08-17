from celery import Celery
from app.core.config import get_settings

celery_app = Celery("rachel", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    task_always_eager=get_settings().testing,
    task_eager_propagates=False,
    task_track_started=True,
    include=["app.worker.tasks"],
)
