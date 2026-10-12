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
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Zap, Send, Settings, Sparkles, Clock } from "lucide-react"

const EXAMPLES = [
  "Will quantum computing achieve commercial advantage before 2030?",
  "What are the most viable methods for replicating room-temperature superconductors?",
  "Analyse the timeline and economic impacts of AGI given current scaling laws.",
  "Which battery chemistry is most likely to replace Lithium-Ion in EVs by 2035?"
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
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6 py-12">
      <main className="w-full max-w-2xl space-y-8">
        <div className="text-center space-y-4">
          <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-brand/10 text-brand mb-4">
            <Zap className="size-8" />
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
            Assembly
          </h1>
          <p className="text-lg text-muted-foreground mx-auto max-w-xl">
            Turn one question into a temporary team of AI agents that reason, debate, and verify to find the best answer.
          </p>
        </div>

        {!hasKeys && (
          <div className="rounded-xl border border-warning/30 bg-warning-subtle p-4 flex items-center justify-between gap-4">
            <p className="text-sm text-warning">Add provider keys first — runs use your keys, never a server account.</p>
            <Button variant="outline" size="sm" onClick={() => router.push("/settings")}>
              <Settings className="size-4 mr-2" />
              Configure Keys
            </Button>
          </div>
        )}

        <div data-testid="diversity-chip" className={`rounded-xl border p-3 text-sm ${gate.level === "OK" ? "border-success/30" : gate.level === "WARN" ? "border-warning/30 bg-warning-subtle" : gate.level === "DEGRADED" ? "border-danger/30 bg-danger/10" : "border-border"}`}>
          <p className="font-mono">{gateChipText(gate)}</p>
          {gate.level !== "OK" && <p className="mt-1 text-xs text-muted-foreground">{gate.reasons[0]}</p>}
          {gate.level === "DEGRADED" && !degradedConfirmed && (
            <Button variant="outline" size="sm" className="mt-2" data-testid="degraded-confirm" onClick={() => setConfirmedGateSignature(gateSignature)}>
              Run anyway with 1 family
            </Button>
          )}
        </div>

        {catalogFailed && (
          <ServerStatusBanner url={env.apiUrl} onRetry={() => setCatalogTick((t) => t + 1)} />
        )}

        <div className="space-y-4">
          <div className="relative rounded-2xl border border-border bg-card p-2 shadow-sm focus-within:border-brand">
            <label htmlFor="research-question" className="sr-only">Research question (max 2000 characters)</label>
            <textarea
              id="research-question"
              ref={textareaRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What do you want the team to research?"
              aria-describedby="question-status"
              className="w-full resize-none bg-transparent px-4 pt-3 pb-16 text-base text-foreground placeholder:text-muted-foreground focus:outline-none sm:pb-12"
              rows={2}
              maxLength={2000}
              required
            />
            <div className="absolute bottom-2 left-2 right-2 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" className="bg-muted px-2 py-1 font-mono text-muted-foreground">
                  Mode: Auto
                </Badge>
                <div className="flex items-center rounded-md border border-border bg-background p-0.5" role="group" aria-label="Time budget">
                  <Clock className="size-3.5 text-muted-foreground ml-2 mr-1" aria-hidden />
                  {TIME_BUDGETS.map((m) => (
                    <button
                      key={m}
                      onClick={() => setMinutes(m)}
                      aria-pressed={minutes === m}
                      aria-label={`${m} minutes`}
                      className={`min-h-11 min-w-11 px-2.5 py-2 text-xs font-medium rounded-sm ${minutes === m ? "bg-muted text-foreground" : "text-muted-foreground"}`}
                    >
                      {m}m
                    </button>
                  ))}
                </div>
              </div>
              <Button size="sm" onClick={handleLaunch} disabled={loading || !question.trim() || gate.level === "BLOCKED"} className="shrink-0 min-h-11 rounded-lg">
                {loading ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Send className="size-4 mr-1.5" />}
                Launch Team
              </Button>
            </div>
          </div>
          {status && <p id="question-status" role="alert" className="rounded-lg border border-danger/40 bg-danger-subtle px-3 py-2 text-xs font-medium text-danger">{status}</p>}
        </div>

        <ModelPicker value={selection} onChange={setSelection} keyedProviderIds={enabledIds} />

        <div className="grid gap-3 sm:grid-cols-2">
          {EXAMPLES.map((ex, i) => (
            <Card key={i} className="cursor-pointer hover:-translate-y-0.5 bg-card" onClick={() => { setQuestion(ex); textareaRef.current?.focus() }}>
              <CardContent className="p-4 flex gap-3">
                <Sparkles className="size-4 shrink-0 text-brand mt-0.5" />
                <p className="text-sm text-muted-foreground">{ex}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
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
