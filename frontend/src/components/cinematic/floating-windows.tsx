"use client"

import type { RefObject } from "react"
import { GalaxyField } from "@/components/landing/galaxy-field"
import { TrafficDots } from "./window-card"

function WindowShell({
  title,
  children,
  className,
}: {
  title: string
  children: React.ReactNode
  className: string
}) {
  return (
    <div className={`cin-window cin-float-window ${className}`}>
      <div className="cin-window-bar">
        <TrafficDots />
        <span className="cin-window-title">{title}</span>
      </div>
      <div className="cin-window-body">{children}</div>
    </div>
  )
}

export function FloatingWindows({ heroRef }: { heroRef?: RefObject<HTMLElement | null> }) {
  return (
    <div className="cin-hero-stage" aria-hidden="true">
      <GalaxyField heroRef={heroRef} className="cin-hero-field" />

      <div className="cin-orbit-art">
        <span className="cin-ring" />
        <span className="cin-ring" />
        <span className="cin-ring" />
        <span className="cin-orbit-node" />
        <span className="cin-orbit-node is-violet" />
        <span className="cin-orbit-node is-mint" />
      </div>

      <div className="cin-hero-cards">
        <WindowShell title="Live run" className="is-live">
          <p className="cin-live-title">Skeptic is reviewing…</p>
          <div className="cin-progress">
            <i style={{ width: "72%" }} />
          </div>
          <div className="cin-progress-meta">
            <span>3:12 left</span>
            <span>step 2 of 4</span>
          </div>
        </WindowShell>

        <WindowShell title="Agreement" className="is-agreement">
          <div className="cin-agreement-value">
            <strong>72%</strong>
            <span>
              agents
              <br />
              agree
            </span>
          </div>
        </WindowShell>

        <WindowShell title="Answer" className="is-answer">
          <p className="cin-answer-window-text">
            Wait. One region with read replicas is cheaper and simpler.
          </p>
        </WindowShell>
      </div>
    </div>
  )
}
