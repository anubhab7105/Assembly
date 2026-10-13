import type { NextConfig } from "next";

// Static-export response headers are configured in frontend/vercel.json.
const nextConfig: NextConfig = {
  output: "export",
  /* config options here */
  // The Next.js app and lockfile live under frontend/ in this monorepo.
  turbopack: {
    root: process.cwd(),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
