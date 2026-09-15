"""
Stub for the Raspberry Pi print bridge (WS printing / future package).

The bridge is a small long-running process on-prem; initialise the plain Sentry SDK
the same way when that package lands. Do not use Django integrations here.

  pip install sentry-sdk
  export SENTRY_DSN=… GIT_SHA=… SENTRY_ENVIRONMENT=production
  python sentry.example.py   # smoke only
"""

from __future__ import annotations

import os

import sentry_sdk

dsn = os.environ.get("SENTRY_DSN")
if dsn:
    sentry_sdk.init(
        dsn=dsn,
        release=os.environ.get("GIT_SHA"),
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("component", "print_bridge")

if __name__ == "__main__":
    if not dsn:
        print("SENTRY_DSN unset — bridge Sentry stub is idle")
    else:
        print("Sentry initialised for print bridge stub")
