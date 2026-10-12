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
    default: "Assembly — Multi-Agent AI Consensus Platform",
    template: "%s | Assembly",
  },
  description:
    "Assembly turns one question into a temporary team of AI agents that reason independently, cross-examine, and verify before synthesising a final answer with sources.",
  keywords: ["AI agents", "research", "consensus", "multi-agent", "LLM", "BYOK"],
  alternates: {
    canonical: "/",
  },
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: "Assembly — Multi-Agent AI Consensus Platform",
    description:
      "One question, a temporary team of AI agents, one verified answer with sources. Bring your own free API keys.",
    url: "/",
    siteName: "Assembly",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "Assembly — Multi-Agent AI Consensus Platform",
    description:
      "One question, a temporary team of AI agents, one verified answer with sources.",
  },
}

import { LayoutWrapper } from "@/components/layout-wrapper"

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <LayoutWrapper>{children}</LayoutWrapper>
      </body>
    </html>
  )
}
