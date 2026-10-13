"use client"

import React, { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { globalVault } from "@/lib/key-vault"
import { ApiClient, type Catalog, type UsageEntry } from "@/lib/api-client"
import { storage } from "@/lib/storage"
import { env } from "@/lib/env"
import {
  PRIVACY_ACK_KEY,
  PRIVACY_NOTICE_VERSION,
} from "@/lib/privacy-notice"
import { PrivacyDialog } from "@/components/privacy-dialog"
import { ServerStatusBanner } from "@/components/server-status-banner"
import { evaluateGate, gateChipText } from "@/lib/diversity-gate"
import { failureMessage, isPresentableRun } from "@/lib/run-outcome"
import { ModelPicker, type ModelSelection } from "@/components/model-picker"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Zap, Send, Settings, Sparkles, Clock, SlidersHorizontal } from "lucide-react"

const EXAMPLES = [
  { label: "Quantum computing", question: "Will quantum computing achieve commercial advantage before 2030?" },
  { label: "Room-temperature superconductors", question: "What are the most viable methods for replicating room-temperature superconductors?" },
  { label: "AGI timeline", question: "Analyse the timeline and economic impacts of AGI given current scaling laws." },
  { label: "EV battery chemistry", question: "Which battery chemistry is most likely to replace Lithium-Ion in EVs by 2035?" },
]

const TIME_BUDGETS = [3, 5, 10, 15]

export default function Home() {
  const router = useRouter()

  const [question, setQuestion] = useState("")
  const [minutes, setMinutes] = useState(5)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [selection, setSelection] = useState<ModelSelection>({ selected: [], pins: {} })
  const [hasKeys, setHasKeys] = useState(false)
  const [privacyAcked, setPrivacyAcked] = useState(false)
  const [showPrivacy, setShowPrivacy] = useState(false)
  const [catalogNotes, setCatalogNotes] = useState<{ id: string; privacy_note?: string | null }[]>([])
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [catalogFailed, setCatalogFailed] = useState(false)
  const [catalogTick, setCatalogTick] = useState(0)
  const [showModelSettings, setShowModelSettings] = useState(false)
  const [enabledIds, setEnabledIds] = useState<string[]>([])
  const [confirmedGateSignature, setConfirmedGateSignature] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const appMode = env.NEXT_PUBLIC_APP_MODE === "desktop" ? "desktop" : "web"

  const gate = React.useMemo(() => {
    const enabled = new Set(enabledIds)
    const fams: string[] = []
    if (catalog) {
      for (const p of catalog.providers) {
        if (!p.enabled || !enabled.has(p.id)) continue
        for (const m of p.models) {
          if (selection.selected.length > 0 && !selection.selected.includes(m.id)) continue
          if (!fams.includes(m.family)) fams.push(m.family)
        }
      }
    }
    return evaluateGate(fams, enabled.size)
  }, [catalog, enabledIds, selection.selected])

  const gateSignature = JSON.stringify({
    level: gate.level,
    reasons: gate.reasons,
    enabledIds: [...enabledIds].sort(),
    selected: [...selection.selected].sort(),
    pins: selection.pins,
  })
  const degradedConfirmed = confirmedGateSignature === gateSignature

  useEffect(() => {
    const refreshKeys = () => {
      globalVault.allKeys().then((k) => { setHasKeys(Object.keys(k).length > 0); setEnabledIds(Object.keys(k)) }).catch(() => {})
    }
    refreshKeys()
    // The vault is persistent: re-read when the tab regains focus so the
    // picker gate and the execution request always agree on readiness.
    window.addEventListener("focus", refreshKeys)
    document.addEventListener("visibilitychange", refreshKeys)
    storage
      .getSetting(PRIVACY_ACK_KEY)
      .then((raw) => {
        if (!raw) {
          setShowPrivacy(true)
          return
        }
        try {
          const ack = JSON.parse(raw) as { version?: number }
          if (ack.version !== PRIVACY_NOTICE_VERSION) {
            setShowPrivacy(true)
          } else {
            setPrivacyAcked(true)
          }
        } catch {
          setShowPrivacy(true)
        }
      })
      .catch(() => setShowPrivacy(true))
    return () => {
      window.removeEventListener("focus", refreshKeys)
      document.removeEventListener("visibilitychange", refreshKeys)
    }
  }, [])

  useEffect(() => {
    ApiClient.catalog()
      .then((c) => {
        setCatalog(c)
        setCatalogFailed(false)
        setCatalogNotes(
          c.providers
            .filter((p) => p.enabled)
            .map((p) => ({ id: p.id, privacy_note: p.privacy_note ?? null })),
        )
      })
      .catch(() => {
        setCatalog(null)
        setCatalogFailed(true)
      })
  }, [catalogTick])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [question])

  const handleAcknowledge = async () => {
    await storage.setSetting(
      PRIVACY_ACK_KEY,
      JSON.stringify({ version: PRIVACY_NOTICE_VERSION, acknowledged_at: new Date().toISOString() }),
    )
    setPrivacyAcked(true)
    setShowPrivacy(false)
  }

  const handleLaunch = async () => {
    if (!question.trim() || loading) return
    if (!privacyAcked) {
      setShowPrivacy(true)
      setStatus("Please acknowledge the privacy notice first.")
      return
    }
    if (gate.level === "BLOCKED") {
      setStatus(gate.reasons[0] ?? "No model families ready.")
      return
    }
    if (gate.level === "DEGRADED" && !degradedConfirmed) {
      setStatus("Confirm the single-family run below before launching.")
      return
    }
    setLoading(true)
    setStatus("Checking capacity…")
    // Run state hoisted above try: the catch block persists a cancelled
    // record on mid-stream failure, so it must see these bindings.
    let finalAnswer = ""
    let consensus: number | null = null
    let confidence: "High" | "Moderate" | "Low" | null = null
    let agentCount: number | null = null
    let providers: string[] = []
    let debateRounds: number | null = null
    let tokens: number | null = null
    let elapsedSeconds: number | null = null
    let streamStarted = false
    const runId = `local-${Date.now()}`
    try {
      const keys = await globalVault.allKeys()
      // The Tavily search key travels separately; it is never a model key.
      const { tavily, ...providerKeys } = keys
      const searchKeys = tavily ? { tavily } : undefined
      const usage: UsageEntry[] = await storage.getUsage()
      const preflight = await ApiClient.preflight(
        question,
        minutes,
        usage,
        providerKeys,
        { selected: selection.selected, pins: selection.pins },
      )
      if (!preflight.feasible) {
        setStatus(`Not feasible: ${preflight.explanation ?? "quota exhausted"}`)
        setLoading(false)
        return
      }
      setStatus("Running team… (streaming)")
      const result = await ApiClient.startRunStream(
        {
          question,
          minutes,
          providerKeys,
          searchKeys,
          selection: { selected: selection.selected, pins: selection.pins },
          usage,
        },
        (event: {
          event_type?: string
          data?: {
            answer?: string
            consensus_score?: number
            confidence_label?: "High" | "Moderate" | "Low"
            agent_count?: number
            providers_used?: string[]
            debate_rounds?: number
            tokens_used?: number
            elapsed_seconds?: number
          }
          usage?: UsageEntry[]
        }) => {
          streamStarted = true
          if (event.event_type === "execution.completed") {
            finalAnswer = event.data?.answer ?? ""
            consensus = event.data?.consensus_score ?? null
            confidence = event.data?.confidence_label ?? null
            agentCount = event.data?.agent_count ?? null
            providers = event.data?.providers_used ?? []
            debateRounds = event.data?.debate_rounds ?? null
            tokens = event.data?.tokens_used ?? null
            elapsedSeconds = event.data?.elapsed_seconds ?? null
          }
          if (event.event_type === "run.finished" && Array.isArray(event.usage)) {
            void storage.setUsage(event.usage)
          }
        },
      )
      // Explicit terminal handling: only a completed run with a non-empty
      // final answer is presentable. Failed/incomplete runs keep their
      // failure history but never navigate to the active-run screen.
      if (!isPresentableRun({ status: result.status, finalAnswer })) {
        const failedStatus = result.status === "completed" ? "failed" : result.status
        await storage.saveHistory({
          id: runId,
          question,
          answer: finalAnswer,
          status: failedStatus,
          created_at: new Date().toISOString(),
          minutes,
          consensus,
          confidence,
          agentCount,
          providers,
          debateRounds,
          tokens,
          elapsedSeconds,
        })
        setStatus(
          failureMessage({
            status: failedStatus,
            stage: result.stage,
            errorCode: result.errorCode,
          }),
        )
        setLoading(false)
        return
      }
      await storage.saveHistory({
        id: runId,
        question,
        answer: finalAnswer,
        status: result.status,
        created_at: new Date().toISOString(),
        minutes,
        consensus,
        confidence,
        agentCount,
        providers,
        debateRounds,
        tokens,
        elapsedSeconds,
      })
      router.push(`/executions?id=${runId}`)
    } catch (err) {
      // Mid-stream failures (abort vs. broken stream) keep distinct states:
      // a user abort is cancelled; a stream that dies without run.finished
      // is a failure, never a silent empty run. Pre-stream rejections (no
      // run started) only show the error.
      const message = err instanceof Error ? err.message : "Run failed"
      const aborted =
        (err instanceof DOMException && err.name === "AbortError") ||
        /abort/i.test(message)
      if (streamStarted) {
        try {
          await storage.saveHistory({
            id: runId,
            question,
            answer: finalAnswer,
            status: aborted ? "cancelled" : "failed",
            created_at: new Date().toISOString(),
            minutes,
            consensus,
            confidence,
            agentCount,
            providers,
            debateRounds,
            tokens,
            elapsedSeconds,
          })
        } catch {
          // Storage failure must not hide the original error.
        }
      }
      setStatus(message)
      setLoading(false)
    }
  }

  // Warn before a refresh/tab-close kills a running team (the server
  // cancels the run on disconnect; there is no resume for web runs).
  useEffect(() => {
    if (!loading) return
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener("beforeunload", onBeforeUnload)
    return () => window.removeEventListener("beforeunload", onBeforeUnload)
  }, [loading])

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-8 sm:px-6 sm:py-12">
        <div className="mb-7 text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-brand/10 text-brand">
            <Zap className="size-6" aria-hidden />
          </div>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
            Ask one hard question
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Independent analysis. One sourced answer.
          </p>
        </div>

        {!hasKeys && (
          <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-warning/30 bg-warning-subtle px-3 py-2.5">
            <p className="text-xs font-medium text-warning">Add provider keys to run an investigation.</p>
            <Button variant="outline" size="sm" onClick={() => router.push("/settings")} className="shrink-0">
              <Settings className="mr-1.5 size-3.5" />
              Add keys
            </Button>
          </div>
        )}

        <div
          data-testid="diversity-chip"
          className={`mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 py-2 text-xs ${
            gate.level === "OK" ? "border-success/30 bg-success-subtle/40" : gate.level === "WARN" ? "border-warning/30 bg-warning-subtle" : gate.level === "DEGRADED" ? "border-danger/30 bg-danger/10" : "border-border bg-card"
          }`}
        >
          <span className="font-medium">{gateChipText(gate)}</span>
          {gate.level !== "OK" && <span className="text-muted-foreground">{gate.reasons[0]}</span>}
          {gate.level === "DEGRADED" && !degradedConfirmed && (
            <Button variant="outline" size="sm" className="min-h-8" data-testid="degraded-confirm" onClick={() => setConfirmedGateSignature(gateSignature)}>
              Run anyway
            </Button>
          )}
        </div>

        {catalogFailed && (
          <div className="mb-3">
            <ServerStatusBanner url={env.apiUrl} onRetry={() => setCatalogTick((t) => t + 1)} />
          </div>
        )}

        <div className="space-y-3">
          <div className="rounded-2xl border border-border bg-card p-3 shadow-sm transition-colors focus-within:border-brand/60 focus-within:ring-2 focus-within:ring-brand/10">
            <label htmlFor="research-question" className="sr-only">Research question (max 2000 characters)</label>
            <textarea
              id="research-question"
              ref={textareaRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask anything worth checking across multiple models…"
              aria-describedby="question-status"
              className="max-h-56 min-h-24 w-full resize-y bg-transparent px-2 py-2 text-base leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none"
              rows={3}
              maxLength={2000}
              required
            />
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/70 pt-3">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-9"
                  onClick={() => setShowModelSettings(true)}
                  aria-haspopup="dialog"
                  aria-label="Open model and role settings"
                >
                  <SlidersHorizontal className="mr-1.5 size-3.5" />
                  Models{selection.selected.length > 0 ? ` · ${selection.selected.length}` : " · Auto"}
                </Button>
                <div className="flex items-center rounded-lg border border-border bg-background p-0.5" role="group" aria-label="Time budget">
                  <Clock className="ml-2 mr-1 size-3.5 text-muted-foreground" aria-hidden />
                  {TIME_BUDGETS.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setMinutes(m)}
                      aria-pressed={minutes === m}
                      aria-label={`${m} minutes`}
                      className={`min-h-9 min-w-9 rounded-md px-2 text-xs font-medium transition-colors ${
                        minutes === m ? "bg-muted text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {m}m
                    </button>
                  ))}
                </div>
              </div>
              <Button size="default" onClick={handleLaunch} disabled={loading || !question.trim() || gate.level === "BLOCKED"} className="min-h-10 rounded-xl px-4">
                {loading ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Send className="mr-1.5 size-4" />}
                {loading ? "Running…" : "Run"}
              </Button>
            </div>
          </div>
          {status && <p id="question-status" role="alert" className="rounded-lg border border-danger/40 bg-danger-subtle px-3 py-2 text-xs font-medium text-danger">{status}</p>}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-center gap-2" aria-label="Suggested questions">
          <span className="mr-1 text-xs text-muted-foreground">Try</span>
          {EXAMPLES.map((example) => (
            <button
              key={example.label}
              type="button"
              onClick={() => { setQuestion(example.question); textareaRef.current?.focus() }}
              className="min-h-9 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-brand/40 hover:bg-brand/5 hover:text-foreground"
              title={example.question}
            >
              {example.label}
            </button>
          ))}
        </div>
      </main>

      <Dialog open={showModelSettings} onOpenChange={setShowModelSettings}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Models and roles</DialogTitle>
            <DialogDescription>
              Automatic selection is the default. Choose specific models or pin a model to a role when needed.
            </DialogDescription>
          </DialogHeader>
          <ModelPicker value={selection} onChange={setSelection} keyedProviderIds={enabledIds} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModelSettings(false)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {showPrivacy && (
        <PrivacyDialog
          mode={appMode}
          providers={catalogNotes.filter((p) =>
            enabledIds.length > 0 ? enabledIds.includes(p.id) : true,
          )}
          onAcknowledge={() => void handleAcknowledge()}
        />
      )}
    </div>
  )
}
