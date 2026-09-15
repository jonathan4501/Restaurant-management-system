# Uptime monitoring (placeholders)

Nobody is in the building when it breaks — wire SMS/WhatsApp to the developer before go-live.

## Targets

| Check | URL | Expect |
|---|---|---|
| API liveness | `https://api.<domain>/healthz` | `200` JSON `{"ok": true, …}` |
| API readiness | `https://api.<domain>/readyz` | `200` (after deploys) |
| Frontend | `https://app.<domain>/` | `200` |
| SSE (manual) | `curl -N https://api.<domain>/api/v1/stream` | connection > 5 min |

Do **not** put a high-frequency uptime poller on `/api/v1/stream` — use a weekly manual `curl -N`
or a low-frequency authenticated synthetic.

## Better Stack (preferred)

1. Create monitors for `/healthz` and the frontend origin.
2. Incident channel: SMS + WhatsApp/email to the on-call developer.
3. Paste monitor IDs here when created:

```
BETTERSTACK_API_HEALTHZ_ID=
BETTERSTACK_FRONTEND_ID=
BETTERSTACK_STATUS_PAGE=
```

## UptimeRobot (fallback)

- Monitor type: HTTPS, interval 5 minutes
- Alert contacts: developer phone (SMS)

```
UPTIMEROBOT_API_HEALTHZ_ID=
UPTIMEROBOT_FRONTEND_ID=
```

## Cloudflare

Ensure `/api/v1/stream*` is not buffered (see RUNBOOK “Stream outage”). Orange-cloud is fine for TLS
if origin certificates + Full (Strict) are set; grey-cloud is the emergency escape hatch.
