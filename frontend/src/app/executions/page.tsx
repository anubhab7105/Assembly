"use client"

import React, { Suspense } from "react"
import Link from "next/link"
import { useSearchParams, useRouter } from "next/navigation"
import { useExecution } from "@/hooks/use-execution"
import { ApiClient } from "@/lib/api-client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Users,
  AlertTriangle,
  WifiOff,
  Link as LinkIcon,
  MessageSquareWarning,
  CheckCircle2,
  XCircle,
  Activity,
  X,
  PlayCircle,
  Target,
  ArrowRight,
} from "lucide-react"

import { FinalAnswer } from "@/components/final-answer"
import { ExecutionTiming } from "@/components/execution-timing"

const STAGES = ["Plan", "Solve", "Compare", "Synthesize"]

function ExecutionContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const rawId = searchParams?.get("id")
  const id: string | null = rawId || null

  const state = useExecution(id)

  const handleCancel = async () => {
    if (id && confirm("Cancel this run? The team will stop and you can start a new investigation.")) {
      if (!id.startsWith("local-")) {
        try {
          await ApiClient.cancelExecution(id)
        } catch {
          // Local or already-settled runs have nothing to cancel server-side.
        }
      }
      router.push("/chat")
    }
  }

  if (!id) {
    return (
      <div className="asm-page asm-run min-h-screen pb-20">
        <main id="main-content" tabIndex={-1} className="asm-run-main">
          <section className="asm-panel mx-auto mt-10 max-w-xl p-8 text-center">
            <span className="asm-index">[ 03 / Result ]</span>
            <h1 className="mt-4 text-3xl font-bold uppercase tracking-tight">No run selected</h1>
            <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-muted-foreground">
              Choose a saved run from History, or start a new investigation to see the team work.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              <Link href="/history" className="asm-btn asm-btn-outline">
                Open history
              </Link>
              <Link href="/chat" className="asm-btn asm-btn-primary">
                Start an investigation
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
          </section>
        </main>
      </div>
    )
  }

  const formatTime = (secs: number | null) => {
    if (secs === null) return "--:--"
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}:${s.toString().padStart(2, "0")}`
  }

  const terminal = ["completed", "cancelled", "failed", "failed_partial"].includes(state.status)
  const failedBanner = ["failed", "failed_partial", "unknown"].includes(state.status)

  const stageIndex = state.finalAnswer
    ? 3
    : state.round > 0 || state.disagreements.length > 0
      ? 2
      : state.team.length > 0
        ? 1
        : 0

  const confidenceValue =
    state.confidence === "High" ? 1 : state.confidence === "Moderate" ? 0.62 : state.confidence === "Low" ? 0.3 : 0
  const evidenceValue = state.sources.length
    ? state.sources.filter((source) => source.verified).length / state.sources.length
    : 0
  const contradictionValue = state.disagreements.length
    ? state.disagreements.filter((item) => item.resolved).length / state.disagreements.length
    : state.disagreements.length === 0 && terminal
      ? 1
      : 0
  const newInfoValue = Math.min(1, state.sources.length / 6)

  const meters = [
    { label: "Evidence", value: evidenceValue },
    { label: "Confidence", value: confidenceValue },
    { label: "Contradictions", value: contradictionValue },
    { label: "New information", value: newInfoValue },
  ]

  return (
    <div className="asm-page asm-run min-h-screen pb-20">
      {state.connectionState !== "connected" && (
        <div className="asm-run-banner" data-tone="warning">
          <span className="inline-flex items-center gap-2">
            <WifiOff className="size-3.5 animate-pulse" />
            {state.connectionState === "reconnecting"
              ? "Connection lost. Reconnecting…"
              : "WebSocket failed. Polling for updates…"}
          </span>
        </div>
      )}
      {state.quotaWarning && (
        <div className="asm-run-banner" data-tone="danger">
          <span className="inline-flex items-center gap-2">
            <AlertTriangle className="size-3.5" />
            {state.quotaWarning}
            {state.degradedMode && <Badge variant="outline" className="ml-2 rounded-none border-danger text-danger">Degraded mode</Badge>}
          </span>
        </div>
      )}
      {state.status === "cancelled" && (
        <div className="asm-run-banner" data-tone="warning">
          <span className="inline-flex items-center gap-2">
            <WifiOff className="size-3.5" />
            This run ended before completing. It was cancelled when the page closed or the connection dropped.
          </span>
        </div>
      )}
      {failedBanner && (
        <div className="asm-run-banner" data-tone="danger" data-testid="run-failed-banner">
          <span className="inline-flex items-center gap-2">
            <XCircle className="size-3.5" />
            {state.status === "failed_partial"
              ? "This run ended with partial failures. Review the event log for details."
              : "This run failed before producing an answer. Check your provider keys and quota, then start a new run."}
          </span>
        </div>
      )}

      <header className="asm-run-head">
        <div className="asm-run-head-inner">
          <div className="min-w-0">
            <span className="asm-index">
              [ 03 / {terminal ? "Result" : "Live run"} ]
            </span>
            <h1>
              {terminal
                ? state.finalAnswer
                  ? "Synthesized answer"
                  : "Run ended"
                : "Run in progress"}
            </h1>
            <p className="mt-3 max-w-full break-all font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              Run ID: {id}
            </p>
            <Link
              href="/history"
              className="mt-2 inline-flex items-center font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:text-brand"
            >
              ← All runs
            </Link>
          </div>

          <div className="asm-run-head-meta">
            <ExecutionTiming
              status={state.status}
              remainingSeconds={state.timerSeconds}
              elapsedSeconds={state.summary?.elapsedSeconds ?? null}
            />
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" className="rounded-none" onClick={handleCancel} disabled={terminal}>
                <X className="mr-1.5 size-3.5" />
                Cancel
              </Button>
              <Link href="/chat" className="asm-btn asm-btn-primary !min-h-9 !px-3 !text-[0.6rem]">
                New investigation
                <ArrowRight className="size-3.5" />
              </Link>
            </div>
          </div>
        </div>

        <div className="asm-stage-rail" aria-label="Run stages">
          {STAGES.map((stage, index) => {
            const stageState = terminal && index <= stageIndex ? "done" : index < stageIndex ? "done" : index === stageIndex ? "active" : "todo"
            return (
              <div key={stage} className="asm-stage" data-state={stageState}>
                <span className="asm-stage-track">
                  <i style={{ width: stageState === "todo" ? "0%" : stageState === "active" ? "62%" : "100%" }} />
                </span>
                <span>{index < stageIndex || (terminal && index <= stageIndex) ? "✓ " : ""}{stage}</span>
              </div>
            )
          })}
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="asm-run-main space-y-5">
        {terminal && state.summary && (
          <div data-testid="run-summary-strip" className="asm-run-summary">
            <span>{state.summary.agentCount === null ? "agents unavailable" : `${state.summary.agentCount} agents`}</span>
            {(state.summary.providers?.length ?? 0) > 0 && (
              <span>providers: {state.summary.providers?.join(", ")}</span>
            )}
            {state.summary.debateRounds !== null ? (
              <span>{state.summary.debateRounds} debate rounds</span>
            ) : (
              <span>debate rounds unavailable</span>
            )}
            {state.summary.tokens !== null && (
              <span>{state.summary.tokens.toLocaleString()} tokens</span>
            )}
            {state.summary.elapsedSeconds !== null && (
              <span>finished in {formatTime(Math.round(state.summary.elapsedSeconds))}</span>
            )}
          </div>
        )}

        {state.question && (
          <section className="asm-question-brief" aria-label="Investigation question and attachments">
            <span className="asm-label">The question</span>
            <p className="whitespace-pre-wrap break-words">{state.question}</p>
            {state.attachments.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2" aria-label="Attached files used in this investigation">
                {state.attachments.map((attachment) => (
                  <span key={attachment.filename} className="asm-attachment">
                    <b>{attachment.filename}</b>
                    <span>{attachment.filename.toLowerCase().endsWith(".env.example") ? "ENV.EXAMPLE" : (attachment.filename.split(".").pop() || "TEXT").toUpperCase()}</span>
                    <span>{Math.max(1, Math.ceil(attachment.size_bytes / 1024))} KB</span>
                  </span>
                ))}
                <p className="w-full text-[10px] leading-relaxed text-muted-foreground">
                  Only attachment names and sizes are kept in local history; original file contents are not saved.
                </p>
              </div>
            )}
          </section>
        )}

        <div className="asm-run-grid">
          <section className="asm-panel asm-consensus-panel" aria-label="Consensus">
            <div className="asm-section-label">
              <span className="asm-label flex items-center gap-2">
                <Target className="size-3.5 text-brand" aria-hidden />
                Consensus
              </span>
              {state.round > 0 && <small>Round {state.round}</small>}
            </div>

            <div className="asm-consensus-body flex flex-1 flex-col">
              {state.consensusScore !== null ? (
                <>
                  <div className="asm-big-score">
                    {Math.round(state.consensusScore * 100)}%
                    <small>
                      Agreement
                      <br />
                      across {state.summary?.agentCount ?? state.team.length ?? "—"} agents
                    </small>
                  </div>

                  <div className="mt-6">
                    {meters.map((meter) => (
                      <div className="asm-meter-row" key={meter.label}>
                        <span>{meter.label}</span>
                        <span className="asm-meter">
                          <i style={{ width: `${Math.round(meter.value * 100)}%` }} />
                        </span>
                        <b>{Math.round(meter.value * 100)}%</b>
                      </div>
                    ))}
                  </div>

                  {state.consensusHistory.length > 1 && (
                    <div className="mt-5 flex h-8 items-end gap-1 border-t border-border pt-3">
                      {state.consensusHistory.map((score, index) => (
                        <div
                          key={index}
                          className="w-2 bg-brand/50"
                          style={{ height: `${Math.max(10, score * 100)}%` }}
                          title={`Round ${index + 1}: ${Math.round(score * 100)}%`}
                        />
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 py-12 text-muted-foreground">
                  {failedBanner ? (
                    <>
                      <XCircle className="size-10" />
                      <span className="asm-label">No consensus. The run failed.</span>
                    </>
                  ) : (
                    <>
                      <PlayCircle className="size-10 animate-pulse" />
                      <span className="asm-label">Awaiting first comparison</span>
                    </>
                  )}
                </div>
              )}
            </div>
          </section>

          <section className="asm-panel" aria-label="Temporary team">
            <div className="asm-section-label">
              <span className="flex items-center gap-2">
                <Users className="size-3.5 text-brand" aria-hidden />
                <h2 className="asm-label">Research team</h2>
              </span>
              <small>{state.team.length.toString().padStart(2, "0")} roles</small>
            </div>

            {state.team.length > 0 ? (
              <div className="asm-team-grid">
                {state.team.map((agent) => (
                  <div key={agent.id} className="asm-agent-tile" data-state={agent.state}>
                    <div className="asm-agent-head">
                      <b>{agent.role}</b>
                      <span>{agent.model_family}</span>
                    </div>
                    <div className="asm-agent-state" title={agent.activity}>
                      {agent.state === "done" && <CheckCircle2 className="size-3" aria-hidden />}
                      {agent.state === "failed-replaced" && <XCircle className="size-3" aria-hidden />}
                      {agent.activity}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="asm-empty">
                {failedBanner
                  ? "This run failed before a team formed."
                  : terminal && (state.summary?.agentCount ?? 0) > 0
                    ? `Team disbanded. ${state.summary?.agentCount} agents served this run.`
                    : "Forming temporary team…"}
              </div>
            )}
          </section>
        </div>

        {state.finalAnswer && <FinalAnswer state={state} />}

        <div className="asm-run-grid">
          <section className="asm-panel" aria-label="Cross-examinations">
            <div className="asm-section-label">
              <span className="asm-label flex items-center gap-2">
                <MessageSquareWarning className="size-3.5 text-warning" aria-hidden />
                Cross-examinations
              </span>
              <small>{state.disagreements.length.toString().padStart(2, "0")} recorded</small>
            </div>
            <div className="asm-list">
              {state.disagreements.length === 0 ? (
                <div className="asm-empty">No disagreements so far. New conflicts appear here.</div>
              ) : (
                state.disagreements.map((item) => (
                  <div key={item.id} className="asm-list-row">
                    {item.resolved ? (
                      <CheckCircle2 className="size-3.5 text-success" aria-hidden />
                    ) : (
                      <AlertTriangle className="size-3.5 animate-pulse text-warning" aria-hidden />
                    )}
                    <div>
                      <p className={item.resolved ? "text-muted-foreground" : "text-foreground"}>{item.issue}</p>
                      <small>Source: {item.agent_id}</small>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="asm-panel" aria-label="Verified sources">
            <div className="asm-section-label">
              <span className="asm-label flex items-center gap-2">
                <LinkIcon className="size-3.5 text-info" aria-hidden />
                Sources
              </span>
              <small>{state.sources.length.toString().padStart(2, "0")} cited</small>
            </div>
            <div className="asm-list">
              {state.sources.length === 0 ? (
                <div className="asm-empty">No sources cited in this run.</div>
              ) : (
                state.sources.map((source, index) => (
                  <div key={source.id} id={`source-${index + 1}`} className="asm-list-row">
                    {source.verified ? (
                      <CheckCircle2 className="size-3.5 shrink-0 text-success" aria-hidden />
                    ) : (
                      <span className="mt-0.5 size-3.5 shrink-0 animate-spin rounded-full border border-muted-foreground border-t-info" aria-hidden />
                    )}
                    <div className="min-w-0">
                      <a href={source.url} target="_blank" rel="noreferrer" className="block truncate hover:text-brand">
                        [{index + 1}] {source.title || new URL(source.url).hostname}
                      </a>
                      <small className="truncate">{source.url}</small>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        <section className="asm-panel" aria-label="Event log">
          <div className="asm-section-label">
            <span className="asm-label flex items-center gap-2">
              <Activity className="size-3.5 text-brand" aria-hidden />
              Event stream
            </span>
            <small>{terminal ? "closed" : "live"}</small>
          </div>
          <div className="asm-list h-56 p-3">
            {state.feed.length === 0 ? (
              <div className="asm-empty">Awaiting events…</div>
            ) : (
              [...state.feed].reverse().map((entry) => (
                <div key={entry.id} className="asm-feed-row" data-type={entry.type}>
                  <time>{new Date(entry.timestamp).toLocaleTimeString([], { hour12: false })}</time>
                  <span>{entry.message}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  )
}

export default function ExecutionPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-muted-foreground">Loading…</div>}>
      <ExecutionContent />
    </Suspense>
  )
}
