"use client"

import React from "react"
import Link from "next/link"
import { ArrowUpRight } from "lucide-react"
import { BrandOrbMark } from "@/components/brand-orb-mark"
import { LandingFooter } from "@/components/landing-footer"

interface LegalPageLayoutProps {
  title: string
  children: React.ReactNode
  currentPath?: string
  index?: string
  lastUpdated?: string
  contactEmail?: string
}

export function LegalPageLayout({
  title,
  children,
}: LegalPageLayoutProps) {
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Top Site Header */}
      <header className="border-b border-border/40 bg-background/90 backdrop-blur-md sticky top-0 z-30 w-full">
        <div className="w-full flex h-16 sm:h-20 items-center justify-between px-6 sm:px-10 lg:px-12">
          <Link href="/" className="assembly-wordmark flex items-center" aria-label="Assembly Home">
            <BrandOrbMark className="assembly-wordmark-mark--header" />
            <span>ssembly</span>
          </Link>

          <nav className="flex items-center gap-6 sm:gap-8 text-sm" aria-label="Legal header navigation">
            <Link
              href="/"
              className="text-muted-foreground hover:text-foreground transition-colors font-medium text-sm"
            >
              Home
            </Link>
            <Link
              href="/science"
              className="text-muted-foreground hover:text-foreground transition-colors font-medium text-sm"
            >
              Idea
            </Link>
            <Link
              href="/chat"
              className="inline-flex items-center gap-1.5 rounded-full bg-brand px-4 py-2 text-xs font-semibold text-brand-foreground shadow-sm hover:opacity-90 transition-opacity"
            >
              <span>Start an investigation</span>
              <ArrowUpRight className="size-3.5" />
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content Stage */}
      <main id="main-content" tabIndex={-1} className="flex-1 w-full max-w-6xl mx-auto px-6 sm:px-10 lg:px-16 py-12 sm:py-16">
        <h1
          className="text-4xl sm:text-6xl lg:text-7xl font-semibold tracking-tight italic"
          style={{
            fontFamily: 'Georgia, "Times New Roman", serif',
            color: 'var(--brand, #eaa221)',
          }}
        >
          {title}
        </h1>

        {/* Full-width elegant dividing rule */}
        <hr className="border-t border-border/50 my-8 sm:my-10" />

        {/* Spacious Content Body */}
        <div className="w-full space-y-12 sm:space-y-14 text-left leading-relaxed">
          {children}
        </div>
      </main>

      {/* Global Landing Footer (Trust & Legal links live exclusively here) */}
      <LandingFooter />
    </div>
  )
}
