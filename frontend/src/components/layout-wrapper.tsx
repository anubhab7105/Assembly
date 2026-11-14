"use client"

import React, { useState, useEffect, useSyncExternalStore, Suspense } from "react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { ToastProvider, useToast } from "@/components/ui/toast"
import { storage, type HistoryRecord } from "@/lib/storage"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import {
  Settings, Menu, X, WifiOff, Plus, History, Trash2, Search, MessageSquare, Download, Upload, ChevronDown,
} from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"
import { BrandOrbMark } from "@/components/brand-orb-mark"

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

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const router = useRouter()
  const { toast } = useToast()

  const [executions, setExecutions] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [showHistory, setShowHistory] = useState(pathname === "/executions")
  const importInputRef = React.useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)

  const loadExecutions = async () => {
    setLoading(true)
    try {
      setExecutions(await storage.listHistory())
    } catch (e) {
      if (process.env.NODE_ENV !== "production") console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    storage
      .listHistory()
      .then((items) => {
        if (!cancelled) setExecutions(items)
      })
      .catch((error: unknown) => {
        if (!cancelled && process.env.NODE_ENV !== "production") console.error(error)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [pathname])

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    e.preventDefault()
    if (!confirm("Delete this execution?")) return
    await storage.deleteHistory(id)
    setExecutions((prev) => prev.filter((x) => x.id !== id))
    toast({ title: "Deleted", description: "Execution removed from history." })
    if (pathname === `/executions` && searchParams?.get("id") === id) {
      router.push("/chat")
      if (onClose) onClose()
    }
  }

  const handleExport = async () => {
    const text = await storage.exportJSON()
    const blob = new Blob([text], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "assembly-history.json"
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImport = async (file: File, input: HTMLInputElement) => {
    if (importing) return
    setImporting(true)
    try {
      const text = await file.text()
      await storage.importJSON(text)
      await loadExecutions()
      toast({ title: "Import complete", description: "History and usage were imported successfully.", variant: "success" })
    } catch (error) {
      const message = error instanceof Error
        ? error.message
        : "Couldn't import this file. Check that it is a valid Assembly history export and try again."
      toast({
        title: "History import failed",
        description: message,
        variant: "danger",
        duration: 7000,
      })
    } finally {
      // File inputs do not fire change again when the same file is selected.
      // Clearing it on both success and failure allows an immediate retry.
      input.value = ""
      setImporting(false)
    }
  }

  const filtered = executions.filter((e) =>
    e.question.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="assembly-sidebar flex h-full flex-col">
      <div className="assembly-sidebar-header">
        <Link
          href="/"
          className="assembly-sidebar-brand assembly-wordmark flex items-center text-white cursor-pointer"
          onClick={() => {
            if (onClose) onClose()
            if (typeof document !== "undefined") {
              const scrollContainers = document.querySelectorAll(".overflow-y-auto")
              scrollContainers.forEach((el) => {
                el.scrollTo({ top: 0, behavior: "instant" })
              })
              window.scrollTo({ top: 0, behavior: "instant" })
            }
          }}
          aria-label="Assembly home"
        >
          <BrandOrbMark className="assembly-wordmark-mark--sidebar" style={{ width: "32px", height: "32px" }} />
          <span>ssembly</span>
        </Link>
        <Button variant="default" className="assembly-new-investigation w-full justify-start" onClick={() => { router.push("/chat"); if (onClose) onClose() }}>
          <Plus className="size-4 mr-2" />
          New chat
        </Button>
      </div>

      <div className="assembly-sidebar-scroll flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-2">
        <div className="px-1">
          <Button
            variant="default"
            className="assembly-new-investigation w-full justify-between flex items-center"
            onClick={() => setShowHistory((prev) => !prev)}
            aria-expanded={showHistory}
          >
            <div className="flex items-center">
              <History className="size-4 mr-2 opacity-85" />
              <span>History</span>
              {executions.length > 0 && (
                <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-white/80 font-normal">
                  {executions.length}
                </span>
              )}
            </div>
            <ChevronDown className={`size-3.5 text-muted-foreground transition-transform duration-200 ${showHistory ? "rotate-180" : ""}`} />
          </Button>
        </div>

        {showHistory && (
          <div className="flex flex-col gap-2 pt-1">
            {executions.length > 0 && (
              <div className="px-1">
                <div className="relative">
                  <Search className="size-3.5 absolute left-2.5 top-2.5 text-muted-foreground" aria-hidden />
                  <label htmlFor="history-search" className="sr-only">Search history</label>
                  <input
                    id="history-search"
                    type="text"
                    placeholder="Search investigations"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="assembly-sidebar-search w-full rounded-md border border-border bg-muted/30 pl-8 pr-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-brand"
                  />
                </div>
              </div>
            )}

            {loading ? (
              <div className="space-y-2 px-1">
                <Skeleton className="h-10 w-full rounded-full" />
                <Skeleton className="h-10 w-full rounded-full" />
              </div>
            ) : filtered.length === 0 ? (
              <p className="px-3 py-2 text-xs text-muted-foreground">
                {search ? "No matching runs" : "No saved investigations"}
              </p>
            ) : (
              filtered.map((ex) => {
                const isActive = pathname === `/executions` && searchParams?.get("id") === ex.id
                return (
                  <div key={ex.id} className="relative group px-1">
                    <Link
                      href={`/executions?id=${ex.id}`}
                      prefetch={false}
                      onClick={onClose}
                      className={`assembly-new-investigation w-full justify-start flex items-center px-4 pr-10 ${
                        isActive ? "border-brand/60 bg-brand/10 text-brand" : ""
                      }`}
                    >
                      <MessageSquare className="size-4 mr-2 shrink-0 opacity-80" />
                      <span className="truncate text-xs font-semibold text-white/95">{ex.question}</span>
                    </Link>
                    <button
                      type="button"
                      onClick={(e) => handleDelete(e, ex.id)}
                      aria-label={`Delete run: ${ex.question.slice(0, 60)}`}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground hover:text-danger hover:bg-white/10 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                      title="Delete execution"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                )
              })
            )}
          </div>
        )}
      </div>

      <div className="assembly-sidebar-footer p-3 border-t border-border mt-auto">
        <div className="assembly-sidebar-preferences flex items-center justify-between gap-1.5">
          <div className="flex items-center gap-1.5">
            <Link
              href="/settings"
              onClick={onClose}
              aria-label="Settings"
              title="Settings"
              className="assembly-sidebar-icon-btn"
            >
              <Settings className="size-4" />
            </Link>
            <button
              type="button"
              aria-label="Export history"
              title="Export history"
              onClick={handleExport}
              className="assembly-sidebar-icon-btn"
            >
              <Download className="size-4" />
            </button>
            <button
              type="button"
              aria-label="Import history"
              title={importing ? "Importing…" : "Import history"}
              disabled={importing}
              onClick={() => importInputRef.current?.click()}
              className="assembly-sidebar-icon-btn disabled:opacity-50"
            >
              <Upload className="size-4" />
            </button>
          </div>
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
          <ThemeToggle className="assembly-theme-toggle" />
        </div>
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

  // Public marketing/editorial pages render their own nav; hide the app sidebar there.
  const isLandingPage = pathname === "/" || pathname === "/science"

  // Enforce dark theme permanently on landing/editorial pages (/, /science).
  // Day/night theme preference applies exclusively to the chat workspace and app shell.
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (isLandingPage) {
      document.documentElement.classList.add("dark");
    } else {
      try {
        const stored = window.localStorage.getItem("assembly:theme");
        if (stored === "light") {
          document.documentElement.classList.remove("dark");
        } else {
          document.documentElement.classList.add("dark");
        }
      } catch {
        document.documentElement.classList.add("dark");
      }
    }
  }, [pathname, isLandingPage]);

  useEffect(() => {
    if (pathname === "/") {
      if (typeof document !== "undefined") {
        const scrollContainers = document.querySelectorAll(".overflow-y-auto")
        scrollContainers.forEach((el) => {
          el.scrollTo({ top: 0, behavior: "instant" })
        })
        window.scrollTo({ top: 0, behavior: "instant" })
      }
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
        {!isLandingPage && (
          <aside className="assembly-sidebar-shell hidden md:block w-[264px] shrink-0 h-full relative z-20">
            <Suspense fallback={<div className="p-4">Loading menu...</div>}>
              <SidebarContent />
            </Suspense>
          </aside>
        )}

        <Dialog open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
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
                <SidebarContent onClose={() => setMobileMenuOpen(false)} />
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

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
          {!isLandingPage && (
            <header className="assembly-mobile-header md:hidden sticky top-0 z-30 flex items-center justify-between border-b border-border bg-card px-4 py-3">
              <Link
                href="/"
                className="assembly-wordmark flex items-center text-foreground"
                aria-label="Assembly home"
                onClick={() => {
                  if (typeof document !== "undefined") {
                    const scrollContainers = document.querySelectorAll(".overflow-y-auto")
                    scrollContainers.forEach((el) => {
                      el.scrollTo({ top: 0, behavior: "instant" })
                    })
                    window.scrollTo({ top: 0, behavior: "instant" })
                  }
                }}
              >
                <BrandOrbMark className="assembly-wordmark-mark--mobile" style={{ width: "28px", height: "28px" }} /><span>ssembly</span>
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

          <div className="flex-1 overflow-y-auto overflow-x-hidden relative">
            {children}
          </div>
        </div>
      </div>
    </ToastProvider>
  )
}
