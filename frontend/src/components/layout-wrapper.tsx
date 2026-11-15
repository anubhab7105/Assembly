"use client"
import { importHistoryFile } from "@/lib/history-import"
import React, { useState, useEffect, useSyncExternalStore, Suspense } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { ToastProvider, useToast } from "@/components/ui/toast"
import { storage, type HistoryRecord } from "@/lib/storage"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import {
  Settings,
  Menu,
  X,
  WifiOff,
  Trash2,
  Upload,
  Download,
  SquarePen,
  SlidersHorizontal,
  ShieldCheck,
  type LucideIcon,
  Zap,
} from "lucide-react"
import { ThemeToggle, getThemeSnapshot } from "@/components/theme-toggle"
import { BrandOrbMark } from "@/components/brand-orb-mark"

const OFFLINE_MESSAGE = "You are currently offline. Some features may not work."

function subscribeOnlineStatus(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => { }
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

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const pathname = usePathname()
  const router = useRouter()
  const { toast } = useToast()

  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [search, setSearch] = useState("")
  const importInputRef = React.useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)

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
    window.addEventListener("assembly:history-change", load)

    return () => {
      active = false
      window.removeEventListener("focus", load)
      window.removeEventListener("assembly:history-change", load)
    }
  }, [pathname])

  const handleExport = async () => {
    try {
      const text = await storage.exportJSON()
      const blob = new Blob([text], { type: "application/json" })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")

      anchor.href = url
      anchor.download = "assembly-history.json"
      anchor.click()

      URL.revokeObjectURL(url)
    } catch (error) {
      toast({
        title: "History export failed",
        description:
          error instanceof Error
            ? error.message
            : "Couldn't export history. Please try again.",
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

      const items = await storage.listHistory()
      setRecords(items.slice(0, 12))

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

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.preventDefault()
    e.stopPropagation()

    if (!confirm("Delete this execution?")) return

    await storage.deleteHistory(id)

    setRecords((previous) => previous.filter((record) => record.id !== id))

    window.dispatchEvent(new CustomEvent("assembly:history-change"))

    toast({
      title: "Deleted",
      description: "Execution removed from history.",
    })

    const currentSearch = new URLSearchParams(window.location.search)

    if (
      window.location.pathname === "/executions" &&
      currentSearch.get("id") === id
    ) {
      router.push("/chat")
      onClose?.()
    }
  }

  const filteredRecords = records.filter((record) =>
    record.question.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <aside className="mn-sidebar">
      <div className="mn-sidebar-top">
        <Link
          href="/"
          className="mn-brand"
          aria-label="Assembly home"
          onClick={onClose}
        >
          <BrandOrbMark />
          <span>Assembly</span>
        </Link>

        <button
          type="button"
          className="mn-new-chat"
          onClick={() => {
            router.push("/chat")
            onClose?.()
          }}
        >
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
              onClick={onClose}
            >
              <item.icon aria-hidden />
              <span>{item.label}</span>
            </Link>
          )
        })}
      </nav>

      <div className="mn-recents">
        <span className="mn-recents-label">Recents</span>

        <div className="px-3 py-2">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search history..."
            aria-label="Search execution history"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </div>

        {filteredRecords.length === 0 ? (
          <p className="mn-recents-empty">
            Your runs will show up here.
          </p>
        ) : (
          filteredRecords.map((record) => (
            <div key={record.id} className="group relative">
              <Link
                href={`/executions?id=${record.id}`}
                className="mn-recent"
                title={record.question}
                onClick={onClose}
              >
                <span className="mn-recent-title">{record.question}</span>
              </Link>

              <button
                type="button"
                aria-label={`Delete ${record.question}`}
                onClick={(e) => void handleDelete(e, record.id)}
                className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 focus:opacity-100"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))
        )}
      </div>

      <div className="mn-sidebar-foot">
        <button
          type="button"
          className="mn-nav-link"
          onClick={() => void handleExport()}
        >
          <Download aria-hidden />
          <span>Export</span>
        </button>

        <button
          type="button"
          className="mn-nav-link"
          disabled={importing}
          onClick={() => importInputRef.current?.click()}
        >
          <Upload aria-hidden />
          <span>{importing ? "Importing..." : "Import"}</span>
        </button>

        <input
          ref={importInputRef}
          type="file"
          accept="application/json,.json"
          aria-label="Import Assembly history JSON"
          className="hidden"
          onChange={(e) => {
            const input = e.currentTarget
            const file = input.files?.[0]
            if (file) void handleImport(file, input)
          }}
        />

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

function isNavActive(pathname: string, href: string) {
  if (href === "/chat") return pathname === "/chat" || pathname.startsWith("/executions")
  return pathname === href || pathname.startsWith(`${href}/`)
}



export function MobileMenu({
  open,
  onOpenChange,
  menuCloseRef,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  menuCloseRef: React.RefObject<HTMLButtonElement | null>
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        aria-modal="true"
        aria-describedby="mobile-menu-description"
        className="fixed inset-y-0 left-0 right-auto top-0 h-dvh w-4/5 max-w-sm translate-x-0 translate-y-0 rounded-none border-r border-border bg-card p-0 sm:max-w-sm"
      >
        <DialogTitle className="sr-only">Navigation menu</DialogTitle>
        <DialogDescription id="mobile-menu-description" className="sr-only">
          Navigate between Assembly pages and manage your investigation history.
        </DialogDescription>
        <div id="mobile-menu" className="relative h-full min-h-0">
          <Suspense fallback={<div className="p-4">Loading menu...</div>}>
            <SidebarContent onClose={() => onOpenChange(false)} />
          </Suspense>
          <button
            ref={menuCloseRef}
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close menu"
            className="absolute right-3 top-3 z-10 flex min-h-11 min-w-11 items-center justify-center rounded-full bg-background/80 hover:bg-muted"
          >
            <X className="size-5" />
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function AppSidebar() {
  return (
    <aside className="assembly-sidebar-shell hidden md:block w-[264px] shrink-0 h-full relative z-20">
      <Suspense fallback={<div className="p-4">Loading menu...</div>}>
        <SidebarContent />
      </Suspense>
    </aside>
  )
}

export function AppChrome({
  children,
  isLandingPage,
  isOffline,
  mobileMenuOpen,
  onOpenMobileMenu,
  menuTriggerRef,
}: {
  children: React.ReactNode
  isLandingPage: boolean
  isOffline: boolean
  mobileMenuOpen: boolean
  onOpenMobileMenu: () => void
  menuTriggerRef: React.RefObject<HTMLButtonElement | null>
}) {
  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
      {!isLandingPage && (
        <header className="assembly-mobile-header md:hidden sticky top-0 z-30 flex items-center justify-between border-b border-border bg-card px-4 py-3">
          <div className="flex items-center gap-2">
            <Zap className="size-5 text-brand" />
            <span className="font-bold tracking-tight">assembly<span className="text-brand">.</span></span>
          </div>
          <button
            ref={menuTriggerRef}
            onClick={onOpenMobileMenu}
            aria-label="Open menu"
            aria-expanded={mobileMenuOpen}
            aria-controls={mobileMenuOpen ? "mobile-menu" : undefined}
            className="p-3 -mr-1 min-h-11 min-w-11 rounded hover:bg-muted"
          >
            <Menu className="size-6" />
          </button>
        </header>
      )}

      <div role="status" aria-live="polite" className="sr-only">
        {isOffline ? OFFLINE_MESSAGE : ""}
      </div>

      {isOffline && (
        <div
          data-testid="offline-banner"
          className="bg-danger/90 text-white px-4 py-1.5 text-center text-sm font-medium flex items-center justify-center gap-2"
        >
          <WifiOff className="size-4" />
          {OFFLINE_MESSAGE}
        </div>
      )}

      <div className="flex-1 overflow-y-auto overflow-x-hidden relative">
        {children}
      </div>
    </div>
  )
}

export function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const isOffline = useOfflineStatus()
  const pathname = usePathname()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const menuTriggerRef = React.useRef<HTMLButtonElement>(null)
  const menuCloseRef = React.useRef<HTMLButtonElement>(null)
  const wasMenuOpen = React.useRef(false)

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

  // Public marketing/editorial/legal pages render full-width.
  const isPublicPage =
    pathname === "/" ||
    pathname === "/science" ||
    pathname === "/privacy" ||
    pathname === "/terms" ||
    pathname === "/cookies" ||
    pathname === "/refunds" ||
    pathname === "/references"

  // Public pages always use dark theme.
  useEffect(() => {
    if (typeof document === "undefined") return

    if (isPublicPage) {
      document.documentElement.classList.add("dark")
    } else {
      const current = getThemeSnapshot()

      if (current === "light") {
        document.documentElement.classList.remove("dark")
      } else {
        document.documentElement.classList.add("dark")
      }
    }
  }, [pathname, isPublicPage])

  useEffect(() => {
    if (pathname === "/") {
      const scrollContainers = document.querySelectorAll(".overflow-y-auto")

      scrollContainers.forEach((el) => {
        el.scrollTo({ top: 0, behavior: "instant" })
      })

      window.scrollTo({ top: 0, behavior: "instant" })
    }
  }, [pathname])

  return (
    <ToastProvider>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-100 focus:rounded-lg focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-foreground"
      >
        Skip to content
      </a>

      <div className="assembly-app-shell flex h-screen overflow-hidden bg-background">
        {!isPublicPage && (
          <aside className="assembly-sidebar-shell hidden md:block w-[264px] shrink-0 h-full relative z-20">
            <Suspense fallback={<div className="p-4">Loading menu...</div>}>
              <SidebarContent />
            </Suspense>
          </aside>
        )}

        {mobileMenuOpen && (
          <Dialog open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
            <DialogContent
              showCloseButton={false}
              aria-modal="true"
              aria-describedby="mobile-menu-description"
              className="fixed inset-y-0 left-0 right-auto top-0 h-dvh w-4/5 max-w-sm translate-x-0 translate-y-0 rounded-none border-r border-border bg-card p-0 sm:max-w-sm"
            >
              <DialogTitle className="sr-only">
                Navigation menu
              </DialogTitle>

              <DialogDescription
                id="mobile-menu-description"
                className="sr-only"
              >
                Navigate between Assembly pages and manage your investigation history.
              </DialogDescription>

              <div id="mobile-menu" className="relative h-full min-h-0">
                <Suspense fallback={<div className="p-4">Loading menu...</div>}>
                  <SidebarContent
                    onClose={() => setMobileMenuOpen(false)}
                  />
                </Suspense>

                <button
                  ref={menuCloseRef}
                  type="button"
                  onClick={() => setMobileMenuOpen(false)}
                  aria-label="Close menu"
                  className="absolute right-3 top-3 z-10 flex min-h-11 min-w-11 items-center justify-center rounded-full bg-background/80 hover:bg-muted"
                >
                  <X className="size-5" />
                </button>
              </div>
            </DialogContent>
          </Dialog>
        )}

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
          {!isPublicPage && (
            <header className="assembly-mobile-header md:hidden sticky top-0 z-30 flex items-center justify-between border-b border-border bg-card px-4 py-3">
              <Link
                href="/"
                className="assembly-wordmark flex items-center text-foreground"
                aria-label="Assembly home"
                onClick={() => {
                  const scrollContainers =
                    document.querySelectorAll(".overflow-y-auto")

                  scrollContainers.forEach((el) => {
                    el.scrollTo({ top: 0, behavior: "instant" })
                  })

                  window.scrollTo({ top: 0, behavior: "instant" })
                }}
              >
                <BrandOrbMark
                  className="assembly-wordmark-mark--mobile"
                  style={{ width: "28px", height: "28px" }}
                />
                <span>ssembly</span>
              </Link>

              <button
                ref={menuTriggerRef}
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open menu"
                aria-expanded={mobileMenuOpen}
                aria-controls={mobileMenuOpen ? "mobile-menu" : undefined}
                className="p-3 -mr-1 min-h-11 min-w-11 rounded hover:bg-muted"
              >
                <Menu className="size-6" />
              </button>
            </header>
          )}

          <div role="status" aria-live="polite" className="sr-only">
            {isOffline ? OFFLINE_MESSAGE : ""}
          </div>

          {isOffline && (
            <div
              data-testid="offline-banner"
              className="bg-danger/90 text-white px-4 py-1.5 text-center text-sm font-medium flex items-center justify-center gap-2"
            >
              <WifiOff className="size-4" />
              {OFFLINE_MESSAGE}
            </div>
          )}

          <main
            id="main-content"
            className="flex-1 overflow-y-auto overflow-x-hidden relative"
          >
            {children}
          </main>
        </div>
      </div>
    </ToastProvider>
  )
}