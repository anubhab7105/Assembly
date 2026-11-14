import { defineConfig } from "vitest/config"
import path from "path"

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    // Playwright specs live in tests/ and run under `npx playwright test`.
    // scripts/audit-high.test.mjs uses node:test (`npm run audit:test`).
    exclude: ["tests/**", "scripts/**", "node_modules/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
})
