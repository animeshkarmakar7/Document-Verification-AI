from celery import Celery
from kombu import Exchange, Queue

from app.config.settings import settings

celery_app = Celery(
    "legaldocai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

default_exchange = Exchange("legaldocai", type="direct")

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_accept_content=["json"],
    task_queues=(
        Queue("celery", default_exchange, routing_key="celery"),
        Queue("cpu", default_exchange, routing_key="cpu"),
        Queue("gpu", default_exchange, routing_key="gpu"),
        Queue("analysis", default_exchange, routing_key="analysis"),
    ),
    task_default_queue="celery",
    task_default_exchange="legaldocai",
    task_default_routing_key="celery",
    task_routes={
        "ingestion.process_page_shard": {"queue": "cpu"},
        "ingestion.analyze_document": {"queue": "cpu"},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    result_expires=86_400,
)
