import type { Metadata } from "next"
import { Inter, JetBrains_Mono } from "next/font/google"
import "./globals.css"

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
})

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
})

export const metadata: Metadata = {
  metadataBase: new URL("https://assembly-murex.vercel.app"),
  title: {
    default: "Assembly: one hard question, one cited answer",
    template: "%s | Assembly",
  },
  description:
    "Stop trusting one model with hard questions. Assembly runs your question past agents from 3 or more model families and returns one sourced answer in 3 to 15 minutes. Free, BYOK, no account.",
  keywords: ["AI agents", "research", "consensus", "multi-agent", "LLM", "BYOK"],
  alternates: {
    canonical: "/",
  },
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: "Assembly: one hard question, one cited answer",
    description:
      "Agents from 3 or more model families argue first. You keep one sourced answer with confidence stated.",
    url: "/",
    siteName: "Assembly",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "Assembly: one hard question, one cited answer",
    description:
      "Agents from 3 or more model families argue first. You keep one sourced answer.",
  },
}

import { LayoutWrapper } from "@/components/layout-wrapper"
import { CookieBanner } from "@/components/cookie-banner"

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <LayoutWrapper>{children}</LayoutWrapper>
        <CookieBanner />
      </body>
    </html>
  )
}
