"use client"

import React, { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
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
import { makeChatStatus, type ChatStatus } from "@/lib/chat-status"
import { ModelPicker, type ModelSelection } from "@/components/model-picker"
import { Button } from "@/components/ui/button"
import { ChatStatusMessage } from "@/components/chat-status-message"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { TrafficDots } from "@/components/cinematic/window-card"
import { HistoryQuick } from "@/components/cinematic/history-quick"
import {
  ArrowRight,
  Check,
  FileText,
  Paperclip,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Users,
  X,
} from "lucide-react"

const EXAMPLES = [
  { label: "Quantum computing", question: "Will quantum computing achieve commercial advantage before 2030?" },
  { label: "Superconductors", question: "What are the most viable methods for replicating room-temperature superconductors?" },
  { label: "AGI timeline", question: "Analyse the timeline and economic impacts of AGI given current scaling laws." },
  { label: "EV battery chemistry", question: "Which battery chemistry is most likely to replace Lithium-Ion in EVs by 2035?" },
]

const TIME_BUDGETS = [3, 5, 10, 15] as const
const BUDGET_COPY: Record<(typeof TIME_BUDGETS)[number], string> = {
  3: "Quick",
  5: "Balanced",
  10: "Thorough",
  15: "Deep dive",
}
const MAX_ATTACHMENTS = 5
const MAX_FILE_BYTES = 256 * 1024
const MAX_TOTAL_BYTES = 384 * 1024
const SUPPORTED_EXTENSIONS = new Set([
  "txt", "md", "csv", "json", "log", "py", "js", "jsx", "ts", "tsx",
  "html", "css", "yml", "yaml", "toml", "ini", "cfg", "conf", "xml",
  "sql", "sh", "ps1", "bat", "env.example",
])

type DraftAttachment = {
  id: string
  filename: string
  media_type: string
  content: string
  size: number
}

export default function Home() {
  const router = useRouter()

  const [question, setQuestion] = useState("")
  const [attachments, setAttachments] = useState<DraftAttachment[]>([])
  const [minutes, setMinutes] = useState(5)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<ChatStatus | null>(null)
  const [selection, setSelection] = useState<ModelSelection>({ selected: [], pins: {} })
  const [privacyAcked, setPrivacyAcked] = useState(false)
  const [showPrivacy, setShowPrivacy] = useState(false)
  const [catalogNotes, setCatalogNotes] = useState<{ id: string; privacy_note?: string | null }[]>([])
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [catalogFailed, setCatalogFailed] = useState(false)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogTick, setCatalogTick] = useState(0)
  const [showModelSettings, setShowModelSettings] = useState(false)
  const [enabledIds, setEnabledIds] = useState<string[]>([])
  const [hasSearchKey, setHasSearchKey] = useState(false)
  const [confirmedGateSignature, setConfirmedGateSignature] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const appMode = env.NEXT_PUBLIC_APP_MODE === "desktop" ? "desktop" : "web"

  const gate = React.useMemo(() => {
    const enabled = new Set(enabledIds)
    const fams: string[] = []
    if (catalog) {
      for (const p of catalog.providers) {
        if (!p.enabled || !p.limits_ready || !enabled.has(p.id)) continue
        for (const m of p.models) {
          if (selection.selected.length > 0 && !selection.selected.includes(m.id)) continue
          if (!fams.includes(m.family)) fams.push(m.family)
        }
      }
    }
    const runnableProviderCount = catalog?.providers.filter(
      (provider) => provider.enabled && provider.limits_ready && enabled.has(provider.id),
    ).length ?? 0
    return evaluateGate(fams, runnableProviderCount)
  }, [catalog, enabledIds, selection.selected])

  const gateSignature = JSON.stringify({
    level: gate.level,
    reasons: gate.reasons,
    enabledIds: [...enabledIds].sort(),
    selected: [...selection.selected].sort(),
    pins: selection.pins,
  })
  const degradedConfirmed = confirmedGateSignature === gateSignature
  const missingQuestion = !question.trim() && attachments.length === 0
  const runHint = missingQuestion
    ? "Write a question to start."
    : catalogLoading
      ? "Checking provider keys…"
      : catalogFailed
        ? "Provider status is unavailable. Retry the connection above."
        : gate.level === "BLOCKED"
          ? "Add at least two provider keys in Settings to enable Run."
          : gate.level === "DEGRADED" && !degradedConfirmed
            ? "Choose Run anyway above to start with one model family."
            : null

  useEffect(() => {
    const refreshKeys = () => {
      globalVault.allKeys().then((k) => {
        const modelProviderIds = Object.keys(k).filter((id) => id !== "tavily")
        setEnabledIds(modelProviderIds)
        setHasSearchKey(Boolean(k.tavily))
      }).catch(() => {})
    }
    refreshKeys()
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
      .finally(() => setCatalogLoading(false))
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

  const handleFilesSelected = async (files: FileList | null) => {
    if (!files?.length) return
    const picked = Array.from(files)
    if (attachments.length + picked.length > MAX_ATTACHMENTS) {
      setStatus(makeChatStatus(`Attach up to ${MAX_ATTACHMENTS} files per investigation.`, "info"))
      if (fileInputRef.current) fileInputRef.current.value = ""
      return
    }
    let total = attachments.reduce((sum, item) => sum + item.size, 0)
    const accepted: DraftAttachment[] = []
    for (const file of picked) {
      const lower = file.name.toLowerCase()
      const extension = lower.endsWith(".env.example")
        ? "env.example"
        : lower.includes(".") ? lower.split(".").pop() ?? "" : ""
      if (!SUPPORTED_EXTENSIONS.has(extension)) {
        setStatus(
          makeChatStatus(
            `${file.name}: unsupported type. Choose a text, Markdown, CSV, JSON, log, or source/configuration file.`,
            "warning",
          ),
        )
        continue
      }
      if (file.size <= 0) {
        setStatus(makeChatStatus(`${file.name}: file is empty.`, "warning"))
        continue
      }
      if (file.size > MAX_FILE_BYTES) {
        setStatus(
          makeChatStatus(`${file.name}: file exceeds the 256 KiB per-file limit.`, "warning"),
        )
        continue
      }
      total += file.size
      if (total > MAX_TOTAL_BYTES) {
        total -= file.size
        setStatus(makeChatStatus("Attachments exceed the 384 KiB combined limit.", "warning"))
        continue
      }
      try {
        const content = await file.text()
        const hasUnsupportedControls = Array.from(content).some((character) => {
          const code = character.charCodeAt(0)
          return (code < 32 && ![9, 10, 12, 13].includes(code)) || code === 127
        })
        if (hasUnsupportedControls) {
          total -= file.size
          setStatus(
            makeChatStatus(
              `${file.name}: binary or unsupported control characters aren't supported.`,
              "warning",
            ),
          )
          continue
        }
        if (extension === "json") {
          try { JSON.parse(content) } catch {
            total -= file.size
            setStatus(makeChatStatus(`${file.name}: invalid JSON.`, "warning"))
            continue
          }
        }
        if (!content.trim()) {
          total -= file.size
          setStatus(makeChatStatus(`${file.name}: file is empty.`, "warning"))
          continue
        }
        accepted.push({
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}-${accepted.length}`,
          filename: file.name,
          media_type: file.type || "text/plain",
          content,
          size: file.size,
        })
      } catch {
        total -= file.size
        setStatus(makeChatStatus(`${file.name}: couldn't read this file.`, "warning"))
      }
    }
    if (accepted.length) {
      setAttachments((current) => [...current, ...accepted])
      setStatus(
        makeChatStatus(
          `${accepted.length} file${accepted.length === 1 ? "" : "s"} ready. File contents remain in memory for this investigation.`,
          "info",
        ),
      )
    }
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const handleLaunch = async () => {
    if ((!question.trim() && attachments.length === 0) || loading) return
    if (!privacyAcked) {
      setShowPrivacy(true)
      setStatus(makeChatStatus("Please acknowledge the privacy notice first.", "info"))
      return
    }
    if (gate.level === "BLOCKED") {
      setStatus(makeChatStatus(gate.reasons[0] ?? "No model families ready.", "info"))
      return
    }
    if (gate.level === "DEGRADED" && !degradedConfirmed) {
      setStatus(makeChatStatus("Confirm the single-family run below before launching.", "info"))
      return
    }
    setLoading(true)
    setStatus(makeChatStatus("Checking capacity…", "progress"))
    let finalAnswer = ""
    let consensus: number | null = null
    let confidence: "High" | "Moderate" | "Low" | null = null
    let agentCount: number | null = null
    let providers: string[] = []
    let debateRounds: number | null = null
    let tokens: number | null = null
    let elapsedSeconds: number | null = null
    let verification: {
      agents?: number
      families?: number
      rounds?: number
      disagreements_resolved?: number
      sources_verified?: number
    } | null = null
    let streamStarted = false
    const runId = `local-${Date.now()}`
    const questionForRun = question.trim() || "Analyze the attached files and summarize their key contents, important claims, and uncertainties."
    try {
      const keys = await globalVault.allKeys()
      const { tavily, ...providerKeys } = keys
      const searchKeys = tavily ? { tavily } : undefined
      const usage: UsageEntry[] = await storage.getUsage()
      const preflight = await ApiClient.preflight(
        questionForRun,
        minutes,
        usage,
        providerKeys,
        { selected: selection.selected, pins: selection.pins },
      )
      if (!preflight.feasible) {
        setStatus(makeChatStatus(`Not feasible: ${preflight.explanation ?? "quota exhausted"}`, "error"))
        setLoading(false)
        return
      }
      setStatus(makeChatStatus("Running team… (streaming)", "progress"))
      const result = await ApiClient.startRunStream(
        {
          question: questionForRun,
          minutes,
          providerKeys,
          searchKeys,
          attachments: attachments.map(({ filename, media_type, content }) => ({ filename, media_type, content })),
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
            verification?: {
              agents?: number
              families?: number
              rounds?: number
              disagreements_total?: number
              disagreements_resolved?: number
              sources_verified?: number
            }
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
            verification = event.data?.verification ?? null
            debateRounds = event.data?.debate_rounds ?? event.data?.verification?.rounds ?? null
            tokens = event.data?.tokens_used ?? null
            elapsedSeconds = event.data?.elapsed_seconds ?? null
          }
          if (event.event_type === "run.finished" && Array.isArray(event.usage)) {
            void storage.setUsage(event.usage)
          }
        },
      )
      if (!isPresentableRun({ status: result.status, finalAnswer })) {
        const failedStatus = result.status === "completed" ? "failed" : result.status
        await storage.saveHistory({
          id: runId,
          question: questionForRun,
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
          disagreements: [],
          attachments: attachments.map(({ filename, media_type, size }) => ({
            filename,
            media_type: media_type && media_type.length <= 100 ? media_type : "text/plain",
            size_bytes: size,
          })),
        })
        setStatus(
          makeChatStatus(
            failureMessage({
              status: failedStatus,
              stage: result.stage,
              errorCode: result.errorCode,
            }),
            "error",
          ),
        )
        setLoading(false)
        return
      }
      await storage.saveHistory({
        id: runId,
        question: questionForRun,
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
        verification: verification ?? undefined,
        disagreements: [],
        attachments: attachments.map(({ filename, media_type, size }) => ({
          filename,
          media_type: media_type && media_type.length <= 100 ? media_type : "text/plain",
          size_bytes: size,
        })),
      })
      router.push(`/executions?id=${runId}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Run failed"
      const aborted =
        (err instanceof DOMException && err.name === "AbortError") ||
        /abort/i.test(message)
      if (streamStarted) {
        try {
          await storage.saveHistory({
            id: runId,
            question: questionForRun,
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
            attachments: attachments.map(({ filename, media_type, size }) => ({
              filename,
              media_type: media_type && media_type.length <= 100 ? media_type : "text/plain",
              size_bytes: size,
            })),
          })
        } catch {
          // Storage failure must not hide the original error.
        }
      }
      setStatus(makeChatStatus(message, "error"))
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!loading) return
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener("beforeunload", onBeforeUnload)
    return () => window.removeEventListener("beforeunload", onBeforeUnload)
  }, [loading])

  const readinessOk = gate.level === "OK"
  const readinessValue = Math.min(3, gate.families_count)
  const readinessText = readinessOk
    ? "Keys, models and quota are fine"
    : catalogLoading
      ? "Checking keys and provider quota…"
      : catalogFailed
        ? "Provider status is unavailable"
        : gate.reasons[0] ?? "Add provider keys to start"
  const searchText = hasSearchKey ? "Web search connected" : "Web search not set up (optional)"

  return (
    <div className="cin-page cin-workspace-page">
      <main id="main-content" tabIndex={-1} className="cin-main cin-shell cin-page-inner">
        <header className="cin-page-head">
          <div className="cin-page-head-copy">
            <span className="cin-kicker">01 — Ask</span>
            <h1 className="cin-title">What do you want to know?</h1>
            <p className="cin-lede">
              One hard question. A temporary team from different model families works it separately, challenges
              the weak spots, and leaves you one sourced answer.
            </p>
          </div>
          <div className="cin-page-head-aside">
            <span className="cin-page-number">02 / 08</span>
            <div className="flex flex-wrap justify-end gap-2">
              <span className="cin-chip">
                <Users className="size-3.5" aria-hidden />
                Independent passes
              </span>
              <span className="cin-chip">
                <Sparkles className="size-3.5" aria-hidden />
                One answer
              </span>
            </div>
          </div>
        </header>

        {!catalogLoading && !catalogFailed && gate.families_count === 0 && (
          <div className="cin-run-banner mb-5" role="status">
            <span>
              <strong>Add provider keys to start.</strong> Two model families are the minimum; three are
              recommended. Saved keys stay in this browser.
            </span>
            <Button variant="outline" size="sm" onClick={() => router.push("/settings")} className="ml-auto shrink-0">
              <Settings className="mr-1.5 size-3.5" />
              Add keys
            </Button>
          </div>
        )}

        <div
          data-testid="diversity-chip"
          data-level={catalogLoading ? "LOADING" : catalogFailed ? "WARN" : gate.level}
          className="mb-5 flex flex-wrap items-center gap-3 text-sm text-muted-foreground"
          aria-live="polite"
        >
          {catalogLoading ? (
            <span className="cin-chip">Checking provider keys…</span>
          ) : catalogFailed ? (
            <span className="cin-chip cin-chip-warning">Provider status unavailable — retry the connection above.</span>
          ) : (
            <>
              <span className={`cin-chip ${readinessOk ? "cin-chip-success" : "cin-chip-warning"}`}>
                {gateChipText(gate)}
              </span>
              {gate.level !== "OK" && gate.families_count > 0 && (
                <span className="text-xs">{gate.reasons[0]}</span>
              )}
              {gate.level === "DEGRADED" && !degradedConfirmed && (
                <Button
                  variant="outline"
                  size="sm"
                  data-testid="degraded-confirm"
                  onClick={() => setConfirmedGateSignature(gateSignature)}
                >
                  Run anyway
                </Button>
              )}
            </>
          )}
        </div>

        {catalogFailed && (
          <div className="mb-5">
            <ServerStatusBanner url={env.apiUrl} onRetry={() => setCatalogTick((t) => t + 1)} />
          </div>
        )}

        <div className="cin-workspace-grid">
          <div className="min-w-0">
            {attachments.length > 0 && (
              <div className="cin-attachments" aria-label="Selected attachments">
                {attachments.map((attachment) => (
                  <div key={attachment.id} className="cin-attachment">
                    <FileText className="size-3.5 shrink-0 text-brand" aria-hidden />
                    <b title={attachment.filename}>{attachment.filename}</b>
                    <span>{attachment.filename.toLowerCase().endsWith(".env.example") ? "ENV.EXAMPLE" : (attachment.filename.split(".").pop() || "TEXT").toUpperCase()}</span>
                    <span>{Math.max(1, Math.ceil(attachment.size / 1024))} KB</span>
                    <button
                      type="button"
                      aria-label={`Remove ${attachment.filename}`}
                      disabled={loading}
                      onClick={() => setAttachments((current) => current.filter((item) => item.id !== attachment.id))}
                    >
                      <X className="size-3.5" aria-hidden />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <section className="cin-window cin-composer" aria-labelledby="question-label">
              <div className="cin-window-bar">
                <TrafficDots />
                <span className="cin-window-title">New investigation</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {question.length.toString().padStart(4, "0")} / 2000
                </span>
              </div>
              <div className="cin-window-body">
                <div className="cin-composer-label">
                  <span id="question-label">Your question</span>
                  <span className="hidden sm:inline">Plain text · Markdown · source files</span>
                </div>
                <label htmlFor="research-question" className="sr-only">Research question (max 2000 characters)</label>
                <textarea
                  id="research-question"
                  ref={textareaRef}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Should our startup adopt a multi-region database now, or wait until we reach 100k users?"
                  aria-describedby="question-status"
                  className="cin-question-input"
                  rows={4}
                  maxLength={2000}
                  required
                />

                <div className="cin-suggestion-pop" aria-hidden="true">
                  <div className="cin-window-bar">
                    <TrafficDots />
                    <span className="cin-window-title">Suggestion</span>
                  </div>
                  <div className="cin-window-body">
                    <p>Add your expected user count for a sharper answer.</p>
                  </div>
                </div>

                <div className="cin-composer-tools">
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    aria-label="Choose investigation attachments"
                    accept={[...SUPPORTED_EXTENSIONS].map((ext) => `.${ext}`).join(",")}
                    className="sr-only"
                    disabled={loading}
                    onChange={(event) => void handleFilesSelected(event.currentTarget.files)}
                  />
                  <button
                    type="button"
                    className="cin-tool"
                    disabled={loading || attachments.length >= MAX_ATTACHMENTS}
                    onClick={() => fileInputRef.current?.click()}
                    aria-label="Attach files"
                  >
                    <Paperclip aria-hidden />
                    File
                  </button>
                  <button
                    type="button"
                    className="cin-tool"
                    onClick={() => setShowModelSettings(true)}
                    aria-haspopup="dialog"
                    aria-label="Open model and role settings"
                  >
                    <SlidersHorizontal aria-hidden />
                    Models{selection.selected.length > 0 ? ` · ${selection.selected.length}` : " · Auto"}
                  </button>
                  <span className="cin-tool-hint">
                    Attach up to {MAX_ATTACHMENTS} files · 384 KiB total
                  </span>
                </div>
              </div>
            </section>

            {status && (
              <div className="cin-status-slot" id="question-status">
                <ChatStatusMessage status={status} />
              </div>
            )}

            <section className="cin-budget-block" aria-labelledby="budget-title">
              <div className="cin-budget-title">
                <h2 id="budget-title">How long can we take?</h2>
                <span className="cin-page-number">Hard cutoff</span>
              </div>
              <div className="cin-budget-row" role="group" aria-label="Time budget">
                {TIME_BUDGETS.map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setMinutes(value)}
                    aria-pressed={minutes === value}
                    aria-label={`${value} minutes`}
                    className="cin-budget"
                  >
                    <span className="cin-budget-num">{value}</span>
                    <span className="cin-budget-copy">
                      <b>{value} min</b>
                      <span>{BUDGET_COPY[value]}</span>
                    </span>
                  </button>
                ))}
              </div>
            </section>

            <section className="cin-examples" aria-label="Suggested questions">
              <div className="cin-examples-head">
                <span>Need a starting point?</span>
                <span>{EXAMPLES.length.toString().padStart(2, "0")} prompts</span>
              </div>
              <div className="cin-example-grid">
                {EXAMPLES.map((example, index) => (
                  <button
                    key={example.label}
                    type="button"
                    onClick={() => { setQuestion(example.question); textareaRef.current?.focus() }}
                    className="cin-example"
                    title={example.question}
                  >
                    <span className="cin-example-label">{String(index + 1).padStart(2, "0")} · {example.label}</span>
                    <p>{example.question}</p>
                    <ArrowRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                  </button>
                ))}
              </div>
            </section>
          </div>

          <aside className="min-w-0" aria-label="Run configuration">
            <div className="cin-window">
              <div className="cin-window-bar">
                <TrafficDots />
                <span className="cin-window-title">Run check</span>
              </div>
              <div className="cin-readiness">
                <div className="cin-readiness-ring" aria-hidden="true">
                  <span
                    className="cin-readiness-check"
                    style={{ opacity: readinessValue === 0 ? 0.55 : 1 }}
                  >
                    <Check className="size-10" strokeWidth={2.4} />
                  </span>
                </div>
                <p className="cin-readiness-status">{readinessText}</p>
                <p className="cin-readiness-note">{searchText}</p>

                <div className="cin-readiness-lines">
                  <div className="cin-readiness-line">
                    <span>Families ready</span>
                    <b>{catalogLoading ? "…" : `${gate.families_count} / 3`}</b>
                  </div>
                  <div className="cin-readiness-line">
                    <span>Providers</span>
                    <b>{catalogLoading ? "…" : gate.providers_count}</b>
                  </div>
                  <div className="cin-readiness-line">
                    <span>Budget</span>
                    <b>{minutes} min</b>
                  </div>
                  <div className="cin-readiness-line">
                    <span>Debate rounds</span>
                    <b>Only if needed</b>
                  </div>
                </div>

                <Button
                  onClick={handleLaunch}
                  disabled={loading || missingQuestion || catalogLoading || catalogFailed || gate.level === "BLOCKED"}
                  className="cin-btn cin-btn-primary cin-run-cta"
                  aria-label={loading ? "Running" : "Run"}
                  aria-describedby={runHint ? "run-hint" : undefined}
                >
                  <span>{loading ? "Running the team…" : `Start run · about ${minutes} min`}</span>
                  {loading
                    ? <span className="size-3.5 animate-spin rounded-full border border-current border-t-transparent" />
                    : <ArrowRight className="size-4" aria-hidden />}
                </Button>

                {runHint && (
                  <p className="cin-run-hint" id="run-hint">
                    {runHint}
                  </p>
                )}

                <p className="cin-run-hint">
                  Not a sole source for medical, legal, financial or security-critical decisions. Your
                  question is sent only to the providers you choose.
                </p>
              </div>
            </div>

            <div className="cin-window mt-4">
              <div className="cin-window-bar">
                <TrafficDots />
                <span className="cin-window-title">What the team does</span>
              </div>
              <div className="px-5 py-2">
                <div className="cin-estimate">
                  <div className="cin-estimate-row"><span>Agents</span><b>4–5 temporary roles</b></div>
                  <div className="cin-estimate-row"><span>Families</span><b>3+ independent</b></div>
                  <div className="cin-estimate-row"><span>Evidence</span><b>Verified sources</b></div>
                  <div className="cin-estimate-row"><span>Output</span><b>One cited answer</b></div>
                </div>
              </div>
            </div>

            <p className="mt-4 text-center text-xs leading-relaxed text-muted-foreground">
              Keys stay in your browser.{" "}
              <Link href="/settings" className="font-semibold text-brand hover:underline">
                Review providers
              </Link>
            </p>
          </aside>
        </div>

        <HistoryQuick />
      </main>

      <Dialog open={showModelSettings} onOpenChange={setShowModelSettings}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Models and roles</DialogTitle>
            <DialogDescription>
              Auto selection by default. Optional model overrides and role pins.
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
