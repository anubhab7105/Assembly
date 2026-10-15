import { defineConfig } from "vitest/config"
import path from "path"

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    // Keep Node's native audit tests and dedicated storage suite separate.
    exclude: ["tests/**", "node_modules/**", "scripts/**", "src/lib/storage.test.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
