"use client"

import React, { Suspense, useEffect, useState, useSyncExternalStore } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { ToastProvider } from "@/components/ui/toast"
import { storage, type HistoryRecord } from "@/lib/storage"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { BrandMark } from "@/components/cinematic/brand-mark"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  History,
  Menu,
  Plus,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  SquarePen,
  WifiOff,
  X,
  type LucideIcon,
} from "lucide-react"

function subscribeOnlineStatus(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => {}
  window.addEventListener("online", onStoreChange)
  window.addEventListener("offline", onStoreChange)
  return () => {
    window.removeEventListener("online", onStoreChange)
    window.removeEventListener("offline", onStoreChange)
  }
}

function getOnlineStatusSnapshot() {
  return typeof navigator === "undefined" ? true : navigator.onLine
}

function getOnlineStatusServerSnapshot() {
  return true
}

function useOfflineStatus() {
  return !useSyncExternalStore(
    subscribeOnlineStatus,
    getOnlineStatusSnapshot,
    getOnlineStatusServerSnapshot,
  )
}

const NAV_ITEMS: Array<{ href: string; label: string; icon: LucideIcon }> = [
  { href: "/chat", label: "Workspace", icon: SquarePen },
  { href: "/history", label: "History", icon: History },
  { href: "/models", label: "Models", icon: SlidersHorizontal },
  { href: "/settings", label: "Settings", icon: Settings },
]

const DOCS_URL = "https://github.com/arkap1502/Assembly#readme"

function pageMeta(pathname: string): { number: string; label: string } {
  if (pathname.startsWith("/chat")) return { number: "01", label: "Workspace" }
  if (pathname.startsWith("/executions")) return { number: "02", label: "Live run" }
  if (pathname.startsWith("/history")) return { number: "06", label: "History" }
  if (pathname.startsWith("/models")) return { number: "07", label: "Models" }
  if (pathname.startsWith("/settings")) return { number: "08", label: "Settings" }
  if (pathname.startsWith("/styleguide")) return { number: "—", label: "Design system" }
  return { number: "08", label: "Assembly" }
}

function isNavActive(pathname: string, href: string) {
  if (href === "/chat") return pathname === "/chat" || pathname.startsWith("/executions")
  return pathname === href || pathname.startsWith(`${href}/`)
}

function MobileMenu({
  open,
  setOpen,
  closeButtonRef,
  pathname,
}: {
  open: boolean
  setOpen: (open: boolean) => void
  closeButtonRef: React.RefObject<HTMLButtonElement | null>
  pathname: string
}) {
  const router = useRouter()
  const [records, setRecords] = useState<HistoryRecord[]>([])

  useEffect(() => {
    if (!open) return
    let active = true
    storage
      .listHistory()
      .then((items) => {
        if (active) setRecords(items.slice(0, 4))
      })
      .catch(() => {
        if (active) setRecords([])
      })
    return () => {
      active = false
    }
  }, [open])

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        showCloseButton={false}
        aria-modal="true"
        aria-describedby="mobile-menu-description"
        className="fixed inset-y-0 left-0 right-auto top-0 h-dvh w-4/5 max-w-sm translate-x-0 translate-y-0 overflow-y-auto rounded-none border-0 border-r border-border bg-card p-0 sm:max-w-sm"
      >
        <DialogTitle className="sr-only">Navigation menu</DialogTitle>
        <DialogDescription id="mobile-menu-description" className="sr-only">
          Navigate between Assembly pages and manage your investigation history.
        </DialogDescription>
        <div id="mobile-menu" className="relative flex min-h-full flex-col p-5 pt-6">
          <button
            ref={closeButtonRef}
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close menu"
            className="absolute right-3 top-3 z-10 flex min-h-11 min-w-11 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="size-5" />
          </button>

          <Link href="/" className="cin-brand mb-6" onClick={() => setOpen(false)}>
            <BrandMark />
            <span className="cin-brand-word">Assembly</span>
          </Link>

          <button
            type="button"
            className="cin-btn cin-btn-primary mb-5 w-full"
            onClick={() => {
              router.push("/chat")
              setOpen(false)
            }}
          >
            <Plus className="size-4" aria-hidden />
            New Investigation
          </button>

          <nav aria-label="Workspace" className="grid gap-1">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                data-active={isNavActive(pathname, item.href)}
                className="flex min-h-12 items-center gap-3 rounded-xl px-3 text-sm font-semibold text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <item.icon className="size-4" aria-hidden />
                {item.label}
              </Link>
            ))}
            <a
              href={DOCS_URL}
              target="_blank"
              rel="noreferrer"
              onClick={() => setOpen(false)}
              className="flex min-h-12 items-center gap-3 rounded-xl px-3 text-sm font-semibold text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <BookOpen className="size-4" aria-hidden />
              Docs
            </a>
          </nav>

          <div className="mt-6 border-t border-border pt-5">
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-muted-foreground">History (this device)</span>
              <ThemeToggle className="cin-icon-button" />
            </div>
            {records.length === 0 ? (
              <p className="text-xs leading-relaxed text-muted-foreground">
                No runs saved on this device yet.
              </p>
            ) : (
              <div className="grid gap-1">
                {records.map((record) => (
                  <Link
                    key={record.id}
                    href={`/executions?id=${record.id}`}
                    onClick={() => setOpen(false)}
                    className="flex min-h-11 items-center gap-2 rounded-lg px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    <span className="size-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
                    <span className="truncate">{record.question}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>

          <div className="mt-auto pt-6">
            <Link
              href="/chat"
              onClick={() => setOpen(false)}
              className="cin-btn cin-btn-outline w-full"
            >
              Open workspace
              <ArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function AppSidebar({ pathname }: { pathname: string }) {
  const router = useRouter()

  return (
    <aside className="cin-sidebar">
      <div className="cin-sidebar-head">
        <Link href="/" className="cin-brand cin-sidebar-brand" aria-label="Assembly home">
          <BrandMark />
          <span className="cin-brand-word">Assembly</span>
        </Link>

        <button
          type="button"
          className="cin-btn cin-btn-primary cin-sidebar-new"
          onClick={() => router.push("/chat")}
        >
          <Plus className="size-4" aria-hidden />
          New Investigation
        </button>
      </div>

      <nav className="cin-sidebar-nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => {
          const active = isNavActive(pathname, item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              className="cin-side-link"
              data-active={active}
              aria-current={active ? "page" : undefined}
            >
              <item.icon className="cin-side-link-icon" aria-hidden />
              <span>{item.label}</span>
            </Link>
          )
        })}
        <a href={DOCS_URL} target="_blank" rel="noreferrer" className="cin-side-link">
          <BookOpen className="cin-side-link-icon" aria-hidden />
          <span>Docs</span>
          <ArrowUpRight className="cin-side-link-trailing" aria-hidden />
        </a>
      </nav>

      <div className="cin-sidebar-footer">
        <p className="cin-sidebar-note">
          <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
          Keys stay on this device
        </p>
        <div className="cin-sidebar-footer-row">
          <span>Appearance</span>
          <ThemeToggle className="cin-icon-button" />
        </div>
      </div>
    </aside>
  )
}

function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/"
  const router = useRouter()
  const isOffline = useOfflineStatus()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const menuTriggerRef = React.useRef<HTMLButtonElement>(null)
  const menuCloseRef = React.useRef<HTMLButtonElement>(null)
  const wasMenuOpen = React.useRef(false)
  const meta = pageMeta(pathname)

  useEffect(() => {
    if (mobileMenuOpen) {
      wasMenuOpen.current = true
      menuCloseRef.current?.focus()
      return
    }
    if (wasMenuOpen.current) {
      wasMenuOpen.current = false
      menuTriggerRef.current?.focus()
    }
  }, [mobileMenuOpen])

  return (
    <>
      <div className="cin-app-shell">
        <AppSidebar pathname={pathname} />

        <div className="cin-app-column">
          <header className="cin-topbar is-floating">
            <Link href="/" className="cin-brand cin-topbar-brand" aria-label="Assembly home">
              <BrandMark />
              <span className="cin-brand-word">Assembly</span>
            </Link>

            <span className="cin-topbar-meta hidden lg:inline">{meta.label}</span>

            <div className="cin-topbar-actions">
              <span className="cin-topbar-count">
                {meta.number} / 08
              </span>
              <button
                type="button"
                className="cin-btn cin-btn-sm cin-btn-primary cin-topbar-new hidden sm:inline-flex"
                onClick={() => router.push("/chat")}
              >
                <Plus className="size-4" aria-hidden />
                New Investigation
              </button>
              <ThemeToggle className="cin-icon-button cin-topbar-theme" />
              <button
                ref={menuTriggerRef}
                type="button"
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open menu"
                aria-expanded={mobileMenuOpen}
                aria-controls={mobileMenuOpen ? "mobile-menu" : undefined}
                className="cin-icon-button cin-menu-trigger md:hidden"
              >
                <Menu className="size-5" aria-hidden />
              </button>
            </div>
          </header>

          {isOffline && (
            <div className="mx-auto mt-3 flex w-[min(1240px,calc(100%-32px))] items-center justify-center gap-2 rounded-xl border border-danger/30 bg-danger/10 px-4 py-2 text-center text-sm font-medium text-danger">
              <WifiOff className="size-4" aria-hidden />
              You are currently offline. Some features may not work.
            </div>
          )}

          <div className="cin-app-body flex-1">{children}</div>
        </div>
      </div>

      <nav className="cin-bottom-nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="cin-nav-link"
            data-active={isNavActive(pathname, item.href)}
            aria-current={isNavActive(pathname, item.href) ? "page" : undefined}
          >
            {item.label}
          </Link>
        ))}
        <a href={DOCS_URL} target="_blank" rel="noreferrer" className="cin-nav-link">
          Docs
        </a>
      </nav>

      <Suspense fallback={null}>
        <MobileMenu
          open={mobileMenuOpen}
          setOpen={setMobileMenuOpen}
          closeButtonRef={menuCloseRef}
          pathname={pathname}
        />
      </Suspense>
    </>
  )
}

export function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/"
  const isLandingPage = pathname === "/"

  return (
    <ToastProvider>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-100 focus:rounded-lg focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-foreground"
      >
        Skip to content
      </a>
      <div className="cin-app">
        {isLandingPage ? children : <AppChrome>{children}</AppChrome>}
      </div>
    </ToastProvider>
  )
}
