import os

os.environ.setdefault("SECRET_KEY", "test-only-not-a-secret-but-long-enough-for-hmac")
os.environ.setdefault("DATABASE_URL", "postgres://renzy:renzy@localhost:5433/renzy")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

from .base import *  # noqa: E402

DEBUG = False
# Fast hashing in tests; production uses argon2 (see accounts.pins for the PIN hasher).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
LOGGING["root"]["level"] = "WARNING"  # type: ignore[index]
