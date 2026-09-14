"""
Production settings. Secrets come from the environment — never from the repo.

Sentry and R2 (django-storages) are env-gated so a missing DSN/keys never crash boot;
local prod-like runs without credentials still start.
"""

from __future__ import annotations

import os

from .base import *  # noqa: F403

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")  # noqa: F405
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# ---- Sentry (Django + Celery + Redis) --------------------------------------------------------
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    def _before_send(event: dict, hint: dict) -> dict | None:  # noqa: ARG001
        # Tag critical money / order paths for alert rules (see infra/sentry/alert-rules.md).
        request = (event.get("request") or {}) if isinstance(event, dict) else {}
        url = str(request.get("url") or "")
        if "/api/v1/orders/" in url and url.rstrip("/").endswith("/submit"):
            event.setdefault("tags", {})["alert_priority"] = "immediate"
            event.setdefault("tags", {})["critical_path"] = "order_submit"
        if "/sessions/" in url and "/payments" in url:
            event.setdefault("tags", {})["alert_priority"] = "immediate"
            event.setdefault("tags", {})["critical_path"] = "session_payment"
        return event

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        release=os.environ.get("GIT_SHA") or None,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,
        before_send=_before_send,
    )

# ---- Media on Cloudflare R2 (django-storages). Local volume if unset. ------------------------
_r2_bucket = os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
_r2_endpoint = os.environ.get("AWS_S3_ENDPOINT_URL", "").strip()
_r2_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
_r2_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()

if _r2_bucket and _r2_endpoint and _r2_key and _r2_secret:
    _custom_domain = os.environ.get("AWS_S3_CUSTOM_DOMAIN", "").strip() or None
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": _r2_key,
                "secret_key": _r2_secret,
                "bucket_name": _r2_bucket,
                "endpoint_url": _r2_endpoint,
                "region_name": os.environ.get("AWS_S3_REGION_NAME", "auto"),
                "default_acl": None,
                "querystring_auth": False,
                "file_overwrite": False,
                **({"custom_domain": _custom_domain} if _custom_domain else {}),
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    if _custom_domain:
        MEDIA_URL = f"https://{_custom_domain}/"
