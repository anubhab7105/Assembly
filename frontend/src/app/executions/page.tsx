"use client"

import React, { Suspense } from "react"
import Link from "next/link"
import { useSearchParams, useRouter } from "next/navigation"
import { useExecution, type AgentInfo, type ExecutionState } from "@/hooks/use-execution"
import { ApiClient } from "@/lib/api-client"
import { FinalAnswer } from "@/components/final-answer"
import { TrafficDots } from "@/components/cinematic/window-card"
import {
  Users,
  AlertTriangle,
  WifiOff,
  Link as LinkIcon,
  MessageSquareWarning,
  CheckCircle2,
  XCircle,
  Activity,
  PlayCircle,
  Target,
  ArrowRight,
  Square,
  Search,
} from "lucide-react"

const STAGES = ["Plan", "Solve", "Compare", "Synthesize"]

function formatClock(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "—:—"
  const safe = Math.max(0, Math.round(seconds))
  const m = Math.floor(safe / 60)
  const s = safe % 60
  return `${m}:${s.toString().padStart(2, "0")}`
}

function hostFor(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function shortAgentStatus(agent: AgentInfo): string {
  if (agent.state === "done") return "Done"
  if (agent.state === "failed-replaced") return "Replaced"
  if (agent.state === "idle") return "Queued"
  const activity = (agent.activity || "").toLowerCase()
  if (activity.includes("review") || activity.includes("critic") || activity.includes("cross")) return "Reviewing"
  if (activity.includes("search") || activity.includes("research")) return "Searching"
  if (activity.includes("solv")) return "Solving"
  if (activity.includes("writ") || activity.includes("synthes")) return "Writing"
  if (activity.includes("verif")) return "Verifying"
  return "Working"
}

function TeamGrid({
  state,
  terminal,
  failed,
}: {
  state: ExecutionState
  terminal: boolean
  failed: boolean
}) {
  if (state.team.length > 0) {
    return (
      <div className="cin-team-grid">
        {state.team.map((agent) => (
          <div key={agent.id} className="cin-team-card">
            <div className="cin-team-card-head">
              <b>{agent.role}</b>
              <span>{agent.model_family}</span>
            </div>
            <div className="cin-team-state" title={agent.activity}>
              {agent.state === "done" && <CheckCircle2 className="size-3 text-success" aria-hidden />}
              {agent.state === "failed-replaced" && <XCircle className="size-3 text-danger" aria-hidden />}
              {agent.state === "working" && (
                <span className="size-2.5 animate-pulse rounded-full bg-brand" aria-hidden />
              )}
              {agent.state === "idle" && (
                <span className="size-2.5 rounded-full border border-muted-foreground" aria-hidden />
              )}
              {agent.activity}
            </div>
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="cin-team-grid-empty">
      {failed
        ? "This run failed before a team formed."
        : terminal && (state.summary?.agentCount ?? 0) > 0
          ? `Team disbanded. ${state.summary?.agentCount} agents served this run.`
          : terminal
            ? "The team for this run is no longer available."
            : "Forming the temporary team…"}
    </div>
  )
}

function ExecutionContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const rawId = searchParams?.get("id")
  const id: string | null = rawId || null

  const state = useExecution(id)

  const handleCancel = async () => {
    if (id && confirm("Stop this run? The team will stop and you can start a new investigation.")) {
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
      <div className="cin-page">
        <main id="main-content" tabIndex={-1} className="cin-main">
          <div className="cin-shell cin-page-inner">
            <div className="cin-empty-state cin-window px-6 py-14">
              <span className="cin-kicker">03 — Result</span>
              <h1 className="cin-title">No run selected</h1>
              <p>
                Choose a saved run from History, or start a new investigation to watch the team work
                through the question.
              </p>
              <div className="mt-7 flex flex-wrap justify-center gap-3">
                <Link href="/history" className="cin-btn cin-btn-outline">
                  Open history
                </Link>
                <Link href="/chat" className="cin-btn cin-btn-primary">
                  Start an investigation
                  <ArrowRight className="size-4" aria-hidden />
                </Link>
              </div>
            </div>
          </div>
        </main>
      </div>
    )
  }

  const terminal = ["completed", "cancelled", "failed", "failed_partial"].includes(state.status)
  const active = !terminal
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
  const consensusPct = state.consensusScore !== null ? Math.round(state.consensusScore * 100) : null

  const meters = [
    { label: "Evidence", value: evidenceValue },
    { label: "Confidence", value: confidenceValue },
    { label: "Contradictions", value: contradictionValue },
    { label: "New information", value: newInfoValue },
  ]

  const kicker = state.finalAnswer ? "04 — Answer" : terminal ? "03 — Compare" : "02 — Watch"
  const title = state.finalAnswer
    ? "Your answer"
    : terminal
      ? "Run ended"
      : state.team.length > 0
        ? "Agents are working"
        : "Assembling the team"

  const timerLabel = terminal ? "Elapsed" : "Time left"
  const timerValue = terminal
    ? state.summary?.elapsedSeconds ?? null
    : state.timerSeconds

  const verifiedSources = state.sources.filter((source) => source.verified).length
  const resolvedDisagreements = state.disagreements.filter((item) => item.resolved).length
  const activeAgents = state.team.filter((agent) => agent.state === "working").length
  const ringProgress = Math.max(8, Math.min(96, 14 + stageIndex * 25))

  return (
    <div className="cin-page">
      {state.connectionState !== "connected" && (
        <div className="cin-run-banner" data-tone="warning">
          <span className="inline-flex items-center gap-2">
            <WifiOff className="size-3.5 animate-pulse" aria-hidden />
            {state.connectionState === "reconnecting"
              ? "Connection lost. Reconnecting…"
              : "WebSocket failed. Polling for updates…"}
          </span>
        </div>
      )}
      {state.quotaWarning && (
        <div className="cin-run-banner" data-tone="danger">
          <span className="inline-flex items-center gap-2">
            <AlertTriangle className="size-3.5" aria-hidden />
            {state.quotaWarning}
            {state.degradedMode && <span className="cin-chip cin-chip-danger ml-2">Degraded mode</span>}
          </span>
        </div>
      )}
      {state.status === "cancelled" && (
        <div className="cin-run-banner" data-tone="warning">
          <span className="inline-flex items-center gap-2">
            <WifiOff className="size-3.5" aria-hidden />
            This run ended before completing. It was cancelled when the page closed or the connection
            dropped.
          </span>
        </div>
      )}
      {failedBanner && (
        <div className="cin-run-banner" data-tone="danger" data-testid="run-failed-banner">
          <span className="inline-flex items-center gap-2">
            <XCircle className="size-3.5" aria-hidden />
            {state.status === "failed_partial"
              ? "This run ended with partial failures. Review the event log for details."
              : "This run failed before producing an answer. Check your provider keys and quota, then start a new run."}
          </span>
        </div>
      )}

      <main id="main-content" tabIndex={-1} className="cin-main">
        <div className="cin-shell cin-page-inner">
          <header className="cin-run-head">
            <div className="min-w-0">
              <span className="cin-kicker">{kicker}</span>
              <h1 className="cin-title">{title}</h1>
              <p className="cin-run-id">Run ID: {id}</p>
              <Link href="/history" className="cin-quiet-link mt-1 !px-0">
                ← All runs
              </Link>
            </div>
            <div className="cin-run-head-meta">
              <div className="cin-timer">
                <span>{timerLabel}</span>
                <b>{timerValue === null ? "Unavailable" : formatClock(timerValue)}</b>
              </div>
              <button
                type="button"
                className="cin-btn cin-btn-sm cin-btn-outline"
                onClick={() => void handleCancel()}
                disabled={terminal}
              >
                <Square className="size-3.5" aria-hidden />
                Stop run
              </button>
              <Link href="/chat" className="cin-btn cin-btn-sm cin-btn-primary">
                Ask another
                <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </div>
          </header>

          <div className="cin-stage-rail" aria-label="Run stages">
            {STAGES.map((stage, index) => {
              const stageState =
                terminal && index <= stageIndex
                  ? "done"
                  : index < stageIndex
                    ? "done"
                    : index === stageIndex
                      ? "active"
                      : "todo"
              return (
                <div key={stage} className="cin-stage" data-state={stageState}>
                  <span className="cin-stage-track">
                    <i
                      style={{
                        width: stageState === "todo" ? "0%" : stageState === "active" ? "62%" : "100%",
                      }}
                    />
                  </span>
                  <span>
                    {index < stageIndex || (terminal && index <= stageIndex) ? "✓ " : ""}
                    {stage}
                  </span>
                </div>
              )
            })}
          </div>

          {terminal && state.summary && (
            <div data-testid="run-summary-strip" className="cin-run-summary">
              <span>
                {state.summary.agentCount === null ? "agents unavailable" : `${state.summary.agentCount} agents`}
              </span>
              {(state.summary.providers?.length ?? 0) > 0 && (
                <span>providers: {state.summary.providers?.join(", ")}</span>
              )}
              {state.summary.debateRounds !== null ? (
                <span>{state.summary.debateRounds} debate rounds</span>
              ) : (
                <span>debate rounds unavailable</span>
              )}
              {state.summary.tokens !== null && <span>{state.summary.tokens.toLocaleString()} tokens</span>}
              {state.summary.elapsedSeconds !== null && (
                <span>finished in {formatClock(Math.round(state.summary.elapsedSeconds))}</span>
              )}
            </div>
          )}

          {state.question && (
            <section className="cin-question-brief" aria-label="Investigation question and attachments">
              <span className="cin-kicker !mb-0">The question</span>
              <p className="whitespace-pre-wrap break-words">{state.question}</p>
              {state.attachments.length > 0 && (
                <div
                  className="mt-4 flex flex-wrap gap-2"
                  aria-label="Attached files used in this investigation"
                >
                  {state.attachments.map((attachment) => (
                    <span key={attachment.filename} className="cin-attachment">
                      <b>{attachment.filename}</b>
                      <span>
                        {attachment.filename.toLowerCase().endsWith(".env.example")
                          ? "ENV.EXAMPLE"
                          : (attachment.filename.split(".").pop() || "TEXT").toUpperCase()}
                      </span>
                      <span>{Math.max(1, Math.ceil(attachment.size_bytes / 1024))} KB</span>
                    </span>
                  ))}
                  <p className="w-full text-[10px] leading-relaxed text-muted-foreground">
                    Only attachment names and sizes are kept in local history; original file contents are
                    not saved.
                  </p>
                </div>
              )}
            </section>
          )}

          {active ? (
            <>
              <div className="cin-watch-grid">
                <section className="cin-window cin-watch-stage" aria-label="Live team activity">
                  <div className="mb-1 flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <span className="cin-kicker !mb-1 !text-[0.68rem]">Live team</span>
                      <p className="m-0 text-sm text-muted-foreground">
                        {activeAgents > 0
                          ? `${activeAgents} agent${activeAgents === 1 ? "" : "s"} reasoning now`
                          : "Waiting for the next agent to report"}
                      </p>
                    </div>
                    <span className="cin-chip cin-chip-brand">
                      <span className="size-1.5 animate-pulse rounded-full bg-brand" aria-hidden />
                      {STAGES[Math.min(stageIndex, STAGES.length - 1)]}
                    </span>
                  </div>

                  <div className="cin-orbit">
                    <span className="cin-orbit-ring" aria-hidden />
                    <div
                      className="cin-timer-ring"
                      style={{ "--cin-progress": ringProgress } as React.CSSProperties}
                    >
                      <div className="cin-timer-center">
                        <strong>{formatClock(state.timerSeconds)}</strong>
                        <span>{state.timerSeconds === null ? "waiting for timer" : "left"}</span>
                      </div>
                    </div>

                    {state.team.slice(0, 4).map((agent, index) => (
                      <div
                        key={agent.id}
                        className={`cin-agent-node is-${["a", "b", "c", "d"][index]}`}
                        data-state={agent.state}
                      >
                        <span className="cin-agent-dot" aria-hidden>
                          {["A", "B", "C", "D"][index]}
                        </span>
                        <span className="cin-agent-copy">
                          <b>{agent.role}</b>
                          <span>{shortAgentStatus(agent)}</span>
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="cin-window cin-watch-float">
                    <div className="cin-window-bar">
                      <TrafficDots />
                      <span className="cin-window-title">Researcher</span>
                    </div>
                    <div className="cin-window-body">
                      <p className="m-0 text-sm font-semibold text-foreground">
                        {state.sources.length === 0
                          ? "Checking primary sources"
                          : `${state.sources.length} source${state.sources.length === 1 ? "" : "s"} found`}
                      </p>
                      <div className="cin-progress">
                        <i
                          style={{
                            width: `${state.sources.length ? Math.min(100, 22 + state.sources.length * 18) : 14}%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </section>

                <aside className="cin-watch-side">
                  <section className="cin-window cin-live-feed" aria-label="Live feed">
                    <div className="cin-window-bar">
                      <TrafficDots />
                      <span className="cin-window-title">Live feed</span>
                      <span className="ml-auto text-[0.68rem] uppercase tracking-[0.14em] text-muted-foreground">
                        {state.feed.length} events
                      </span>
                    </div>
                    <div className="cin-window-body">
                      {state.feed.length === 0 ? (
                        <div className="cin-feed-empty">Awaiting the first event…</div>
                      ) : (
                        [...state.feed]
                          .reverse()
                          .slice(-30)
                          .map((entry) => (
                            <div key={entry.id} className="cin-feed-row" data-type={entry.type}>
                              <time>
                                {new Date(entry.timestamp).toLocaleTimeString([], { hour12: false })}
                              </time>
                              <span>{entry.message}</span>
                            </div>
                          ))
                      )}
                    </div>
                    <div className="px-4 pb-4 pt-0">
                      <button
                        type="button"
                        className="cin-btn cin-btn-outline w-full"
                        onClick={() => void handleCancel()}
                      >
                        <Square className="size-3.5" aria-hidden />
                        Stop run
                      </button>
                    </div>
                  </section>
                </aside>
              </div>

              <section className="cin-window cin-panel mt-5" aria-label="Research team">
                <div className="cin-panel-head">
                  <h2>
                    <Users className="size-4" aria-hidden />
                    Research Team
                  </h2>
                  <small>
                    {state.team.length.toString().padStart(2, "0")} role
                    {state.team.length === 1 ? "" : "s"}
                  </small>
                </div>
                <TeamGrid state={state} terminal={terminal} failed={failedBanner} />
              </section>
            </>
          ) : (
            <div className="cin-compare-grid">
              <section className="cin-window cin-consensus-card" aria-label="Consensus">
                <div className="cin-panel-head">
                  <h2>
                    <Target className="size-4" aria-hidden />
                    Consensus
                  </h2>
                  {state.round > 0 && <small>Round {state.round}</small>}
                </div>

                {state.consensusScore !== null ? (
                  <>
                    <div
                      className="cin-donut"
                      style={{ "--cin-value": consensusPct ?? 0 } as React.CSSProperties}
                    >
                      <div className="cin-donut-center">
                        <strong>{consensusPct}%</strong>
                        <span>agree</span>
                      </div>
                    </div>
                    <div className="cin-consensus-summary">
                      <p>
                        Evidence <b>{evidenceValue >= 0.6 ? "Good" : evidenceValue > 0 ? "Partial" : "Thin"}</b>
                      </p>
                      <p>
                        Confidence <b>{state.confidence ?? "Not assessed"}</b>
                      </p>
                      <p>
                        Team{" "}
                        <b>
                          {state.summary?.agentCount ?? state.team.length ?? "—"} agent
                          {(state.summary?.agentCount ?? state.team.length) === 1 ? "" : "s"}
                        </b>
                      </p>
                      <p>
                        Sources checked{" "}
                        <b>
                          {verifiedSources} of {state.sources.length}
                        </b>
                      </p>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-1 flex-col items-center justify-center gap-3 py-12 text-muted-foreground">
                    {failedBanner ? (
                      <>
                        <XCircle className="size-10" aria-hidden />
                        <span className="text-xs uppercase tracking-[0.16em]">No consensus</span>
                        <p className="m-0 max-w-[220px] text-center text-xs leading-relaxed">
                          The run ended before the team could be compared.
                        </p>
                      </>
                    ) : (
                      <>
                        <PlayCircle className="size-10 animate-pulse" aria-hidden />
                        <span className="text-xs uppercase tracking-[0.16em]">Awaiting comparison</span>
                      </>
                    )}
                  </div>
                )}
              </section>

              <section className="cin-window cin-meter-block" aria-label="Agreement detail">
                <div className="cin-meter-title">
                  <h2>Where the agents stand</h2>
                  <span className={`cin-chip ${failedBanner ? "cin-chip-warning" : "cin-chip-success"}`}>
                    {resolvedDisagreements} point{resolvedDisagreements === 1 ? "" : "s"} resolved
                  </span>
                </div>

                {meters.map((meter) => (
                  <div className="cin-meter-row" key={meter.label}>
                    <span>{meter.label}</span>
                    <span className="cin-meter">
                      <i style={{ width: `${Math.round(meter.value * 100)}%` }} />
                    </span>
                    <b>{Math.round(meter.value * 100)}%</b>
                  </div>
                ))}

                {state.consensusHistory.length > 1 && (
                  <div className="cin-consensus-history" aria-label="Consensus by round">
                    {state.consensusHistory.map((score, index) => (
                      <i
                        key={index}
                        style={{ height: `${Math.max(10, score * 100)}%` }}
                        title={`Round ${index + 1}: ${Math.round(score * 100)}%`}
                      />
                    ))}
                  </div>
                )}

                <div className="cin-panel-head mt-6">
                  <h2>
                    <Users className="size-4" aria-hidden />
                    Research Team
                  </h2>
                  <small>
                    {state.team.length.toString().padStart(2, "0")} role
                    {state.team.length === 1 ? "" : "s"}
                  </small>
                </div>
                <TeamGrid state={state} terminal={terminal} failed={failedBanner} />

                {state.finalAnswer && (
                  <Link href="#final-answer" className="cin-btn cin-btn-primary mt-6 w-full">
                    See the answer
                    <ArrowRight className="size-4" aria-hidden />
                  </Link>
                )}
              </section>
            </div>
          )}

          {state.finalAnswer && <FinalAnswer state={state} />}

          <div className="cin-run-panels">
            <section className="cin-window cin-panel" aria-label="Cross-examinations">
              <div className="cin-panel-head">
                <h2>
                  <MessageSquareWarning className="size-4" aria-hidden />
                  Cross-examinations
                </h2>
                <small>{state.disagreements.length.toString().padStart(2, "0")} recorded</small>
              </div>
              <div className="cin-list">
                {state.disagreements.length === 0 ? (
                  <div className="cin-list-empty">
                    {active
                      ? "No disagreements so far. New conflicts appear here."
                      : "The team did not record a disagreement."}
                  </div>
                ) : (
                  state.disagreements.map((item) => (
                    <div key={item.id} className="cin-list-row">
                      {item.resolved ? (
                        <CheckCircle2 className="size-3.5 text-success" aria-hidden />
                      ) : (
                        <AlertTriangle className="size-3.5 animate-pulse text-warning" aria-hidden />
                      )}
                      <div>
                        <p className={item.resolved ? "text-muted-foreground" : "text-foreground"}>
                          {item.issue}
                        </p>
                        <small>Source: {item.agent_id}</small>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>

            <section className="cin-window cin-panel" aria-label="Verified sources">
              <div className="cin-panel-head">
                <h2>
                  <LinkIcon className="size-4" aria-hidden />
                  Sources
                </h2>
                <small>
                  {verifiedSources}/{state.sources.length} verified
                </small>
              </div>
              <div className="cin-list">
                {state.sources.length === 0 ? (
                  <div className="cin-list-empty">
                    {active ? "No sources cited yet." : "No sources were cited in this run."}
                  </div>
                ) : (
                  state.sources.map((source, index) => (
                    <div key={source.id} id={`source-${index + 1}`} className="cin-list-row">
                      {source.verified ? (
                        <CheckCircle2 className="size-3.5 shrink-0 text-success" aria-hidden />
                      ) : (
                        <span
                          className="mt-0.5 size-3.5 shrink-0 animate-spin rounded-full border border-muted-foreground border-t-info"
                          aria-hidden
                        />
                      )}
                      <div className="min-w-0">
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          className="block truncate"
                        >
                          [{index + 1}] {source.title || hostFor(source.url)}
                        </a>
                        <small className="truncate">{source.url}</small>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>
          </div>

          <section className="cin-window cin-event-log" aria-label="Event log">
            <div className="cin-panel-head">
              <h2>
                <Activity className="size-4" aria-hidden />
                Event stream
              </h2>
              <small>{terminal ? "closed" : "live"}</small>
            </div>
            <div className="cin-event-scroll">
              {state.feed.length === 0 ? (
                <div className="cin-feed-empty">Awaiting events…</div>
              ) : (
                [...state.feed].reverse().map((entry) => (
                  <div key={entry.id} className="cin-feed-row" data-type={entry.type}>
                    <time>{new Date(entry.timestamp).toLocaleTimeString([], { hour12: false })}</time>
                    <span>{entry.message}</span>
                  </div>
                ))
              )}
            </div>
          </section>

          {terminal && (
            <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
              <Link href="/history" className="cin-btn cin-btn-outline">
                <Search className="size-4" aria-hidden />
                All past runs
              </Link>
              <Link href="/chat" className="cin-btn cin-btn-primary">
                Start another investigation
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
          )}
        </div>
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
