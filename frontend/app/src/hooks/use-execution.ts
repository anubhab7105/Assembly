import { useState, useEffect, useRef, useCallback } from "react"
import { env } from "@/lib/env"
import { ApiClient } from "@/lib/api-client"
import type { 
  ProgressEvent, 
  TeamReadyData, 
  DisagreementData, 
  SourceData, 
  ConsensusData, 
  TimerData,
  ExecutionCompletedData 
} from "@/lib/events"

interface ExecutionState {
  status: string
  team: TeamReadyData["agents"]
  consensusScore: number | null
  disagreements: DisagreementData[]
  sources: SourceData[]
  timerSeconds: number | null
  finalAnswer: string | null
}

const WS_RECONNECT_MAX_ATTEMPTS = 5
const WS_RECONNECT_DELAY_MS = 2000

export function useExecution(executionId: string | null) {
  const [state, setState] = useState<ExecutionState>({
    status: "idle",
    team: [],
    consensusScore: null,
    disagreements: [],
    sources: [],
    timerSeconds: null,
    finalAnswer: null,
  })

  const wsRef = useRef<WebSocket | null>(null)
  const lastSeqRef = useRef<number>(0)
  const reconnectAttemptsRef = useRef<number>(0)

  const processEvent = useCallback((event: ProgressEvent) => {
    // Only process newer events to handle replays via after_seq
    if (event.seq <= lastSeqRef.current) return
    lastSeqRef.current = event.seq

    setState((prev) => {
      const next = { ...prev }
      if (event.state) next.status = event.state

      switch (event.event_type) {
        case "team.ready":
          next.team = (event.data as TeamReadyData).agents
          break
        case "consensus.updated":
          next.consensusScore = (event.data as ConsensusData).score
          break
        case "disagreement.opened":
          next.disagreements = [...prev.disagreements, event.data as DisagreementData]
          break
        case "disagreement.resolved": {
          const resolvedData = event.data as DisagreementData
          next.disagreements = prev.disagreements.map((d) =>
            d.id === resolvedData.id ? { ...d, resolved: true } : d
          )
          break
        }
        case "source.found":
          next.sources = [...prev.sources, event.data as SourceData]
          break
        case "source.verified": {
          const verifiedData = event.data as SourceData
          next.sources = prev.sources.map((s) =>
            s.id === verifiedData.id ? { ...s, verified: true } : s
          )
          break
        }
        case "timer.tick":
          next.timerSeconds = (event.data as TimerData).remaining_seconds
          break
        case "execution.completed":
          next.finalAnswer = (event.data as ExecutionCompletedData).final_answer
          break
      }
      return next
    })
  }, [])

  const connectWs = useCallback(() => {
    if (!executionId) return

    const wsUrl = new URL(`${env.apiUrl}/executions/${executionId}/ws`)
    wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:"
    // Send after_seq to get missed events
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
        console.error("Failed to parse WS message", err)
      }
    }

    ws.onclose = () => {
      if (reconnectAttemptsRef.current < WS_RECONNECT_MAX_ATTEMPTS) {
        reconnectAttemptsRef.current++
        setTimeout(connectWs, WS_RECONNECT_DELAY_MS * reconnectAttemptsRef.current)
      } else {
        // Fallback to REST polling if WS fails persistently
        fallbackPoll()
      }
    }
  }, [executionId, processEvent])

  const fallbackPoll = useCallback(() => {
    if (!executionId) return
    const pollInterval = setInterval(async () => {
      try {
        const res = await ApiClient.getExecution(executionId)
        setState((prev) => ({ ...prev, status: res.status }))
        
        // Optionally process missed events if the backend returns them in the payload
        if (res.events) {
          res.events.forEach(processEvent)
        }
        
        if (res.status === "completed" || res.status === "failed") {
          clearInterval(pollInterval)
        }
      } catch (err) {
        console.error("REST fallback poll failed", err)
      }
    }, 5000)
    return () => clearInterval(pollInterval)
  }, [executionId, processEvent])

  useEffect(() => {
    lastSeqRef.current = 0
    reconnectAttemptsRef.current = 0
    
    if (executionId) {
      connectWs()
    }

    return () => {
      wsRef.current?.close()
    }
  }, [executionId, connectWs])

  return state
}
