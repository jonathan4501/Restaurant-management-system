import os

os.environ.setdefault("SECRET_KEY", "dev-only-not-a-secret-but-long-enough-for-hmac")
os.environ.setdefault("DATABASE_URL", "postgres://renzy:renzy@localhost:5433/renzy")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from .base import *  # noqa: E402

DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
