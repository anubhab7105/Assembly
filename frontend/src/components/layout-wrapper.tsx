"use client"

import React, { Suspense, useEffect, useState, useSyncExternalStore } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { ToastProvider } from "@/components/ui/toast"
import { storage, type HistoryRecord } from "@/lib/storage"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { importHistoryFile } from "@/lib/history-import"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { BrandMark } from "@/components/cinematic/brand-mark"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  ArrowRight,
  Download,
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

const OFFLINE_MESSAGE = "You are currently offline. Some features may not work."

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
  { href: "/models", label: "Models", icon: SlidersHorizontal },
  { href: "/settings", label: "Settings", icon: Settings },
]

function pageMeta(pathname: string): { number: string; label: string } {
  if (pathname.startsWith("/chat")) return { number: "01", label: "Workspace" }
  if (pathname.startsWith("/executions")) return { number: "02", label: "Live run" }
  if (pathname.startsWith("/history")) return { number: "06", label: "History" }
  if (pathname.startsWith("/models")) return { number: "07", label: "Models" }
  if (pathname.startsWith("/settings")) return { number: "08", label: "Settings" }
  if (pathname.startsWith("/references")) return { number: "09", label: "Research" }
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
  const [records, setRecords] = useState<HistoryRecord[]>([])

  // Same export the history page offers: one JSON file with runs and usage.
  const handleExport = async () => {
    try {
      const text = await storage.exportJSON()
      const blob = new Blob([text], { type: "application/json" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "assembly-history.json"
      a.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Couldn't export history. Please try again."

      toast({
        title: "History export failed",
        description: message,
        variant: "danger",
        duration: 7000,
      })
    }
  }

const handleImport = async (file: File, input: HTMLInputElement) => {
  if (importing) return

  setImporting(true)

  try {
    await importHistoryFile(file, (text) => storage.importJSON(text))

    await loadExecutions()

    toast({
      title: "Import complete",
      description: "History and usage were imported successfully.",
      variant: "success",
    })
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Couldn't import this file. Check that it is a valid Assembly history export and try again."

    toast({
      title: "History import failed",
      description: message,
      variant: "danger",
      duration: 7000,
    })
  } finally {
    input.value = ""
    setImporting(false)
  }
}

  const filtered = executions.filter((e) =>
    e.question.toLowerCase().includes(search.toLowerCase()),
  )
    const text = await storage.exportJSON()
    const blob = new Blob([text], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = "assembly-history.json"
    anchor.click()
    URL.revokeObjectURL(url)
  }

  useEffect(() => {
    let active = true
    const load = () => {
      storage
        .listHistory()
        .then((items) => {
          if (active) setRecords(items.slice(0, 12))
        })
        .catch(() => {
          if (active) setRecords([])
        })
    }
    load()
    window.addEventListener("focus", load)
    return () => {
      active = false
      window.removeEventListener("focus", load)
    }
  }, [pathname])

  return (
    <aside className="mn-sidebar">
      <div className="mn-sidebar-top">
        <Link href="/" className="mn-brand" aria-label="Assembly home">
          <BrandMark />
          <span>Assembly</span>
        </Link>

        <button type="button" className="mn-new-chat" onClick={() => router.push("/chat")}>
          <SquarePen className="size-4" aria-hidden />
          New chat
        </button>
      </div>

      <nav className="mn-nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => {
          const active = isNavActive(pathname, item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              className="mn-nav-link"
              data-active={active}
              aria-current={active ? "page" : undefined}
            >
              <item.icon aria-hidden />
              <span>{item.label}</span>
            </Link>
          )
        })}
      </nav>

      <div className="mn-recents">
        <span className="mn-recents-label">Recents</span>
        {records.length === 0 ? (
          <p className="mn-recents-empty">Your runs will show up here.</p>
        ) : (
          records.map((record) => (
            <Link
              key={record.id}
              href={`/executions?id=${record.id}`}
              className="mn-recent"
              title={record.question}
            >
              <span className="mn-recent-title">{record.question}</span>
            </Link>
          ))
        )}
      </div>

      <div className="mn-sidebar-foot">
        <button type="button" className="mn-nav-link" onClick={() => void handleExport()}>
          <Download aria-hidden />
          <span>Export</span>
        </button>
        <p className="mn-key-note">
          <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
          Keys stay on this device
        </p>
        <div className="mn-foot-row">
          <span>Appearance</span>
          <ThemeToggle className="cin-icon-button" />
        </div>
      </div>
    </aside>
  )
}

function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/"
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
  // The references page is a standalone document with its own top bar, so it
  // renders outside the workspace chrome instead of inside the app sidebar.
  const isStandalonePage = isLandingPage || pathname.startsWith("/references")
  // Connectivity is announced on every page, including the standalone ones
  // that render outside the workspace chrome.
  const isOffline = useOfflineStatus()

  return (
    <ToastProvider>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-100 focus:rounded-lg focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-foreground"
      >
        Skip to content
      </a>
      {/* Polite live region: empty online, announced when connectivity changes. */}
      <div role="status" aria-live="polite" className="sr-only">
        {isOffline ? OFFLINE_MESSAGE : ""}
      </div>

      {isOffline && (
        <div
          data-testid="offline-banner"
          className="fixed inset-x-0 top-0 z-100 flex items-center justify-center gap-2 border-b border-danger/30 bg-danger/10 px-4 py-2 text-center text-sm font-medium text-danger backdrop-blur"
        >
          <WifiOff className="size-4" aria-hidden />
          {OFFLINE_MESSAGE}
        </div>
      )}

      <div className="cin-app">
        {isStandalonePage ? children : <AppChrome>{children}</AppChrome>}
      </div>
    </ToastProvider>
  )
}
