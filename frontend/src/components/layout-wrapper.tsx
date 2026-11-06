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
  Zap, Settings, Menu, X, WifiOff, Plus, History, Trash2, Search, MessageSquare, Download, Upload,
  SquarePen, ArrowUpRight,
} from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"

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
        <Link href="/" className="assembly-sidebar-brand flex items-center gap-2.5" onClick={onClose}>
          <span className="asm-mark" aria-hidden="true">
            <i /><i /><i /><i />
          </span>
          <span>Assembly</span>
        </Link>
        <Button variant="default" className="assembly-new-investigation w-full justify-start" onClick={() => { router.push("/chat"); if (onClose) onClose() }}>
          <span className="flex items-center gap-2">
            <Plus className="size-4" />
            New Investigation
          </span>
          <ArrowUpRight className="size-3.5" aria-hidden />
        </Button>
      </div>

      <nav className="asm-side-nav" aria-label="Workspace">
        <Link href="/chat" className="asm-side-link" data-active={pathname === "/chat"} onClick={onClose}>
          <SquarePen aria-hidden /> Run <span>↗</span>
        </Link>
        <Link href="/history" className="asm-side-link" data-active={pathname === "/history"} onClick={onClose}>
          <History aria-hidden /> History <span>↗</span>
        </Link>
        <Link href="/settings" className="asm-side-link" data-active={pathname === "/settings"} onClick={onClose}>
          <Settings aria-hidden /> Settings <span>↗</span>
        </Link>
        <a
          href="https://github.com/arkap1502/Assembly#readme"
          target="_blank"
          rel="noreferrer"
          className="asm-side-link"
          onClick={onClose}
        >
          <Zap aria-hidden /> Docs <span>↗</span>
        </a>
      </nav>

      <div className="assembly-sidebar-scroll flex-1 overflow-y-auto px-1 py-2 flex flex-col gap-1">
        <div className="assembly-sidebar-section-label px-2 pb-2">
          <History className="size-3" aria-hidden />
          History (this device)
          <span className="ml-auto opacity-60">{executions.length.toString().padStart(2, "0")}</span>
        </div>

        <div className="px-1 pb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" aria-hidden />
            <label htmlFor="history-search" className="sr-only">Search history</label>
            <input
              id="history-search"
              type="text"
              placeholder="Search runs"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="assembly-sidebar-search w-full border border-border bg-muted/30 py-2.5 pl-8 pr-3 text-xs focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>
        </div>

        {loading ? (
          <div className="space-y-2 px-1">
            <Skeleton className="h-11 w-full rounded-none" />
            <Skeleton className="h-11 w-full rounded-none" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="mx-1 border border-dashed border-border px-4 py-10 text-center">
            <MessageSquare className="mx-auto size-7 text-muted-foreground" aria-hidden />
            <p className="mt-3 text-xs font-semibold text-foreground">
              {search ? "No matching runs" : "No runs yet"}
            </p>
            <p className="mx-auto mt-1 max-w-56 text-[11px] leading-relaxed text-muted-foreground">
              {search
                ? "Try a different search term."
                : "Your first cited answer is a few minutes away."}
            </p>
            {!search && (
              <Button
                variant="default"
                size="sm"
                className="mt-4 min-h-10 rounded-none"
                onClick={() => { router.push("/chat"); if (onClose) onClose() }}
              >
                <Plus className="mr-2 size-4" />
                Run my first question
              </Button>
            )}
          </div>
        ) : (
          filtered.map((ex) => {
            const isActive = pathname === `/executions` && searchParams?.get("id") === ex.id
            return (
              <div
                key={ex.id}
                className={`assembly-history-row group relative text-sm transition-colors ${
                  isActive ? "bg-brand/10" : "hover:bg-muted"
                }`}
              >
                <Link
                  href={`/executions?id=${ex.id}`}
                  prefetch={false}
                  onClick={onClose}
                  className={`assembly-history-link flex items-start gap-2 px-2.5 py-2.5 pr-9 ${
                    isActive ? "text-brand" : "text-foreground"
                  }`}
                >
                  <span className="mt-1 block size-1.5 shrink-0 bg-current opacity-60" aria-hidden />
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <p className="truncate text-[11px] font-medium leading-snug">{ex.question}</p>
                    <div className="mt-1.5 flex items-center gap-2">
                      <span className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                        {new Date(ex.created_at).toLocaleDateString()}
                      </span>
                      <span className="bg-muted px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-wider text-muted-foreground">
                        {ex.status}
                      </span>
                    </div>
                  </div>
                </Link>
                <button
                  type="button"
                  onClick={(e) => handleDelete(e, ex.id)}
                  aria-label={`Delete run: ${ex.question.slice(0, 60)}`}
                  className="absolute right-0 top-1 p-2.5 text-muted-foreground hover:text-danger md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100"
                  title="Delete execution"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            )
          })
        )}
      </div>

      <div className="assembly-sidebar-footer p-4 border-t border-border mt-auto flex flex-col gap-2">
        <div className="assembly-sidebar-utility-row flex gap-2">
          <Button variant="outline" size="sm" className="flex-1" onClick={handleExport}>
            <Download className="size-3.5 mr-1" /> Export
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            disabled={importing}
            onClick={() => importInputRef.current?.click()}
          >
            <Upload className="size-3.5 mr-1" /> {importing ? "Importing…" : "Import"}
          </Button>
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
        </div>
        <div className="assembly-sidebar-preferences flex items-center justify-end gap-2">
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

  // The landing page renders its own nav; hide the app sidebar there.
  const isLandingPage = pathname === "/"

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
              <div className="flex items-center gap-2.5">
                <span className="asm-mark !h-6 !w-6" aria-hidden="true">
                  <i /><i /><i /><i />
                </span>
                <span className="text-xs font-bold uppercase tracking-[0.2em]">Assembly</span>
              </div>
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

          {isOffline && (
            <div className="bg-danger/90 text-white px-4 py-1.5 text-center text-sm font-medium flex items-center justify-center gap-2">
              <WifiOff className="size-4" />
              You are currently offline. Some features may not work.
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
