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

export interface AgentStatusData {
  agent_id: string
  state: "idle" | "working" | "done" | "failed-replaced"
  activity: string
}

export interface QuotaWarningData {
  provider: string
  message: string
  degraded: boolean
}

export interface RoundData {
  round: number
}

export interface ActivityFeedEntry {
  id: string
  timestamp: string
  message: string
  type: "info" | "warning" | "success" | "error"
}

export interface ExecutionCompletedData {
  // Wire names sent by the backend (orchestrator execution.completed).
  answer: string
  confidence_label?: "High" | "Moderate" | "Low"
  consensus_score?: number
  agent_count?: number
  providers_used?: string[]
  model_families?: string[]
  disagreement_count?: number
  resolved_disagreement_count?: number
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
  uncertainty_note?: string
  question?: string
  // Legacy aliases (never sent by current backends; read tolerantly).
  final_answer?: string
  confidence?: "High" | "Moderate" | "Low"
}

export interface ProgressEvent extends BaseEvent {
  data:
    | TeamReadyData
    | DisagreementData
    | SourceData
    | ConsensusData
    | TimerData
    | ExecutionCompletedData
    | AgentStatusData
    | QuotaWarningData
    | RoundData
    | Record<string, unknown>
}
