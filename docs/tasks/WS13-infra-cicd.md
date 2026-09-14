# WS13 — Infrastructure, CI/CD, backups, observability

**Goal:** everything remotely deployable, debuggable and recoverable from Lomé. Nobody drives to Accra.

**Depends on:** WS00. **Blocks:** Phase 1 go-live.

## Owns

`infra/`, `.github/workflows/`, `backend/config/settings/prod.py`, Sentry wiring in backend and frontend.

## Build

1. **Production compose** on one VPS (Hetzner/DO, Amsterdam or London): `caddy` (TLS via Cloudflare DNS
   challenge, `flush_interval -1` on `/api/v1/stream`), `api` (uvicorn, 2 workers), `worker`, `beat`,
   `redis` (persistence on, `maxmemory-policy noeviction`). Postgres is **managed** (`DATABASE_URL`);
   `compose.prod.yml` has no `db` service. Healthchecks on every service; `restart: unless-stopped`.
2. **Deploy**: `deploy.yml` on push to `main` after CI: build + push images to GHCR tagged by SHA, SSH to
   the VPS, `docker compose pull && up -d`, `migrate` in the `api` container, smoke `GET /readyz`. Roll
   back = redeploy the previous SHA (documented one-liner).
3. **Frontend** on Vercel (or the same Caddy, decide by env) — the stream stays on the VPS either way;
   `NEXT_PUBLIC_API_URL` points at it.
4. **Sentry**: backend (Django, Celery, Redis integrations, `restaurant_id`/`device_id` tags, release =
   SHA), frontend (`@sentry/nextjs`, source maps), bridge (plain SDK). Alert rule: any error on
   `/api/v1/orders/*/submit` or `/sessions/*/payments` pages immediately.
5. **Uptime**: Better Stack or UptimeRobot on `/healthz` and on the frontend; SMS/WhatsApp to the developer.
6. **Backups**: even with managed Postgres, nightly `pg_dump` to Cloudflare R2 (`rclone`), 30-day
   retention, and a **monthly restore test job** in GitHub Actions that restores into a scratch Postgres and
   runs `verify_projections`. An untested backup is not a backup.
7. **Media**: R2 for menu images via `django-storages`; `MEDIA_URL` through Cloudflare.
8. **Roles**: `infra/db/roles.sql` creates `app_user` without `UPDATE/DELETE` on `order_events`; document how
   to apply it on the managed instance.
9. **Runbook** `infra/RUNBOOK.md`: deploy, roll back, rotate a device token, revoke a tablet, restore a
   backup, rebuild projections, what to do at 22:00 on a Friday when the stream dies.

## Tests required

- CI green on a clean clone.
- Restore-test workflow passes against last night's dump.
- `curl -N` against production `/stream` stays open > 5 minutes through Caddy and Cloudflare.

## Exit criteria

A change merged to `main` is live at RENZY within ten minutes with no SSH session opened by a human,
and last night's backup restores cleanly.
