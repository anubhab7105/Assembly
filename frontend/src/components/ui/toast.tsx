"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

/* ─── Variants ────────────────────────────────────────────────────────────── */
const toastVariants = cva(
  [
    "pointer-events-auto relative flex w-full max-w-[1080px] items-center justify-between gap-4 rounded-xl border p-4 shadow-2xl backdrop-blur-md",
    "animate-toast-in",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "border-border bg-card/95 text-foreground",
        success: "border-emerald-500/40 bg-emerald-950/90 text-emerald-200 dark:bg-emerald-950/90 dark:text-emerald-200",
        warning: "border-amber-500/40 bg-[#1e190e]/95 text-amber-300 dark:bg-[#1e190e]/95 dark:text-amber-200",
        danger: "border-red-500/50 bg-[#1a0c0e]/95 text-red-500 dark:bg-[#1a0c0e]/95 dark:text-red-400",
        info: "border-sky-500/40 bg-sky-950/90 text-sky-200 dark:bg-sky-950/90 dark:text-sky-200",
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
      className="ml-auto flex-none rounded-none p-0.5 opacity-60 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
      <div className="flex-1 min-w-0 pr-2">
        <p className="text-sm font-semibold">{title}</p>
        {description && <p className="text-xs sm:text-sm opacity-90 mt-0.5 leading-snug">{description}</p>}
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
      {/* Toast stack — full-width bottom matching main content / cards */}
      <div
        aria-label="Notifications"
        className="fixed bottom-5 left-0 md:left-[264px] right-0 z-50 flex flex-col items-center pointer-events-none px-4 sm:px-7 gap-2.5"
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
