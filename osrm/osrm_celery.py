"""
Celery app used for managing OSRM server instances.
"""
from celery import Celery

from osrm import settings


def get_app(redis_host: str, redis_port: int, db_index: int) -> Celery:
    """
    Create and configure celery app instance.
    """
    celery_app = Celery("osrm")

    config = {
        "broker_url": f"redis://{redis_host}:{redis_port}/{db_index}",
        "broker_transport_options": {"fanout_prefix": True, "fanout_patterns": True},
        "result_backend": f"redis://{redis_host}:{redis_port}/{db_index}",
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "enable_utc": True,
        "worker_concurrency": 1,
        "imports": ("osrm.tasks",),
        "task_ignore_result": True,
        "result_expires": 10,
        "worker_log_format": "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    }

    celery_app.conf.update(config)
    return celery_app


# pylint: disable=invalid-name
app = get_app(
    redis_host=settings.CELERY_REDIS_HOST,
    redis_port=settings.CELERY_REDIS_PORT,
    db_index=settings.CELERY_REDIS_DATABASE,
)
