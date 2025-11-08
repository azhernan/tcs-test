import os

from celery import Celery

broker_url = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")
result_backend = os.getenv(
    "CELERY_RESULT_BACKEND", "db+postgresql+psycopg2://tcs:tcs@db:5432/tcsdb"
)

celery = Celery("tcs_demo", broker=broker_url, backend=result_backend)

# --- Config ---
celery.conf.task_acks_late = True
celery.conf.worker_prefetch_multiplier = 1
celery.conf.task_default_retry_delay = 5
celery.conf.task_time_limit = 60

# 👇 Registrar explícitamente el módulo de tareas
celery.conf.update(imports=("app.tasks",))
# (alternativa: celery.autodiscover_tasks(["app"]))
