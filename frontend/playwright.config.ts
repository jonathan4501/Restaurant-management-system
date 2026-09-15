import { defineConfig, devices } from "@playwright/test";

const mockPort = Number(process.env.MOCK_PORT ?? 4012);
const appPort = 3000;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "list",
  use: { baseURL: `http://127.0.0.1:${appPort}`, trace: "on-first-retry" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `npx prism mock ./mock/openapi.json -p ${mockPort} --host 127.0.0.1`,
      url: `http://127.0.0.1:${mockPort}/api/v1/menu`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
    {
      command: "npm run dev",
      url: `http://127.0.0.1:${appPort}`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: { NEXT_PUBLIC_API_URL: `http://127.0.0.1:${mockPort}` },
    },
  ],
});
