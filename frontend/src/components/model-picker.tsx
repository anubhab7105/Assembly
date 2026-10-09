"use client"

import React, { useEffect, useState } from "react"
import { ApiClient, type Catalog } from "@/lib/api-client"
import { Badge } from "@/components/ui/badge"
import { AlertTriangle } from "lucide-react"

export interface ModelSelection {
  selected: string[]
  pins: Record<string, string>
}

const ROLES = ["solver", "researcher", "critic", "synthesizer", "planner"] as const

export function ModelPicker({
  value,
  onChange,
}: {
  value: ModelSelection
  onChange: (v: ModelSelection) => void
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pinRole, setPinRole] = useState<string>("critic")
  const [pinModel, setPinModel] = useState<string>("")

  useEffect(() => {
    ApiClient.catalog().then(setCatalog).catch(() => setError("Could not load model catalog."))
  }, [])

  const toggle = (id: string) => {
    const next = value.selected.includes(id)
      ? value.selected.filter((m) => m !== id)
      : [...value.selected, id]
    onChange({ ...value, selected: next })
  }

  const families = new Set<string>()
  if (catalog) {
    for (const p of catalog.providers) {
      for (const m of p.models) {
        if (value.selected.length === 0 || value.selected.includes(m.id)) {
          families.add(m.family)
        }
      }
    }
  }

  const allModels = catalog?.providers.flatMap((p) => p.models) ?? []

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-4" data-testid="model-picker">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Models (Auto when none selected)</h3>
        <Badge variant="secondary">{families.size} families</Badge>
      </div>

      {error && <p className="text-xs text-danger">{error}</p>}

      {families.size > 0 && families.size < 3 && (
        <div className="flex items-center gap-2 rounded-md border border-warning/30 bg-warning-subtle p-2 text-xs text-warning">
          <AlertTriangle className="size-4 shrink-0" />
          Fewer than 3 families selected — debate quality will suffer.
        </div>
      )}

      <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
        {catalog?.providers.map((p) => (
          <div key={p.id}>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
              {p.id}
            </p>
            <div className="flex flex-wrap gap-2">
              {p.models.map((m) => (
                <label
                  key={m.id}
                  className={`flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-mono transition-colors ${
                    value.selected.includes(m.id)
                      ? "border-brand bg-brand/10 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="accent-brand"
                    checked={value.selected.includes(m.id)}
                    onChange={() => toggle(m.id)}
                  />
                  {m.id}
                  <span className="text-[10px] opacity-60">{m.family}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <span className="text-xs text-muted-foreground">Pin role:</span>
        <select
          value={pinRole}
          onChange={(e) => setPinRole(e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1 text-xs"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <select
          value={pinModel}
          onChange={(e) => setPinModel(e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1 text-xs max-w-56"
        >
          <option value="">none</option>
          {allModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.id}
            </option>
          ))}
        </select>
        <button
          className="rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
          onClick={() => {
            if (!pinModel) {
              const next = { ...value.pins }
              delete next[pinRole]
              onChange({ ...value, pins: next })
            } else {
              onChange({ ...value, pins: { ...value.pins, [pinRole]: pinModel } })
            }
          }}
        >
          Apply pin
        </button>
        {Object.keys(value.pins).length > 0 && (
          <span className="text-[11px] font-mono text-muted-foreground">
            {Object.entries(value.pins).map(([r, m]) => `${r}=${m}`).join(" ")}
          </span>
        )}
      </div>
    </div>
  )
}
