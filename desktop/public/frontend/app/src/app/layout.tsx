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
  title: {
    default: "Assembly — AI Research Platform",
    template: "%s | Assembly",
  },
  description:
    "Assembly turns one question into a temporary team of AI agents that reason independently, cross-examine, and verify before synthesising a final answer.",
  keywords: ["AI agents", "research", "consensus", "multi-agent", "LLM"],
  openGraph: {
    title: "Assembly — AI Research Platform",
    description: "Multi-agent AI research that produces measurably better answers.",
    type: "website",
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
