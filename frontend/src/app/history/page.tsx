"use client"

import React, { useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { storage, type HistoryRecord } from "@/lib/storage"
import { useToast } from "@/components/ui/toast"
import { ArrowRight, Download, Search, Trash2, Upload, X } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleDateString(undefined, { month: "short", day: "2-digit", year: "numeric" })
}

export default function HistoryPage() {
  const { toast } = useToast()
  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [importing, setImporting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const load = React.useCallback(async () => {
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
    await storage.deleteHistory(id)
    setRecords((current) => current.filter((record) => record.id !== id))
    toast({ title: "Deleted", description: "The run was removed from this device." })
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
    <div className="asm-page asm-history-page min-h-screen">
      <header className="asm-page-head-wrap">
        <div className="asm-history !py-0">
          <div className="asm-page-head">
            <div>
              <span className="asm-index">[ 06 / History ]</span>
              <h1 className="asm-page-title">Run history</h1>
            </div>
            <p className="asm-page-head-note" aria-live="polite">
              {records.length.toString().padStart(3, "0")} runs on this device · {completed} completed
              {averageConsensus !== null
                ? ` · ${Math.round(averageConsensus * 100)}% average agreement`
                : ""}
            </p>
          </div>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="asm-history">
        <div className="asm-history-tools">
          <div className="asm-search">
            <Search className="size-3.5 shrink-0" aria-hidden />
            <label htmlFor="history-search" className="sr-only">Search past runs</label>
            <input
              id="history-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search past runs…"
            />
            {search && (
              <button
                type="button"
                className="asm-search-clear"
                aria-label="Clear search"
                onClick={() => setSearch("")}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            )}
          </div>

          <div className="asm-history-actions">
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
            <button type="button" className="asm-btn asm-btn-outline" onClick={() => inputRef.current?.click()} disabled={importing}>
              <Upload className="size-3.5" aria-hidden />
              {importing ? "Importing" : "Import"}
            </button>
            <button type="button" className="asm-btn asm-btn-outline" onClick={() => void handleExport()} disabled={!records.length}>
              <Download className="size-3.5" aria-hidden />
              Export
            </button>
            <Link href="/chat" className="asm-btn asm-btn-primary" data-cursor-label="NEW RUN">
              New run
              <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </div>

        {loading ? (
          <div className="border border-border px-6 py-10" aria-busy="true">
            <p className="asm-label">Loading local history…</p>
            <div className="mt-6 space-y-3">
              {[0, 1, 2].map((index) => (
                <Skeleton key={index} className="h-12 w-full rounded-none" />
              ))}
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="border border-dashed border-border px-6 py-20 text-center">
            <span className="asm-index">[ Empty ]</span>
            <h2 className="mt-4 text-2xl font-bold uppercase tracking-tight">
              {search ? "No matching runs" : "No runs on this device yet"}
            </h2>
            <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-muted-foreground">
              {search
                ? "Try a different question or clear the search."
                : "Your first investigation will appear here. History stays in this browser unless you export it."}
            </p>
            {search ? (
              <button type="button" className="asm-btn asm-btn-outline mt-6" onClick={() => setSearch("")}>
                Clear search
                <X className="size-4" aria-hidden />
              </button>
            ) : (
              <Link href="/chat" className="asm-btn asm-btn-primary mt-6">
                Start an investigation
                <ArrowRight className="size-4" />
              </Link>
            )}
          </div>
        ) : (
          <table className="asm-table">
            <thead>
              <tr>
                <th>Question</th>
                <th>Date</th>
                <th>Budget</th>
                <th>Agreement</th>
                <th>Status</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((record) => (
                <tr key={record.id}>
                  <td data-label="Question">
                    <Link href={`/executions?id=${record.id}`} className="is-question hover:text-brand">
                      {record.question}
                    </Link>
                  </td>
                  <td data-label="Date">{formatDate(record.created_at)}</td>
                  <td data-label="Budget" className="is-mono">{record.minutes} min</td>
                  <td data-label="Agreement" className="is-score">
                    {typeof record.consensus === "number" ? `${Math.round(record.consensus * 100)}%` : "—"}
                  </td>
                  <td data-label="Status" className="is-mono">{record.status.replace(/_/g, " ")}</td>
                  <td className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Link
                        href={`/executions?id=${record.id}`}
                        className="asm-row-action"
                        aria-label={`Open run: ${record.question.slice(0, 60)}`}
                      >
                        <ArrowRight className="size-4" />
                      </Link>
                      <button
                        type="button"
                        onClick={() => void handleDelete(record.id)}
                        className="asm-row-action hover:!text-danger"
                        aria-label={`Delete run: ${record.question.slice(0, 60)}`}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  )
}
