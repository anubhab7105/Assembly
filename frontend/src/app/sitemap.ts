import type { MetadataRoute } from "next"

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://assembly-murex.vercel.app"
  const now = new Date()
  return [
    { url: `${base}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/chat`, lastModified: now, changeFrequency: "weekly", priority: 0.8 },
    { url: `${base}/settings`, lastModified: now, changeFrequency: "monthly", priority: 0.6 },
    { url: `${base}/executions`, lastModified: now, changeFrequency: "weekly", priority: 0.5 },
  ]
}
