import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  /* config options here */
};

const sentryEnabled = Boolean(process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_DSN);

export default sentryEnabled
  ? withSentryConfig(nextConfig, {
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
  : nextConfig;
