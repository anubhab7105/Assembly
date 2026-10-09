"use client"

import React, { useState, useEffect, Suspense } from "react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { ToastProvider, useToast } from "@/components/ui/toast"
import { storage, type HistoryRecord } from "@/lib/storage"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Zap, Settings, Menu, X, WifiOff, Plus, History, Trash2, Search, MessageSquare, Download, Upload,
} from "lucide-react"

function useOfflineStatus() {
  const [isOffline, setIsOffline] = useState(false)
  useEffect(() => {
    const handleOnline = () => setIsOffline(false)
    const handleOffline = () => setIsOffline(true)
    if (typeof navigator !== "undefined") {
      setIsOffline(!navigator.onLine)
    }
    window.addEventListener("online", handleOnline)
    window.addEventListener("offline", handleOffline)
    return () => {
      window.removeEventListener("online", handleOnline)
      window.removeEventListener("offline", handleOffline)
    }
  }, [])
  return isOffline
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
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadExecutions()
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
            <Search className="size-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-border bg-muted/30 pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>
        </div>

        {loading ? (
          <div className="space-y-2 px-1">
            <Skeleton className="h-12 w-full rounded-md" />
            <Skeleton className="h-12 w-full rounded-md" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-2 py-8 text-center text-xs text-muted-foreground">
            {search ? "No matching executions found." : "No history yet."}
          </div>
        ) : (
          filtered.map((ex) => {
            const isActive = pathname === `/executions` && searchParams?.get("id") === ex.id
            return (
              <Link
                key={ex.id}
                href={`/executions?id=${ex.id}`}
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
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-danger rounded shrink-0"
                  title="Delete execution"
                >
                  <Trash2 className="size-3.5" />
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <ToastProvider>
      <div className="flex h-screen overflow-hidden bg-background">
        <aside className="hidden md:block w-72 shrink-0 h-full relative z-20">
          <Suspense fallback={<div className="p-4">Loading menu...</div>}>
            <SidebarContent />
          </Suspense>
        </aside>

        {mobileMenuOpen && (
          <div className="md:hidden fixed inset-0 z-50 flex">
            <div className="fixed inset-0 bg-background/80 backdrop-blur-sm" onClick={() => setMobileMenuOpen(false)} />
            <div className="relative w-4/5 max-w-sm h-full shadow-2xl">
              <Suspense fallback={<div className="p-4">Loading menu...</div>}>
                <SidebarContent onClose={() => setMobileMenuOpen(false)} />
              </Suspense>
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="absolute top-4 right-4 p-2 bg-background/50 rounded-full hover:bg-muted"
              >
                <X className="size-5" />
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
          <header className="md:hidden sticky top-0 z-30 flex items-center justify-between border-b border-border bg-card px-4 py-3">
            <div className="flex items-center gap-2">
              <Zap className="size-5 text-brand" />
              <span className="font-bold tracking-tight">Assembly</span>
            </div>
            <button onClick={() => setMobileMenuOpen(true)} className="p-1 -mr-1 rounded hover:bg-muted">
              <Menu className="size-6" />
            </button>
          </header>

          {isOffline && (
            <div className="bg-danger/90 text-white px-4 py-1.5 text-center text-sm font-medium flex items-center justify-center gap-2">
              <WifiOff className="size-4" />
              You are currently offline. Some features may not work.
            </div>
          )}

          <main className="flex-1 overflow-y-auto overflow-x-hidden relative focus-visible:outline-none" tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>
    </ToastProvider>
  )
}
