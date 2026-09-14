# Sentry alert rules (configure in the Sentry UI)

Backend tags every authenticated request with `restaurant_id` and `device_id`
(`RequestContextMiddleware`). Release = `GIT_SHA`.

Prod also sets `alert_priority=immediate` and `critical_path` on:

- order submit — URL contains `/api/v1/orders/` and ends with `/submit`
- session payment — URL contains `/sessions/` and `/payments`

## Create these rules before go-live

1. **Immediate — money / submit path**  
   Filter: `tag[alert_priority] is immediate`  
   Action: notify developer (SMS/WhatsApp) on **first** event. No digests.

2. **API error spike**  
   Filter: project = backend, environment = production  
   Condition: > 20 events in 10 minutes  
   Action: email + SMS.

3. **Frontend**  
   Filter: project = renzy-pwa  
   Condition: new issue  
   Action: email (tighten to SMS after noise is low).

## Env vars

| Var | Component |
|---|---|
| `SENTRY_DSN` | Django / Celery / Redis (`config.settings.prod`) |
| `NEXT_PUBLIC_SENTRY_DSN` | Next.js client + server |
| `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` | Source map upload on Vercel build |
| `GIT_SHA` / `VERCEL_GIT_COMMIT_SHA` | Release |

Print bridge: see `infra/bridge/sentry.example.py` when that process exists.
