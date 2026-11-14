"use client"

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { storage, type HistoryRecord } from "@/lib/storage"
import { useToast } from "@/components/ui/toast"
import { Skeleton } from "@/components/ui/skeleton"
import {
  ArrowRight,
  Download,
  Search,
  Trash2,
  Upload,
  X,
  Clock,
  Users,
  FileText,
} from "lucide-react"

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleDateString(undefined, { month: "short", day: "2-digit", year: "numeric" })
}

function relativeDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  const now = new Date()
  const startOfDay = (input: Date) => new Date(input.getFullYear(), input.getMonth(), input.getDate()).getTime()
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  if (days <= 0) return "Today"
  if (days === 1) return "Yesterday"
  if (days < 7) return `${days} days ago`
  return formatDate(value)
}

function agentCount(record: HistoryRecord): number | null {
  return record.verification?.agents ?? record.agentCount ?? null
}

function statusLabel(status: string) {
  return status.replace(/_/g, " ")
}

export default function HistoryPage() {
  const { toast } = useToast()
  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [importing, setImporting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRecords(await storage.listHistory())
    } catch {
      toast({
        title: "History unavailable",
        description: "Browser storage is blocked in this context. Runs still work, but they cannot be listed.",
        variant: "warning",
      })
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    let active = true
    storage
      .listHistory()
      .then((next) => {
        if (active) setRecords(next)
      })
      .catch(() => {
        if (active) {
          toast({
            title: "History unavailable",
            description: "Browser storage is blocked in this context. Runs still work, but they cannot be listed.",
            variant: "warning",
          })
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [toast])

  const filtered = useMemo(
    () => records.filter((record) => record.question.toLowerCase().includes(search.trim().toLowerCase())),
    [records, search],
  )

  const completed = records.filter((record) => record.status === "completed").length
  const averageConsensus = (() => {
    const scored = records.filter((record) => typeof record.consensus === "number")
    if (!scored.length) return null
    return scored.reduce((sum, record) => sum + (record.consensus ?? 0), 0) / scored.length
  })()

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this run from this device?")) return
    try {
      await storage.deleteHistory(id)
      setRecords((current) => current.filter((record) => record.id !== id))
      toast({ title: "Deleted", description: "The run was removed from this device." })
    } catch {
      toast({
        title: "Could not delete the run",
        description: "Browser storage rejected the deletion. Try again or clear site data.",
        variant: "danger",
      })
    }
  }

  const handleExport = async () => {
    const text = await storage.exportJSON()
    const blob = new Blob([text], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = "assembly-history.json"
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const handleImport = async (file: File) => {
    if (importing) return
    setImporting(true)
    try {
      await storage.importJSON(await file.text())
      await load()
      toast({ title: "Import complete", description: "History and usage were imported.", variant: "success" })
    } catch {
      toast({
        title: "Import failed",
        description: "Check that this is a valid Assembly history export and try again.",
        variant: "danger",
      })
    } finally {
      if (inputRef.current) inputRef.current.value = ""
      setImporting(false)
    }
  }

  return (
    <div className="cin-page cin-history-page">
      <main id="main-content" tabIndex={-1} className="cin-main">
        <div className="cin-shell cin-page-inner">
          <header className="cin-page-head">
            <div className="cin-page-head-copy">
              <span className="cin-kicker">History</span>
              <h1 className="cin-title">Past runs</h1>
              <p className="cin-lede">
                Every investigation stays on this device. Search it, reopen the full debate, or move it
                to another browser with a JSON export.
              </p>
            </div>
            <div className="cin-page-head-aside">
              <span className="cin-page-number">06 / 08</span>
              <div className="cin-history-actions">
                <input
                  ref={inputRef}
                  type="file"
                  accept="application/json,.json"
                  className="sr-only"
                  aria-label="Import Assembly history JSON"
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0]
                    if (file) void handleImport(file)
                  }}
                />
                <button
                  type="button"
                  className="cin-btn cin-btn-sm cin-btn-outline"
                  onClick={() => inputRef.current?.click()}
                  disabled={importing}
                >
                  <Upload className="size-4" aria-hidden />
                  {importing ? "Importing…" : "Import"}
                </button>
                <button
                  type="button"
                  className="cin-btn cin-btn-sm cin-btn-outline"
                  onClick={() => void handleExport()}
                  disabled={!records.length}
                >
                  <Download className="size-4" aria-hidden />
                  Export
                </button>
              </div>
            </div>
          </header>

          <div className="cin-history-tools">
            <div className="cin-search">
              <Search className="size-4 shrink-0" aria-hidden />
              <label htmlFor="history-search" className="sr-only">
                Search past runs
              </label>
              <input
                id="history-search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search past runs…"
              />
              {search && (
                <button
                  type="button"
                  className="cin-search-clear"
                  aria-label="Clear search"
                  onClick={() => setSearch("")}
                >
                  <X className="size-4" aria-hidden />
                </button>
              )}
            </div>

            <div className="cin-history-stats" aria-live="polite">
              <span className="cin-chip">
                {records.length.toString().padStart(2, "0")} run{records.length === 1 ? "" : "s"}
              </span>
              <span className="cin-chip cin-chip-success">{completed} completed</span>
              {averageConsensus !== null && (
                <span className="cin-chip cin-chip-brand">
                  {Math.round(averageConsensus * 100)}% avg agreement
                </span>
              )}
              {search && (
                <span className="cin-chip">
                  {filtered.length} match{filtered.length === 1 ? "" : "es"}
                </span>
              )}
            </div>
          </div>

          {loading ? (
            <div aria-busy="true" aria-label="Loading local history">
              <div className="cin-timeline">
                {[0, 1, 2, 3].map((index) => (
                  <div key={index} className="cin-timeline-row">
                    <Skeleton className="cin-skeleton" />
                  </div>
                ))}
              </div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="cin-empty-state">
              <span className="cin-kicker !mb-0">{search ? "No match" : "Empty"}</span>
              <h2>{search ? "No matching runs" : "No runs on this device yet"}</h2>
              <p>
                {search
                  ? "Try a different question, or clear the search to see every saved run."
                  : "Your first investigation will appear here. History stays in this browser unless you export it."}
              </p>
              {search ? (
                <button
                  type="button"
                  className="cin-btn cin-btn-outline mt-6"
                  onClick={() => setSearch("")}
                >
                  Clear search
                  <X className="size-4" aria-hidden />
                </button>
              ) : (
                <Link href="/chat" className="cin-btn cin-btn-primary mt-6">
                  Start an investigation
                  <ArrowRight className="size-4" aria-hidden />
                </Link>
              )}
            </div>
          ) : (
            <div className="cin-timeline">
              {filtered.map((record) => {
                const agents = agentCount(record)
                const consensus =
                  typeof record.consensus === "number" ? Math.round(record.consensus * 100) : null
                return (
                  <div key={record.id} className="cin-timeline-row">
                    <span className="cin-timeline-date">{relativeDate(record.created_at)}</span>
                    <span className="cin-timeline-dot" aria-hidden />
                    <article className="cin-run-card">
                      <div className="cin-run-card-main">
                        <h2>
                          <Link href={`/executions?id=${record.id}`} className="before:absolute before:inset-0">
                            {record.question}
                          </Link>
                        </h2>
                        <div className="cin-run-card-meta">
                          <span className="inline-flex items-center gap-1.5">
                            <Clock className="size-3.5" aria-hidden />
                            {record.minutes} min
                          </span>
                          {agents !== null && (
                            <span className="inline-flex items-center gap-1.5">
                              <Users className="size-3.5" aria-hidden />
                              {agents} agent{agents === 1 ? "" : "s"}
                            </span>
                          )}
                          {record.verification?.sources_verified !== undefined && (
                            <span className="inline-flex items-center gap-1.5">
                              <FileText className="size-3.5" aria-hidden />
                              {record.verification.sources_verified} sources
                            </span>
                          )}
                          {record.status !== "completed" && (
                            <span className="cin-chip cin-chip-warning !min-h-0 !py-0.5">
                              {statusLabel(record.status)}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="cin-run-card-actions">
                        {consensus !== null && <span className="cin-agree-pill">{consensus}% agree</span>}
                        <span className="cin-open-link" aria-hidden>
                          Open
                          <ArrowRight className="size-4" />
                        </span>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.preventDefault()
                            event.stopPropagation()
                            void handleDelete(record.id)
                          }}
                          className="cin-row-action is-danger relative z-10"
                          aria-label={`Delete run: ${record.question.slice(0, 60)}`}
                        >
                          <Trash2 className="size-4" aria-hidden />
                        </button>
                      </div>
                    </article>
                  </div>
                )
              })}
            </div>
          )}

          <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-5 text-xs text-muted-foreground">
            <span>
              {records.length} local run{records.length === 1 ? "" : "s"} · no account, no server-side
              history
            </span>
            <Link href="/chat" className="cin-quiet-link">
              New investigation
              <ArrowRight className="ml-1.5 size-3.5" aria-hidden />
            </Link>
          </footer>
        </div>
      </main>
    </div>
  )
}
