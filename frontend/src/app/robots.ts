import type { MetadataRoute } from "next"

export const dynamic = "force-static"

export default function robots(): MetadataRoute.Robots {
  const base = "https://assembly-murex.vercel.app"
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/styleguide/"],
      },
    ],
    sitemap: `${base}/sitemap.xml`,
  }
}
