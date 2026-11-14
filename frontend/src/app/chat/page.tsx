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
import { makeChatStatus, type ChatStatus } from "@/lib/chat-status"
import { ModelPicker, type ModelSelection } from "@/components/model-picker"
import { Button } from "@/components/ui/button"
import { ChatStatusMessage } from "@/components/chat-status-message"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Send, Settings, Clock, SlidersHorizontal, X, FileText, Plus, Paperclip, Globe, Sparkles, Check } from "lucide-react"
import { ChatIntroScene } from "@/components/chat-intro-scene"

const TIME_BUDGETS = [3, 5, 10, 15]
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

let chatIntroHasPlayedInCurrentSession = false

function ChatGreetingHeadline({ isRevealed }: { isRevealed: boolean }) {
  const [phase, setPhase] = useState<"welcome" | "dissolving" | "assembled">("welcome")

  useEffect(() => {
    if (!isRevealed) return
    const dissolveTimer = setTimeout(() => {
      setPhase("dissolving")
    }, 2200)

    const assembledTimer = setTimeout(() => {
      setPhase("assembled")
    }, 3000)

    return () => {
      clearTimeout(dissolveTimer)
      clearTimeout(assembledTimer)
    }
  }, [isRevealed])

  return (
    <div className="assembly-chat-greeting-stage select-none" aria-live="polite">
      <h1
        className={`assembly-greeting-welcome ${
          phase === "welcome"
            ? "is-visible"
            : phase === "dissolving"
              ? "is-dissolving"
              : "is-hidden"
        }`}
        aria-hidden={phase === "assembled"}
      >
        Welcome.
      </h1>

      <h1
        className={`assembly-greeting-assemble ${
          phase === "assembled" || phase === "dissolving"
            ? "is-visible"
            : "is-hidden"
        }`}
      >
        <span className="assembly-greeting-subtext mr-1.5">
          Assemble
        </span>{" "}
        your thoughts...
      </h1>
    </div>
  )
}

export default function Home() {
  const router = useRouter()

  const [isIntroComplete, setIsIntroComplete] = useState(() => chatIntroHasPlayedInCurrentSession)
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
  const [catalogTick, setCatalogTick] = useState(0)
  const [showModelSettings, setShowModelSettings] = useState(false)
  const [enabledIds, setEnabledIds] = useState<string[]>([])
  const [confirmedGateSignature, setConfirmedGateSignature] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [showContextPopover, setShowContextPopover] = useState(false)
  const contextMenuRef = useRef<HTMLDivElement>(null)
  const [showBudgetDropdown, setShowBudgetDropdown] = useState(false)
  const budgetMenuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showContextPopover && !showBudgetDropdown) return
    const handleClickOutside = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setShowContextPopover(false)
      }
      if (budgetMenuRef.current && !budgetMenuRef.current.contains(e.target as Node)) {
        setShowBudgetDropdown(false)
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowContextPopover(false)
        setShowBudgetDropdown(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [showContextPopover, showBudgetDropdown])

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

  useEffect(() => {
    const refreshKeys = () => {
      globalVault.allKeys().then((k) => {
        // Tavily is an optional search credential, not a runnable model provider.
        const modelProviderIds = Object.keys(k).filter((id) => id !== "tavily")
        setEnabledIds(modelProviderIds)
      }).catch(() => {})
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
      // The Tavily search key travels separately; it is never a model key.
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
      // Explicit terminal handling: only a completed run with a non-empty
      // final answer is presentable. Failed/incomplete runs keep their
      // failure history but never navigate to the active-run screen.
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
    <div className="assembly-chat-page flex min-h-screen flex-col bg-background">
      <main id="main-content" tabIndex={-1} className="assembly-chat-main flex w-full flex-1 flex-col justify-center">
        {/* Phase 1: Dedicated Loading Screen with ThreeUI Intro Pop Animation */}
        {!isIntroComplete && (
          <div
            className="assembly-chat-loading-overlay is-active"
            onClick={() => {
              chatIntroHasPlayedInCurrentSession = true
              setIsIntroComplete(true)
            }}
            title="Click to skip intro"
          >
            <ChatIntroScene
              onAssembled={() => {
                chatIntroHasPlayedInCurrentSession = true
                setIsIntroComplete(true)
              }}
            />
          </div>
        )}

        <div className={`assembly-chat-box-revealer ${isIntroComplete ? "is-revealed" : "is-hidden"}`}>
          <ChatGreetingHeadline isRevealed={isIntroComplete} />

          <div className="assembly-chat-form-stack space-y-3">
          {attachments.length > 0 && (
            <div className="assembly-attachment-list flex flex-wrap gap-2" aria-label="Selected attachments">
              {attachments.map((attachment) => (
                <div key={attachment.id} className="flex min-w-0 max-w-full items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-xs">
                  <FileText className="size-4 shrink-0 text-brand" aria-hidden />
                  <span className="max-w-48 truncate font-medium" title={attachment.filename}>{attachment.filename}</span>
                  <span className="shrink-0 text-muted-foreground">{attachment.filename.toLowerCase().endsWith(".env.example") ? "ENV.EXAMPLE" : (attachment.filename.split(".").pop() || "TEXT").toUpperCase()}</span>
                  <span className="shrink-0 text-muted-foreground">{Math.max(1, Math.ceil(attachment.size / 1024))} KB</span>
                  <button
                    type="button"
                    aria-label={`Remove ${attachment.filename}`}
                    disabled={loading}
                    onClick={() => setAttachments((current) => current.filter((item) => item.id !== attachment.id))}
                    className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="assembly-chat-composer-pill-bar">
            {/* Left: Plus context button with Cursor-style "Add Context" menu */}
            <div className="relative shrink-0" ref={contextMenuRef}>
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
                className={`assembly-composer-plus-btn shrink-0 ${showContextPopover ? "is-open" : ""}`}
                disabled={loading}
                onClick={() => setShowContextPopover((prev) => !prev)}
                aria-label={showContextPopover ? "Close context menu" : "Add context"}
                aria-expanded={showContextPopover}
                title="Add context"
              >
                <Plus className={`size-5 transition-transform duration-200 ${showContextPopover ? "rotate-45" : ""}`} />
                {attachments.length > 0 && !showContextPopover && (
                  <span className="assembly-composer-attach-badge">{attachments.length}</span>
                )}
              </button>

              {showContextPopover && (
                <div className="assembly-context-popover" role="menu" aria-label="Add context options">
                  <div className="assembly-context-popover-header">Add Context</div>

                  <button
                    type="button"
                    role="menuitem"
                    className="assembly-context-popover-item"
                    onClick={() => {
                      setShowContextPopover(false)
                      fileInputRef.current?.click()
                    }}
                  >
                    <Paperclip className="size-4" />
                    <span>Files</span>
                    {attachments.length > 0 && (
                      <span className="assembly-context-popover-item-badge">{attachments.length}</span>
                    )}
                  </button>

                  <button
                    type="button"
                    role="menuitem"
                    className="assembly-context-popover-item"
                    onClick={() => {
                      setShowContextPopover(false)
                      setMinutes(15)
                      setStatus(makeChatStatus("Deep research mode enabled (15m budget with adversarial debate).", "info"))
                    }}
                  >
                    <Sparkles className="size-4" />
                    <span>Deep Research</span>
                    <span className="assembly-context-popover-item-badge">15m</span>
                  </button>

                  <button
                    type="button"
                    role="menuitem"
                    className="assembly-context-popover-item"
                    onClick={() => {
                      setShowContextPopover(false)
                      setStatus(makeChatStatus("Web sources active: Assembly will query live web evidence during debate rounds.", "info"))
                    }}
                  >
                    <Globe className="size-4" />
                    <span>Web Sources</span>
                    <span className="assembly-context-popover-item-badge">Live</span>
                  </button>

                  <button
                    type="button"
                    role="menuitem"
                    className="assembly-context-popover-item"
                    onClick={() => {
                      setShowContextPopover(false)
                      setShowModelSettings(true)
                    }}
                  >
                    <SlidersHorizontal className="size-4" />
                    <span>Models & Roles</span>
                  </button>
                </div>
              )}
            </div>

            {/* Middle: Seamless input field matching Image 2 */}
            <label htmlFor="research-question" className="sr-only">Research question</label>
            <textarea
              id="research-question"
              ref={textareaRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  if (!loading && (question.trim() || attachments.length > 0) && gate.level !== "BLOCKED") {
                    handleLaunch()
                  }
                }
              }}
              placeholder="Ask anything..."
              aria-describedby="question-status"
              className="assembly-composer-input resize-none"
              rows={1}
              maxLength={2000}
              required
            />

            {/* Right: Actions group (Time Budget Dropdown button + Run pill button) */}
            <div className="flex items-center gap-2 shrink-0">
              <div className="relative" ref={budgetMenuRef}>
                <button
                  type="button"
                  onClick={() => setShowBudgetDropdown((prev) => !prev)}
                  className={`assembly-composer-budget-btn ${showBudgetDropdown ? "is-open" : ""}`}
                  aria-label="Select investigation time budget"
                  aria-expanded={showBudgetDropdown}
                  title={`Time budget: ${minutes} mins`}
                >
                  <Clock className="size-5 transition-colors" />
                </button>

                {showBudgetDropdown && (
                  <div className="assembly-budget-dropdown" role="menu" aria-label="Choose time budget">
                    <div className="assembly-budget-dropdown-header">Time Budget</div>
                    {TIME_BUDGETS.map((m) => (
                      <button
                        key={m}
                        type="button"
                        role="menuitem"
                        className={`assembly-budget-dropdown-item ${minutes === m ? "is-active" : ""}`}
                        onClick={() => {
                          setMinutes(m)
                          setShowBudgetDropdown(false)
                        }}
                      >
                        <Clock className="size-3.5 text-muted-foreground" />
                        <span>{m} mins</span>
                        {minutes === m && <Check className="size-3.5 ml-auto text-amber-400" />}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={handleLaunch}
                disabled={loading || (!question.trim() && attachments.length === 0) || gate.level === "BLOCKED"}
                className="assembly-composer-run-pill shrink-0"
                aria-label="Run investigation"
              >
                {loading ? (
                  <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : (
                  <span className="flex items-center gap-1.5">
                    <Send className="size-3.5" />
                    <span className="font-semibold text-xs tracking-wide uppercase">Run</span>
                  </span>
                )}
              </button>
            </div>
          </div>

          <div className="assembly-chat-banners-stack space-y-3">
            {gate.families_count === 0 && (
              <div className="assembly-chat-warning-banner flex items-center justify-between gap-3 rounded-xl border px-3 py-2.5">
                <p className="text-xs font-medium text-warning">
                  Set up provider keys in Settings. Two ready model families are the minimum for a normal run; three are recommended. Providers with unverified quota limits do not count toward readiness.
                </p>
                <Button variant="outline" size="sm" onClick={() => router.push("/settings")} className="shrink-0 assembly-dark-glass-btn">
                  <Settings className="mr-1.5 size-3.5" />
                  Add keys
                </Button>
              </div>
            )}

            <div
              data-testid="diversity-chip"
              className={`assembly-readiness-chip flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 py-2 text-xs ${
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
              <div>
                <ServerStatusBanner url={env.apiUrl} onRetry={() => setCatalogTick((t) => t + 1)} />
              </div>
            )}
          </div>

          {status && (
            <ChatStatusMessage status={status} />
          )}
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
