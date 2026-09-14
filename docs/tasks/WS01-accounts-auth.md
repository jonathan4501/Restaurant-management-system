# WS01 — Accounts and authentication

**Goal:** every principal in `08-backend-architecture.md §6` can be established end-to-end, and every
failure is recorded.

**Depends on:** WS00. **Blocks:** WS03 (needs staff principals in tests), WS07 (login screen).

## Owns

`backend/apps/accounts/` (all of it except what WS00 created — extend, do not rewrite).

## Endpoints (see `09-api-contract.md`)

`POST /devices/enrol` · `GET /devices/me` · `POST /auth/pin` · `POST /auth/authorise` ·
`POST /auth/owner/login` · `POST /auth/owner/totp` · `POST /auth/logout` ·
`POST /sessions/{id}/guest-token` (the handler lives here; the route is registered under floor).

## Events

`DEVICE_ENROLLED` `DEVICE_REVOKED` `PIN_FAILED` `PIN_LOCKED` `MANAGER_AUTHORISED`.

## Build

1. Device enrolment: admin action "generate enrolment code" (8 chars, 15-minute expiry). `POST /devices/enrol`
   exchanges it for a 32-byte urlsafe token; store `sha256`; return the token once. Revoke action in admin
   emits `DEVICE_REVOKED`; revoked device → 401 `device_revoked` everywhere, including `/stream`.
2. PIN login with argon2id (`argon2-cffi`, `time_cost=2, memory_cost=64MiB`). Redis counter
   `pin_fail:{device_id}` with 15-minute TTL; on the fifth failure emit `PIN_LOCKED` and return 423 with
   `retry_after_seconds`. Success resets the counter. Staff JWT: HS256, `JWT_SIGNING_KEY`, 12 h,
   `{sub, role, rid, did, iat, exp, jti}`; `jti` in Redis so logout can revoke.
3. Manager authorisation: `POST /auth/authorise {pin, purpose}` → verify against MANAGER/OWNER staff of
   this restaurant only; emit `MANAGER_AUTHORISED {purpose}`; store `auth:{token}` in Redis for 60 s with
   `{staff_id, device_id, purpose}`. `CommandView` consumes it: single use (`GETDEL`), device must match,
   purpose must match the view's declared purpose.
4. Owner login: Django auth user linked to `Staff(role=OWNER)`; `django-otp` TOTP device; setup flow in
   admin; session cookie `SameSite=Lax`, `Secure` in prod. `OwnerSessionAuthentication` for the owner API.
5. Guest tokens: `POST /sessions/{id}/guest-token` (waiter hand-over, `mode=guest`) and
   `POST /guest/sessions/{qr_token}` (`mode=qr`; the table must have an open session). 2 h JWT
   `{sid, rid, role: GUEST, mode}`. `GuestAuthentication` + `GuestThrottle` (60/min per `sid`).
6. Admin: staff list with role, active flag, "set PIN" action (never displays a PIN), devices with
   last-seen and revoke, enrolment code generator.

## Tests required

- Enrol → token works; revoked → 401; expired code → 400.
- 4 wrong PINs → 401 each with `PIN_FAILED`; 5th → 423 + `PIN_LOCKED`; correct PIN after lockout expiry works.
- JWT from device A rejected on device B (`did` mismatch).
- Authorisation token: single use; wrong purpose → 403 `authorisation_purpose_mismatch`; expired → 403.
- Guest token cannot read another session (404), cannot call any staff route (403), throttles at 61/min.
- Owner API without TOTP → 401.

## Exit criteria

The `curl` walk-through in `09-api-contract.md §6` steps 1–2 work against a seeded database.
