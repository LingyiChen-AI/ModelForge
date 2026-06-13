from worker.celery_app import celery_app
from modelforge_common.task_names import TRAIN_TASK


def test_train_task_registered():
    assert TRAIN_TASK in celery_app.tasks
