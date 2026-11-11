"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { storage, type HistoryRecord } from "@/lib/storage"
import { useToast } from "@/components/ui/toast"
import { Download, Upload } from "lucide-react"

export function HistoryQuick() {
  const { toast } = useToast()
  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [importing, setImporting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      setRecords((await storage.listHistory()).slice(0, 4))
    } catch {
      setRecords([])
    }
  }, [])

  useEffect(() => {
    let active = true
    queueMicrotask(() => {
      if (active) void load()
    })
    return () => {
      active = false
    }
  }, [load])

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
    <section className="cin-window cin-quick-history" aria-label="History on this device">
      <div className="cin-quick-history-head">
        <h2>
          History <span>(this device)</span>
        </h2>
        <div className="cin-quick-history-actions">
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
            <Upload className="size-3.5" aria-hidden />
            {importing ? "Importing" : "Import"}
          </button>
          <button
            type="button"
            className="cin-btn cin-btn-sm cin-btn-outline"
            onClick={() => void handleExport()}
            disabled={!records.length}
          >
            <Download className="size-3.5" aria-hidden />
            Export
          </button>
        </div>
      </div>

      {records.length === 0 ? (
        <p className="cin-quick-empty">
          No runs on this device yet. Your first investigated answer will appear here.
        </p>
      ) : (
        <div className="cin-quick-runs">
          {records.map((record) => (
            <Link key={record.id} href={`/executions?id=${record.id}`} className="cin-quick-run">
              <span className="size-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
              <b>{record.question}</b>
              <span className="hidden sm:inline">
                {typeof record.consensus === "number" ? `${Math.round(record.consensus * 100)}%` : "—"}
              </span>
              <time dateTime={record.created_at}>
                {new Date(record.created_at).toLocaleDateString(undefined, { month: "short", day: "2-digit" })}
              </time>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
