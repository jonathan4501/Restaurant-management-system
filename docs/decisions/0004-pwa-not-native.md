# ADR-0004 — One PWA, not native apps

**Status:** Accepted · 2026-09-14

## Context

Four surfaces are needed: guest ordering, kitchen display, cashier, owner back office. React Native
is already in the team's toolkit, which makes native the tempting default.

## Decision

A **single Next.js PWA** with role-scoped views and an ordering `mode` flag
(`waiter` / `guest` / `qr`). Installed to the home screen on Android tablets.

## Rationale

| | PWA | React Native |
|---|---|---|
| Distribution | Open a URL, add to home screen | Play Store review, or APK sideloading and signing keys |
| Updates | Deploy; devices get it on next open | Store review lag, or staff stuck on old versions |
| Device support | Any tablet, phone, laptop, smart-TV browser | Android and iOS only |
| Native capability needed here | None | Paying for unused capability |
| Cost to a solo developer | One build | Two builds plus store maintenance |

Nothing in this system needs camera, Bluetooth, GPS or background services. Printing goes through the
Raspberry Pi bridge, not the device.

The update path is the clincher: pushing a fix **during a live dinner service** must not involve an
app store. Familiarity with React Native is not a reason to accept that tax.

## Consequences

- Offline capability is the service worker's job, and must be built properly (ADR-0002) rather than
  inherited from a native shell.
- iOS PWA support is weaker than Android's. Acceptable — the restaurant's devices are Android.
- The kitchen display runs the same PWA full-screen in a browser on a mini-PC or Android TV box.

## If a hardened kiosk is needed later

Wrap the PWA in a **Trusted Web Activity** so guest tablets cannot be navigated away from the app.
That is a thin shell around the same build, not a second application.
