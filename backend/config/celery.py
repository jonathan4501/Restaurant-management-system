import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("renzy")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Beat cannot know each restaurant's cutover hour, so knock every hour at :10 and let
# `rollup_due_restaurants` decide which tenants have just closed (WS06 §1).
app.conf.beat_schedule = {
    "reporting-rollup-due-restaurants": {
        "task": "reporting.rollup_due_restaurants",
        "schedule": crontab(minute=10),
    },
}
