from celery import Celery
from app.config import settings
from modelforge_common.task_names import TRAIN_TASK

_celery = Celery("modelforge-client", broker=settings.redis_url)

def send_train_task(training_job_id: int) -> str:
    result = _celery.send_task(TRAIN_TASK, args=[training_job_id])
    return result.id

from modelforge_common.task_names import EVAL_TASK

def send_eval_task(eval_run_id: int) -> str:
    result = _celery.send_task(EVAL_TASK, args=[eval_run_id])
    return result.id
