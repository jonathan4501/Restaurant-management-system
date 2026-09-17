import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";
import withSerwistInit from "@serwist/next";

const withSerwist = withSerwistInit({
  swSrc: "sw/sw.ts",
  swDest: "public/sw.js",
  // Manual register so we can prompt "Update available" instead of swapping mid-service.
  register: false,
  // Never reload the till when the WAN flickers back — Accra does that all evening.
  reloadOnOnline: false,
  disable: process.env.NODE_ENV === "development",
});

const nextConfig: NextConfig = {
  /* config options here */
};

const sentryEnabled = Boolean(process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_DSN);

const withPwa = withSerwist(nextConfig);

export default sentryEnabled
  ? withSentryConfig(withPwa, {
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      silent: !process.env.CI,
      // Source maps upload only when an auth token is present (Vercel / CI go-live).
      sourcemaps: {
        disable: process.env.SENTRY_AUTH_TOKEN ? false : true,
      },
      widenClientFileUpload: Boolean(process.env.SENTRY_AUTH_TOKEN),
    })
  : withPwa;
