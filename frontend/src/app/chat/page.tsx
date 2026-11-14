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
import { evaluateGate, gateChipText } from "@/lib/diversity-gate"
import {
  estimateAttachmentContextChars,
  MAX_ATTACHMENT_CONTEXT_CHARS,
  SUPPORTED_ATTACHMENT_EXTENSIONS,
  validateAttachmentBatch,
} from "@/lib/attachments"
import { failureMessage, isPresentableRun } from "@/lib/run-outcome"
import { makeChatStatus, type ChatStatus } from "@/lib/chat-status"
import { ModelPicker, type ModelSelection } from "@/components/model-picker"
import { Button } from "@/components/ui/button"
import { ChatStatusMessage } from "@/components/chat-status-message"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ArrowUp, Send, SlidersHorizontal, Paperclip, X, FileText } from "lucide-react"

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
  const attachmentsRef = useRef<DraftAttachment[]>([])
  const attachmentQueueRef = useRef<Promise<void>>(Promise.resolve())
  const [isValidatingAttachments, setIsValidatingAttachments] = useState(false)
  const pendingValidationCountRef = useRef(0)
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
      }).catch(() => { })
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

  const handleRemoveAttachment = (id: string) => {
    const next = attachmentsRef.current.filter((item) => item.id !== id)
    attachmentsRef.current = next
    setAttachments(next)
  }

  const handleFilesSelected = async (files: FileList | null) => {
    if (!files?.length) return
    const picked = Array.from(files)
    pendingValidationCountRef.current += 1
    setIsValidatingAttachments(true)
    const runBatch = async () => {
      try {
        const result = await validateAttachmentBatch(() => attachmentsRef.current, picked)
        if (result.accepted.length > 0) {
          const next = [...attachmentsRef.current, ...result.accepted]
          attachmentsRef.current = next
          setAttachments(next)
        }
        const estimatedPromptChars = estimateAttachmentContextChars(
          attachmentsRef.current,
        )
        const truncationNotice =
          estimatedPromptChars > MAX_ATTACHMENT_CONTEXT_CHARS
            ? ` Formatted attachment context exceeds ${MAX_ATTACHMENT_CONTEXT_CHARS.toLocaleString()} characters, so extra content will be truncated before sending to models.`
            : ""
        if (result.accepted.length > 0 && result.errors.length > 0) {
          setStatus(
            makeChatStatus(
              `${result.accepted.length} file${result.accepted.length === 1 ? "" : "s"} ready. ${result.errors.join(" ")}${truncationNotice}`,
              "warning",
            ),
          )
        } else if (result.errors.length > 0) {
          setStatus(makeChatStatus(result.errors.join(" "), "warning"))
        } else if (result.accepted.length > 0) {
          setStatus(
            makeChatStatus(
              `${result.accepted.length} file${result.accepted.length === 1 ? "" : "s"} ready. File contents remain in memory for this investigation.${truncationNotice}`,
              truncationNotice ? "warning" : "info",
            ),
          )
        }
        if (fileInputRef.current) fileInputRef.current.value = ""
      } finally {
        pendingValidationCountRef.current = Math.max(0, pendingValidationCountRef.current - 1)
        if (pendingValidationCountRef.current === 0) {
          setIsValidatingAttachments(false)
        }
      }
    }
    const nextQueue = attachmentQueueRef.current.then(runBatch, runBatch)
    attachmentQueueRef.current = nextQueue
    await nextQueue
  }

  const handleLaunch = async () => {
    if (loading) return
    // Wait for any queued attachment validation to settle before launching
    await attachmentQueueRef.current
    const activeAttachments = attachmentsRef.current
    if ((!question.trim() && activeAttachments.length === 0) || loading) return
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
          attachments: activeAttachments.map(({ filename, media_type, content }) => ({ filename, media_type, content })),
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
          attachments: activeAttachments.map(({ filename, media_type, size }) => ({
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
        attachments: activeAttachments.map(({ filename, media_type, size }) => ({
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

  return (
    <div className="mn-chat">
      <main id="main-content" tabIndex={-1} className="mn-chat-main">
        <div className="mn-chat-center">
          <h1 className="mn-hello">What&apos;s on your mind today?</h1>


          <div className="mn-dock">
            {status && (
              <div className="mn-status" id="question-status">
                <ChatStatusMessage status={status} />
              </div>
            )}

            <div
              data-testid="diversity-chip"
              data-level={catalogLoading ? "LOADING" : catalogFailed ? "WARN" : gate.level}
              className="mn-meta"
              aria-live="polite"
            >
              {catalogLoading ? (
                <span>Checking provider keys…</span>
              ) : catalogFailed ? (
                <span className="mn-meta-warn">
                  Provider status unavailable ·{" "}
                  <button type="button" onClick={() => setCatalogTick((t) => t + 1)}>
                    Retry
                  </button>
                </span>
              ) : (
                <>
                  <span>{gateChipText(gate)}</span>
                  {gate.level === "DEGRADED" && !degradedConfirmed && (
                    <button
                      type="button"
                      className="mn-link"
                      data-testid="degraded-confirm"
                      onClick={() => setConfirmedGateSignature(gateSignature)}
                    >
                      Run anyway
                    </button>
                  )}
                  {gate.families_count === 0 && (
                    <Link href="/settings" className="mn-link">
                      Add provider keys
                    </Link>
                  )}
                </>
              )}
            </div>

            {runHint && (
              <p className="mn-hint" id="run-hint">
                {runHint}
              </p>
            )}

            {catalogFailed && (
              <div className="mn-alert" role="alert">
                <span>
                  Can&apos;t reach the Assembly server at {env.apiUrl}. Check that the backend is running.
                </span>
                <button type="button" onClick={() => setCatalogTick((t) => t + 1)}>
                  Retry
                </button>
              </div>
            )}

            <div className="mn-suggestions" aria-label="Suggested questions">
              <span>Try</span>
              {EXAMPLES.map((example) => (
                <button
                  key={example.label}
                  type="button"
                  className="mn-chip"
                  title={example.question}
                  onClick={() => {
                    setQuestion(example.question)
                    textareaRef.current?.focus()
                  }}
                >
                  {example.label}
                </button>
              ))}
            </div>
            {attachments.length > 0 && (
              <div className="mn-attachments" aria-label="Selected attachments">
                {attachments.map((attachment) => (
                  <div key={attachment.id} className="mn-attachment">
                    <FileText className="size-3.5 shrink-0 text-brand" aria-hidden />
                    <b title={attachment.filename}>{attachment.filename}</b>
                    <span>{Math.max(1, Math.ceil(attachment.size / 1024))} KB</span>
                    <button
                      type="button"
                      aria-label={`Remove ${attachment.filename}`}
                      disabled={loading}
                      onClick={() => handleRemoveAttachment(attachment.id)}
                      className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                    >
                      <X className="size-3.5" aria-hidden />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form
              className="mn-composer"
              onSubmit={(event) => {
                event.preventDefault()
                void handleLaunch()
              }}
            >
              <label htmlFor="research-question" className="sr-only">
                Ask a question (max 2000 characters)
              </label>
              <textarea
                id="research-question"
                ref={textareaRef}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault()
                    void handleLaunch()
                  }
                }}
                placeholder="Ask Assembly"
                aria-describedby="question-status"
                className="mn-input"
                rows={1}
                maxLength={2000}
                required
              />

              <div className="mn-composer-tools">
                <div className="mn-tools-left">
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    aria-label="Choose investigation attachments"
                    accept={[...SUPPORTED_ATTACHMENT_EXTENSIONS].map((ext) => `.${ext}`).join(",")}
                    className="sr-only"
                    disabled={loading}
                    onChange={(event) => void handleFilesSelected(event.currentTarget.files)}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="min-h-9"
                    disabled={loading}
                    onClick={() => fileInputRef.current?.click()}
                    aria-label="Attach files"
                    title="Attach files"
                  >
                    <Paperclip className="size-[18px]" aria-hidden />
                  </Button>
                  <button
                    type="button"
                    className="mn-pill"
                    onClick={() => setShowModelSettings(true)}
                    aria-haspopup="dialog"
                    aria-label="Open model and role settings"
                  >
                    <SlidersHorizontal className="size-3.5" aria-hidden />
                    {selection.selected.length > 0 ? `${selection.selected.length} models` : "Models · Auto"}
                  </button>
                  <div className="mn-budget" role="group" aria-label="Time budget">
                    {TIME_BUDGETS.map((value) => (
                      <button
                        key={value}
                        type="button"
                        className="mn-budget-opt"
                        onClick={() => setMinutes(value)}
                        aria-pressed={minutes === value}
                        aria-label={`${value} minutes, ${BUDGET_COPY[value]}`}
                        title={BUDGET_COPY[value]}
                      >
                        {value}m
                      </button>
                    ))}
                  </div>
                </div>
                <Button
                  size="default"
                  onClick={handleLaunch}
                  disabled={loading || isValidatingAttachments || (!question.trim() && attachments.length === 0) || gate.level === "BLOCKED"}
                  className="assembly-chat-run-button min-h-10 rounded-xl px-4"
                >
                  {loading ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Send className="mr-1.5 size-4" />}
                  {loading ? "Running…" : isValidatingAttachments ? "Checking…" : "Run"}
                </Button>

                <button
                  type="submit"
                  className="mn-send"
                  disabled={loading || missingQuestion || catalogLoading || catalogFailed || gate.level === "BLOCKED"}
                  aria-label={loading ? "Running" : "Start run"}
                  aria-describedby={runHint ? "run-hint" : undefined}
                >
                  {loading ? (
                    <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <ArrowUp className="size-[18px]" aria-hidden />
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
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
            <Button variant="outline" onClick={() => setShowModelSettings(false)}>
              Done
            </Button>
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
