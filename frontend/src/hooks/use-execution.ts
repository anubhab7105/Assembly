import { useState, useEffect, useRef, useCallback, type SetStateAction } from "react"
import { env } from "@/lib/env"
import { storage } from "@/lib/storage"
import type {
  ProgressEvent,
  TeamReadyData,
  DisagreementData,
  SourceData,
  ConsensusData,
  TimerData,
  ExecutionCompletedData,
  AgentStatusData,
  QuotaWarningData,
  RoundData,
  ActivityFeedEntry,
} from "@/lib/events"

export interface AgentInfo {
  id: string
  role: string
  model_family: string
  state: "idle" | "working" | "done" | "failed-replaced"
  activity: string
}

export interface ExecutionState {
  status: string
  connectionState: "connected" | "reconnecting" | "polling"
  team: AgentInfo[]
  consensusScore: number | null
  consensusHistory: number[]
  disagreements: DisagreementData[]
  sources: SourceData[]
  timerSeconds: number | null
  finalAnswer: string | null
  confidence: "High" | "Moderate" | "Low" | null
  uncertaintyNote: string | null
  question: string | null
  round: number
  degradedMode: boolean
  quotaWarning: string | null
  feed: ActivityFeedEntry[]
  // Frozen post-run summary (from device history for local runs).
  summary: {
    agentCount: number | null
    providers: string[]
    debateRounds: number | null
    tokens: number | null
    elapsedSeconds: number | null
  } | null
}

const WS_RECONNECT_MAX_ATTEMPTS = 5
const WS_RECONNECT_DELAY_MS = 2000

const initialState: ExecutionState = {
  status: "idle",
  connectionState: "connected",
  team: [],
  consensusScore: null,
  consensusHistory: [],
  disagreements: [],
  sources: [],
  timerSeconds: null,
  finalAnswer: null,
  confidence: null,
  uncertaintyNote: null,
  question: null,
  round: 0,
  degradedMode: false,
  quotaWarning: null,
  feed: [],
  summary: null,
}

export function useExecution(executionId: string | null) {
  const [stateRecord, setStateRecord] = useState<{
    executionId: string | null
    state: ExecutionState
  }>({ executionId, state: initialState })
  const state = stateRecord.executionId === executionId ? stateRecord.state : initialState
  const setState = useCallback((nextState: SetStateAction<ExecutionState>) => {
    setStateRecord((current) => {
      const previous = current.executionId === executionId ? current.state : initialState
      return {
        executionId,
        state: typeof nextState === "function" ? nextState(previous) : nextState,
      }
    })
  }, [executionId])

  const wsRef = useRef<WebSocket | null>(null)
  const lastSeqRef = useRef<number>(0)
  const reconnectAttemptsRef = useRef<number>(0)

  const processEvent = useCallback((event: ProgressEvent) => {
    if (event.seq <= lastSeqRef.current) return
    lastSeqRef.current = event.seq

    setState((prev) => {
      const next = { ...prev }
      if (event.state) next.status = event.state

      const pushFeed = (msg: string, type: ActivityFeedEntry["type"] = "info") => {
        next.feed = [{ id: `${event.seq}`, timestamp: event.timestamp, message: msg, type }, ...next.feed].slice(0, 50)
      }

      switch (event.event_type) {
        case "team.ready":
          next.team = (event.data as TeamReadyData).agents.map((a) => ({
            ...a,
            state: "idle" as const,
            activity: "Awaiting instructions",
          }))
          pushFeed(`Team assembled with ${next.team.length} agents.`, "success")
          break
        case "agent.status": {
          const agentData = event.data as AgentStatusData
          next.team = prev.team.map((a) =>
            a.id === agentData.agent_id ? { ...a, state: agentData.state, activity: agentData.activity } : a,
          )
          // Item 5: a "no external sources" outcome must also stay visible
          // in the Event Log (the team panel resets after the run).
          if ((agentData.activity ?? "").includes("no external sources")) {
            pushFeed(agentData.activity, "warning")
          }
          break
        }
        case "round.started":
          next.round = (event.data as RoundData).round
          pushFeed(`Debate Round ${next.round} started.`, "info")
          break
        case "consensus.updated": {
          const score = (event.data as ConsensusData).score
          next.consensusScore = score
          next.consensusHistory = [...prev.consensusHistory, score]
          pushFeed(`Consensus score updated to ${score.toFixed(2)}.`, "info")
          break
        }
        case "disagreement.opened":
          next.disagreements = [...prev.disagreements, event.data as DisagreementData]
          pushFeed(`Disagreement logged: ${(event.data as DisagreementData).issue}`, "warning")
          break
        case "disagreement.resolved": {
          const resolvedData = event.data as DisagreementData
          next.disagreements = prev.disagreements.map((d) =>
            d.id === resolvedData.id ? { ...d, resolved: true } : d,
          )
          pushFeed("A disagreement was resolved.", "success")
          break
        }
        case "source.found":
          next.sources = [...prev.sources, event.data as SourceData]
          pushFeed(`Searching: ${(event.data as SourceData).url}`, "info")
          break
        case "source.verified": {
          const verifiedData = event.data as SourceData
          next.sources = prev.sources.map((s) =>
            s.id === verifiedData.id ? { ...s, verified: true } : s,
          )
          pushFeed(`Verified source: ${(event.data as SourceData).url}`, "success")
          break
        }
        case "quota.warning": {
          const qw = event.data as QuotaWarningData
          next.quotaWarning = qw.message
          if (qw.degraded) {
            next.degradedMode = true
            pushFeed(`Running in degraded mode: ${qw.message}`, "warning")
          } else {
            pushFeed(`Quota warning: ${qw.message}`, "warning")
          }
          break
        }
        case "timer.tick":
          next.timerSeconds = (event.data as TimerData).remaining_seconds
          break
        case "execution.completed": {
          const compData = event.data as ExecutionCompletedData
          // Backend wire names first (answer/confidence_label), legacy
          // aliases tolerated. The label is already capped server-side
          // (e.g. single-family High→Moderate), so the chip always matches
          // the "Confidence:" line the composer writes into the answer.
          next.finalAnswer = compData.answer ?? compData.final_answer ?? null
          next.confidence = compData.confidence_label ?? compData.confidence ?? null
          next.uncertaintyNote = compData.uncertainty_note || null
          next.question = compData.question || null
          next.summary = {
            agentCount: compData.agent_count ?? null,
            providers: compData.providers_used ?? [],
            debateRounds: compData.debate_rounds ?? null,
            tokens: compData.tokens_used ?? null,
            elapsedSeconds: compData.elapsed_seconds ?? null,
          }
          pushFeed("Execution completed. Final answer synthesised.", "success")
          break
        }
        case "execution.failed_partial":
          pushFeed("Execution failed partially. Some agents crashed.", "error")
          break
        case "execution.cancelled":
          pushFeed("Execution was cancelled.", "error")
          break
      }
      return next
    })
  }, [setState])

  const connectWs = useCallback(async function connectWebSocket() {
    if (!executionId || executionId.startsWith("local-")) return

    setState((p) => ({ ...p, connectionState: reconnectAttemptsRef.current > 0 ? "reconnecting" : "connected" }))

    const wsUrl = new URL(`${env.apiUrl}/api/executions/ws/${executionId}`)
    wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:"
    if (lastSeqRef.current > 0) {
      wsUrl.searchParams.set("after_seq", lastSeqRef.current.toString())
    }

    const ws = new WebSocket(wsUrl.toString())
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as ProgressEvent
        processEvent(payload)
      } catch (err) {
        if (process.env.NODE_ENV !== "production") console.error("Failed to parse WS message", err)
      }
    }

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0
      setState((p) => ({ ...p, connectionState: "connected" }))
      // Desktop authenticates with a first-message token (never in the URL).
      if (env.NEXT_PUBLIC_APP_MODE === "desktop" && env.desktopToken) {
        ws.send(JSON.stringify({ type: "auth", token: env.desktopToken }))
      }
    }

    ws.onclose = () => {
      if (reconnectAttemptsRef.current < WS_RECONNECT_MAX_ATTEMPTS) {
        reconnectAttemptsRef.current++
        setState((p) => ({ ...p, connectionState: "reconnecting" }))
        setTimeout(connectWebSocket, WS_RECONNECT_DELAY_MS * reconnectAttemptsRef.current)
      } else {
        setState((p) => ({ ...p, connectionState: "polling" }))
      }
    }
  }, [executionId, processEvent, setState])

  useEffect(() => {
    lastSeqRef.current = 0
    reconnectAttemptsRef.current = 0

    if (!executionId) return
    // Local (stateless web) runs render from device history.
    if (executionId.startsWith("local-")) {
      storage.getHistory(executionId).then((h) => {
        if (h) {
          setState((p) => ({
            ...p,
            status: h.status,
            finalAnswer: h.answer || null,
            question: h.question,
            consensusScore: h.consensus ?? null,
            confidence: h.confidence ?? null,
            summary: {
              agentCount: h.agentCount ?? null,
              providers: h.providers ?? [],
              debateRounds: h.debateRounds ?? null,
              tokens: h.tokens ?? null,
              elapsedSeconds: h.elapsedSeconds ?? null,
            },
          }))
        }
      })
      return
    }
    connectWs()

    return () => {
      wsRef.current?.close()
    }
  }, [executionId, connectWs, setState])

  return state
}
