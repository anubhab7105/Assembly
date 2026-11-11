import type { ReactNode } from "react"

export function TrafficDots() {
  return (
    <span className="cin-dots" aria-hidden="true">
      <span className="cin-dot" />
      <span className="cin-dot" />
      <span className="cin-dot" />
    </span>
  )
}

export function WindowCard({
  title,
  children,
  className = "",
  bodyClassName = "",
  meta,
}: {
  title: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  meta?: ReactNode
}) {
  return (
    <div className={`cin-window ${className}`}>
      <div className="cin-window-bar">
        <TrafficDots />
        <span className="cin-window-title">{title}</span>
        {meta ? <span className="ml-auto text-xs text-muted-foreground">{meta}</span> : null}
      </div>
      <div className={`cin-window-body ${bodyClassName}`}>{children}</div>
    </div>
  )
}
