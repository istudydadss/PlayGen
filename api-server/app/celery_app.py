"""Celery 应用配置"""
from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "playgen",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_routes={
        "app.tasks.collector.*": {"queue": "collector"},
        "app.tasks.executor.*": {"queue": "execution"},
        "app.tasks.analyzer.*": {"queue": "collector"},
    },
    beat_schedule={},
)
