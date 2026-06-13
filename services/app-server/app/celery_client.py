from celery import Celery
from app.config import settings
from modelforge_common.task_names import TRAIN_TASK

_celery = Celery("modelforge-client", broker=settings.redis_url)

def send_train_task(training_job_id: int) -> str:
    result = _celery.send_task(TRAIN_TASK, args=[training_job_id])
    return result.id
