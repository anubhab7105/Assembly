"use client"

import React, { useState, useEffect, useSyncExternalStore, Suspense } from "react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { ToastProvider, useToast } from "@/components/ui/toast"
import { storage, type HistoryRecord } from "@/lib/storage"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Zap, Settings, Menu, X, WifiOff, Plus, History, Trash2, Search, MessageSquare, Download, Upload,
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

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const router = useRouter()
  const { toast } = useToast()

  const [executions, setExecutions] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")

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
      router.push("/")
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

  const handleImport = async (file: File) => {
    const text = await file.text()
    await storage.importJSON(text)
    await loadExecutions()
    toast({ title: "Imported", description: "History imported from JSON." })
  }

  const filtered = executions.filter((e) =>
    e.question.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="flex flex-col h-full bg-card border-r border-border">
      <div className="p-4 space-y-4">
        <Link href="/" className="flex items-center gap-2 text-foreground" onClick={onClose}>
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand/10 text-brand">
            <Zap className="size-4" />
          </div>
          <span className="font-bold tracking-tight">Assembly</span>
        </Link>
        <Button variant="default" className="w-full justify-start" onClick={() => { router.push("/"); if (onClose) onClose() }}>
          <Plus className="size-4 mr-2" />
          New Investigation
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-1">
        <div className="px-2 pb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
          <History className="size-3" />
          History (this device)
        </div>

        <div className="px-1 pb-3">
          <div className="relative">
            <Search className="size-3.5 absolute left-2.5 top-2.5 text-muted-foreground" aria-hidden />
            <label htmlFor="history-search" className="sr-only">Search history</label>
            <input
              id="history-search"
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-border bg-muted/30 pl-8 pr-3 py-2.5 text-xs focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>
        </div>

        {loading ? (
          <div className="space-y-2 px-1">
            <Skeleton className="h-12 w-full rounded-md" />
            <Skeleton className="h-12 w-full rounded-md" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="mx-1 rounded-xl border border-dashed border-border bg-muted/20 px-4 py-10 text-center">
            <MessageSquare className="mx-auto size-8 text-muted-foreground" aria-hidden />
            <p className="mt-3 text-sm font-semibold text-foreground">
              {search ? "No matching runs" : "No runs yet"}
            </p>
            <p className="mx-auto mt-1 max-w-56 text-xs text-muted-foreground">
              {search
                ? "Try a different search term."
                : "Your first cited answer is 3 minutes away."}
            </p>
            {!search && (
              <Button
                variant="default"
                size="sm"
                className="mt-4 min-h-11"
                onClick={() => { router.push("/chat"); if (onClose) onClose() }}
              >
                <Plus className="size-4 mr-2" />
                Run my first question
              </Button>
            )}
          </div>
        ) : (
          filtered.map((ex) => {
            const isActive = pathname === `/executions` && searchParams?.get("id") === ex.id
            return (
              <Link
                key={ex.id}
                href={`/executions?id=${ex.id}`}
                prefetch={false}
                onClick={onClose}
                className={`group flex items-start gap-2 rounded-md px-2 py-2 text-sm ${
                  isActive ? "bg-brand/10 text-brand" : "text-foreground hover:bg-muted"
                }`}
              >
                <MessageSquare className={`size-4 mt-0.5 shrink-0 ${isActive ? "text-brand" : "text-muted-foreground"}`} />
                <div className="flex-1 overflow-hidden">
                  <p className="truncate text-xs font-medium">{ex.question}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] text-muted-foreground">{new Date(ex.created_at).toLocaleDateString()}</span>
                    <span className="text-[9px] uppercase px-1.5 py-0.5 rounded-sm bg-muted text-muted-foreground">{ex.status}</span>
                  </div>
                </div>
                <button
                  onClick={(e) => handleDelete(e, ex.id)}
                  aria-label={`Delete run: ${ex.question.slice(0, 60)}`}
                  className="rounded p-2.5 hover:text-danger shrink-0 md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100"
                  title="Delete execution"
                >
                  <Trash2 className="size-4" />
                </button>
              </Link>
            )
          })
        )}
      </div>

      <div className="p-4 border-t border-border mt-auto flex flex-col gap-1">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="flex-1" onClick={handleExport}>
            <Download className="size-3.5 mr-1" /> Export
          </Button>
          <label className="flex-1">
            <span className="flex cursor-pointer items-center justify-center gap-1 rounded-md border border-border px-2 py-1.5 text-xs hover:bg-muted">
              <Upload className="size-3.5" /> Import
            </span>
            <input
              type="file"
              accept="application/json"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void handleImport(f)
              }}
            />
          </label>
        </div>
        <Link
          href="/settings"
          onClick={onClose}
          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50"
        >
          <Settings className="size-4" />
          Settings
        </Link>
      </div>
    </div>
  )
}

export function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const isOffline = useOfflineStatus()
  const pathname = usePathname()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    if (!mobileMenuOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileMenuOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
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
      <div className="flex h-screen overflow-hidden bg-background">
        {!isLandingPage && (
          <aside className="hidden md:block w-72 shrink-0 h-full relative z-20">
            <Suspense fallback={<div className="p-4">Loading menu...</div>}>
              <SidebarContent />
            </Suspense>
          </aside>
        )}

        {mobileMenuOpen && (
          <div className="md:hidden fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label="Menu">
            <button
              aria-label="Close menu"
              className="fixed inset-0 bg-background/80 backdrop-blur-sm cursor-default"
              onClick={() => setMobileMenuOpen(false)}
            />
            <div className="relative w-4/5 max-w-sm h-full shadow-2xl">
              <Suspense fallback={<div className="p-4">Loading menu...</div>}>
                <SidebarContent onClose={() => setMobileMenuOpen(false)} />
              </Suspense>
              <button
                onClick={() => setMobileMenuOpen(false)}
                aria-label="Close menu"
                className="absolute top-4 right-4 p-3 min-h-11 min-w-11 bg-background/50 rounded-full hover:bg-muted"
              >
                <X className="size-5" />
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
          {!isLandingPage && (
            <header className="md:hidden sticky top-0 z-30 flex items-center justify-between border-b border-border bg-card px-4 py-3">
              <div className="flex items-center gap-2">
                <Zap className="size-5 text-brand" />
                <span className="font-bold tracking-tight">Assembly</span>
              </div>
              <button
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open menu"
                aria-expanded={mobileMenuOpen}
                aria-controls="mobile-menu"
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

          <main id="main-content" className="flex-1 overflow-y-auto overflow-x-hidden relative focus-visible:outline-none" tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>
    </ToastProvider>
  )
}
