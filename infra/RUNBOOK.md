# RENZY operations runbook

Operate from anywhere (Lomé, Accra, a café). Nobody drives to the restaurant for a deploy.

Repo on the VPS: `/opt/renzy` (override with GitHub Actions variable `VPS_DEPLOY_PATH`).
Compose file: `infra/compose.prod.yml`. Secrets: `infra/.env` (never committed).

---

## Deploy

Automatic: merge to `main` → CI green → Deploy workflow builds `ghcr.io/<org>/…/backend:<sha>`,
SSHs to the VPS, `pull` + `migrate` + `collectstatic` + `up -d`, smokes `GET /readyz`.

Manual:

```bash
cd /opt/renzy
export IMAGE=ghcr.io/<org>/restaurant-management-system/backend:<sha>
export GIT_SHA=<sha>
echo "IMAGE=$IMAGE" > infra/.image.env
echo "GIT_SHA=$GIT_SHA" >> infra/.image.env
set -a; . infra/.env; . infra/.image.env; set +a
docker compose -f infra/compose.prod.yml pull api worker beat
docker compose -f infra/compose.prod.yml run --rm --no-deps api \
  uv run --no-dev python manage.py migrate --noinput
docker compose -f infra/compose.prod.yml up -d
docker compose -f infra/compose.prod.yml exec -T api curl -fsS http://localhost:8000/readyz
```

Frontend ships separately on Vercel (or the same Caddy if you choose). Set
`NEXT_PUBLIC_API_URL=https://api.<domain>` so commands and **SSE** hit the VPS
(`/api/v1/stream` must never move to serverless — ADR-0003).

---

## Roll back

Redeploy the previous SHA. The Deploy workflow copies `infra/.image.env` → `infra/.image.env.prev`
before each successful pull.

```bash
cd /opt/renzy
cp infra/.image.env.prev infra/.image.env
set -a; . infra/.env; . infra/.image.env; set +a
docker compose -f infra/compose.prod.yml pull api worker beat
docker compose -f infra/compose.prod.yml up -d
docker compose -f infra/compose.prod.yml exec -T api curl -fsS http://localhost:8000/readyz
```

Or: GitHub Actions → Deploy → Run workflow → paste the previous commit SHA.

Database migrations are additive; rolling back code with a forward-only migration usually still works.
If a migration is incompatible, restore the previous night’s dump into a new DB and cut over
(see Restore backup) — do not `migrate` backwards on production without a written plan.

---

## Rotate a device token / enrol a tablet

```bash
docker compose -f infra/compose.prod.yml exec -T api \
  uv run --no-dev python manage.py enrol_device \
  --restaurant RENZY --label "waiter-2" --roles WAITER,CASHIER
```

Copy `device_token=` onto the tablet once. Prefer the owner UI enrolment flow when WS01 ships it;
this command is the break-glass path.

---

## Revoke a tablet

Never `DELETE` the device row. Soft-revoke:

```bash
docker compose -f infra/compose.prod.yml exec -T api uv run --no-dev python manage.py shell <<'PY'
from django.utils import timezone
from apps.accounts.models import Device
from apps.core.tenancy import restaurant_context
import uuid
device_id = uuid.UUID("……")
restaurant_id = uuid.UUID("……")
with restaurant_context(restaurant_id):
    n = Device.objects.filter(id=device_id, revoked_at__isnull=True).update(revoked_at=timezone.now())
print("revoked" if n else "already revoked or missing")
PY
```

Revoked devices get `401 device_revoked` on every command and on `/stream`. Re-enrol issues a new token.

---

## Restore a backup

Nightly: `infra/scripts/backup-pg.sh` → R2 (`BACKUP_RCLONE_REMOTE`). Monthly: GitHub workflow
`Backup restore test` restores into scratch Postgres and runs `verify_projections`.

Disaster recovery (new database, then cut `DATABASE_URL`):

```bash
rclone copyto r2:renzy-backups/postgres/renzy-YYYYMMDDThhmmssZ.dump ./restore.dump
export DATABASE_URL='postgres://owner:…@host:5432/renzy_restored?sslmode=require'
infra/scripts/restore-pg.sh ./restore.dump
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f infra/db/roles.sql
# Point infra/.env DATABASE_URL at app_user on renzy_restored, bounce api/worker/beat
docker compose -f infra/compose.prod.yml up -d api worker beat
```

Then verify:

```bash
docker compose -f infra/compose.prod.yml exec -T api \
  uv run --no-dev python manage.py verify_projections --restaurant <RESTAURANT_UUID>
```

---

## Rebuild projections

If reads look wrong but `order_events` is intact:

```bash
docker compose -f infra/compose.prod.yml exec -T api \
  uv run --no-dev python manage.py rebuild_projections --restaurant <RESTAURANT_UUID>
docker compose -f infra/compose.prod.yml exec -T api \
  uv run --no-dev python manage.py verify_projections --restaurant <RESTAURANT_UUID>
```

---

## Stream outage (Friday 22:00)

Symptoms: kitchen / cashier not updating; `curl -N https://api.<domain>/api/v1/stream` dies or buffers.

1. **Confirm the path is still on the VPS** — not rewritten to Vercel. Cloudflare: disable buffering on
   `/api/v1/stream*`. Caddy must keep `flush_interval -1` (see `infra/Caddyfile`).
2. **Redis**: `docker compose -f infra/compose.prod.yml exec redis redis-cli ping` → `PONG`.
   Persistence uses `maxmemory-policy noeviction` — if Redis is OOM it errors rather than evicting;
   bump `--maxmemory` in compose and restart redis.
3. **API logs**: `docker compose -f infra/compose.prod.yml logs --tail 200 api`.
4. **Restart only api** (keeps redis):  
   `docker compose -f infra/compose.prod.yml up -d --no-deps --force-recreate api`
5. **Clients**: after two consecutive SSE failures the PWA falls back to 3s polling (ADR-0003).
6. **Probe**: `curl -N` with staff auth against `/api/v1/stream` must stay open > 5 minutes.

If Cloudflare is the buffer: temporarily grey-cloud the API hostname, then fix proxy settings.

---

## Apply `app_user` privileges

After first migrate on managed Postgres (as owner):

```bash
psql "$DATABASE_URL_OWNER" -v ON_ERROR_STOP=1 -f infra/db/roles.sql
ALTER ROLE app_user PASSWORD '…';
```

Point `DATABASE_URL` at `app_user`. Confirm `\dp order_events` shows no UPDATE/DELETE for `app_user`.

---

## Secrets checklist (human)

| Secret | Where |
|---|---|
| `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` | GitHub Actions |
| `infra/.env` (`SECRET_KEY`, `JWT_*`, `DATABASE_URL`, …) | VPS only |
| `SENTRY_DSN` / `NEXT_PUBLIC_SENTRY_DSN` | VPS + Vercel |
| `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` | Vercel (source maps) |
| R2 keys + `RCLONE_CONFIG_B64` | VPS cron + GitHub restore-test |
| `CLOUDFLARE_API_TOKEN` | VPS (optional Caddy DNS-01) |
| Better Stack / UptimeRobot | see `infra/uptime/README.md` |
