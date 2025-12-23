# yourproject/celery.py
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gme_backend.settings')

app = Celery('gme_backend')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Using Redis as broker and backend
app.conf.broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
app.conf.result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
app.conf.task_track_started = True
