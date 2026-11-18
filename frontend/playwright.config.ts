import { defineConfig, devices } from "@playwright/test"

// E2E coverage exercises the locally hosted workspace, not the marketing-only deployment.
// Use an isolated port and never reuse an existing server: the test server must inherit workspace mode.
process.env.NEXT_PUBLIC_ASSEMBLY_LOCAL = "true"
const testServerUrl = "http://127.0.0.1:3100"

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: testServerUrl,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3100",
    url: testServerUrl,
    reuseExistingServer: false,
    timeout: 120 * 1000,
  },
})
