import { z } from "zod"

export type ProgressEventType =
  | "execution.started"
  | "plan.ready"
  | "team.ready"
  | "agent.status"
  | "round.started"
  | "round.finished"
  | "disagreement.opened"
  | "disagreement.resolved"
  | "source.found"
  | "source.verified"
  | "consensus.updated"
  | "quota.warning"
  | "timer.tick"
  | "synthesis.started"
  | "execution.completed"
  | "execution.failed_partial"
  | "execution.cancelled"

export interface BaseEvent {
  event_type: ProgressEventType
  execution_id: string
  seq: number
  state: string | null
  timestamp: string
}

// Payload Types
export interface TeamReadyData {
  agents: Array<{
    id: string
    role: string
    model_family: string
  }>
}

export interface DisagreementData {
  id: string
  agent_id: string
  issue: string
  resolved?: boolean
}

export interface SourceData {
  id: string
  url: string
  title?: string
  verified?: boolean
}

export interface ConsensusData {
  score: number
  threshold: number
  agreed: boolean
}

export interface TimerData {
  remaining_seconds: number
}

export interface ExecutionCompletedData {
  final_answer: string
}

export interface ProgressEvent extends BaseEvent {
  data:
    | TeamReadyData
    | DisagreementData
    | SourceData
    | ConsensusData
    | TimerData
    | ExecutionCompletedData
    | Record<string, unknown>
}
