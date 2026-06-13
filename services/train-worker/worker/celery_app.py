from celery import Celery

from worker.config import settings

celery_app = Celery("modelforge", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_track_started = True
celery_app.conf.worker_prefetch_multiplier = 1  # 一次只取一个 GPU 任务

import worker.tasks  # noqa: E402,F401  注册任务
