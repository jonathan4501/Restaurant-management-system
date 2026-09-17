# RENZY PWA (WS07 — shell + ordering)

## Run against Prism mock

```powershell
cd frontend
npm install
npm run mock    # http://127.0.0.1:4010
npm run dev     # http://127.0.0.1:3000
```

`NEXT_PUBLIC_API_URL=http://127.0.0.1:4010` (host only; paths include `/api/v1/...`).

## Screens

- `/login` — device enrolment + PIN pad + role routing
- `/login/chooser` — manager station picker
- `/order` — tables → menu → modifiers → draft → send
- `/order?mode=guest` / `/order?mode=qr` — guest surfaces
- `/guest/[qr_token]` — QR entry
- `components/AuthoriseSheet` — manager PIN + reason

## Tests

```powershell
npm test
npm run typecheck
npm run test:e2e
```

`npm run types` and `npm run mock` both read `backend/openapi.json`, which drf-spectacular generates.
It is the only schema for this API — regenerate it with `make openapi`, never hand-edit it.
