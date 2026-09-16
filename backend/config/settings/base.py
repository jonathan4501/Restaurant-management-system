"""
Base settings. Everything environment-specific comes from environment variables.
See infra/.env.example for the full list.
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable {name}")
    return value


def env_list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


SECRET_KEY = env("SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "apps.core",
    "apps.accounts",
    "apps.menu",
    "apps.floor",
    "apps.orders",
    "apps.payments",
    "apps.realtime",
    "apps.reporting",
    "apps.printing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(env("DATABASE_URL"), conn_max_age=60, conn_health_checks=True)
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TIMEZONE = "UTC"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"  # storage. Restaurant-local time is derived per restaurant, never from this.
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "idempotency-key",
    "x-device-token",
    "x-client-time",
    "last-event-id",
    "if-none-match",
]
CORS_EXPOSE_HEADERS = ["idempotent-replayed", "etag", "date"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.principals.PrincipalAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.core.permissions.RolePermission"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "apps.core.openapi.CommandAutoSchema",
    "EXCEPTION_HANDLER": "apps.core.errors.exception_handler",
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_THROTTLE_RATES": {"guest": "60/min"},
}

SPECTACULAR_SETTINGS = {
    "TITLE": "RENZY API",
    "DESCRIPTION": (
        "Order and sales system for RENZY, Shiashi, Accra. All money fields are integer pesewas "
        "(`*_pesewas`). Every POST requires an `Idempotency-Key` (UUIDv7). Gross sales figures are "
        "'Money taken' — gross cash through the till, not revenue."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "POSTPROCESSING_HOOKS": ["apps.core.openapi.add_standard_headers"],
}

# ---- RENZY-specific -------------------------------------------------------------------------
JWT_SIGNING_KEY = env("JWT_SIGNING_KEY", SECRET_KEY)
STAFF_TOKEN_TTL_SECONDS = 12 * 60 * 60
GUEST_TOKEN_TTL_SECONDS = 2 * 60 * 60
AUTHORISATION_TOKEN_TTL_SECONDS = 60
PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
IDEMPOTENCY_IN_PROGRESS_TAKEOVER_SECONDS = 60
SSE_HEARTBEAT_SECONDS = 15
SSE_REPLAY_LIMIT = 1000
SSE_AUTH_RECHECK_SECONDS = 30  # a revoked device or logged-out token is cut off within this
METRICS_TOKEN = env("METRICS_TOKEN", "")  # /metrics needs this bearer; unset = 404 unless DEBUG
ERROR_TYPE_BASE = "https://renzy.app/errors/"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.logging.JsonFormatter",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {"django.request": {"level": "WARNING"}},
}
