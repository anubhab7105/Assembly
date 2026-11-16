"use client"

import React from "react"
import { LandingHeader } from "@/components/landing-header"
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
    <div className="min-h-screen bg-background text-foreground flex flex-col pt-20">
      {/* Top Site Header - Complete Landing Header */}
      <LandingHeader />

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
