import type { NextConfig } from "next";

// Static-export response headers are configured in frontend/vercel.json.
const nextConfig: NextConfig = {
  output: "export",
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
