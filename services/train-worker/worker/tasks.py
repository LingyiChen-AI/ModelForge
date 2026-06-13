from modelforge_common.task_names import TRAIN_TASK

from worker.celery_app import celery_app


@celery_app.task(name=TRAIN_TASK, bind=True)
def train_task(self, training_job_id: int):
    # 实际实现见 Task 16
    raise NotImplementedError
