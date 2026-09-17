/**
 * RENZY service worker (Serwist / Workbox).
 *
 * Precache the app shell. Runtime-cache menu and tables (stale-while-revalidate,
 * ETag-friendly). Network-only for commands and the SSE stream — never cache a
 * write or a live event.
 *
 * skipWaiting is false so a new version waits for an "Update available" accept
 * rather than swapping mid-service.
 */

/// <reference lib="webworker" />

import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { NetworkOnly, Serwist, StaleWhileRevalidate } from "serwist";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

const API_READ = /\/api\/v1\/(guest\/)?(menu|tables)(\/|$|\?)/;
const API_STREAM = /\/api\/v1\/(events|stream|sse)(\/|$|\?)/;

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: false,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    {
      matcher: ({ request }) => request.method !== "GET" && request.method !== "HEAD",
      handler: new NetworkOnly(),
    },
    {
      matcher: ({ url }) => API_STREAM.test(url.pathname),
      handler: new NetworkOnly(),
    },
    {
      matcher: ({ request, url }) => request.method === "GET" && API_READ.test(url.pathname),
      handler: new StaleWhileRevalidate({
        cacheName: "renzy-api-reads",
        matchOptions: { ignoreSearch: false },
      }),
    },
    ...defaultCache,
  ],
});

serwist.addEventListeners();
