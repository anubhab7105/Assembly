"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

/* ─── Variants ────────────────────────────────────────────────────────────── */
const toastVariants = cva(
  [
    "relative flex w-[360px] max-w-[90vw] items-start gap-3 rounded-xl border p-4 shadow-lg",
    "animate-toast-in",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "border-border bg-card text-foreground",
        success: "border-success/30 bg-success-subtle text-success",
        warning: "border-warning/30 bg-warning-subtle text-warning",
        danger: "border-danger/30 bg-danger-subtle text-danger",
        info: "border-info/30 bg-info-subtle text-info",
      },
    },
    defaultVariants: { variant: "default" },
  }
)

/* ─── Types ───────────────────────────────────────────────────────────────── */
export interface ToastProps extends VariantProps<typeof toastVariants> {
  title: string
  description?: string
  duration?: number
  onDismiss?: () => void
  className?: string
}

/* ─── Dismiss button ─────────────────────────────────────────────────────── */
function DismissButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label="Dismiss notification"
      className="ml-auto flex-none rounded-md p-0.5 opacity-60 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <X className="size-4" />
    </button>
  )
}

/* ─── Single Toast ────────────────────────────────────────────────────────── */
export function Toast({
  title,
  description,
  variant = "default",
  duration = 4000,
  onDismiss,
  className,
}: ToastProps) {
  const [exiting, setExiting] = React.useState(false)
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const dismiss = React.useCallback(() => {
    setExiting(true)
    setTimeout(() => onDismiss?.(), 220)
  }, [onDismiss])

  const startTimer = React.useCallback(() => {
    timerRef.current = setTimeout(dismiss, duration)
  }, [dismiss, duration])

  const clearTimer = React.useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  React.useEffect(() => {
    startTimer()
    return clearTimer
  }, [startTimer, clearTimer])

  return (
    <div
      role="alert"
      aria-live="polite"
      onMouseEnter={clearTimer}
      onMouseLeave={startTimer}
      className={cn(toastVariants({ variant }), exiting && "animate-toast-out", className)}
    >
      <div className="flex-1 space-y-0.5">
        <p className="text-sm font-semibold leading-none">{title}</p>
        {description && <p className="text-sm opacity-80">{description}</p>}
      </div>
      <DismissButton onClick={dismiss} />
    </div>
  )
}

/* ─── Context & Provider ──────────────────────────────────────────────────── */
interface ToastItem extends ToastProps {
  id: string
}

interface ToastContextValue {
  toast: (props: Omit<ToastProps, "onDismiss">) => void
}

const ToastContext = React.createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([])

  const addToast = React.useCallback((props: Omit<ToastProps, "onDismiss">) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((prev) => [...prev, { ...props, id }])
  }, [])

  const removeToast = React.useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      {/* Toast stack — bottom-right */}
      <div
        aria-label="Notifications"
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      >
        {toasts.map((t) => (
          <Toast key={t.id} {...t} onDismiss={() => removeToast(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext)
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>")
  return ctx
}
