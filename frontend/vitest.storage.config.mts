import { defineConfig } from "vitest/config"
import path from "path"

export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    include: [
      "src/lib/storage.test.ts",
      "src/lib/api-client-attachments.test.ts",
      "src/lib/history-import.test.ts",
      "src/lib/attachments.test.ts",
      "src/app/executions/external-links.test.tsx",
      "src/app/reduced-motion.test.ts",
    ],
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
})