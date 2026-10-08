"use client"

import React, { useEffect, useState } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import { useExecution } from "@/hooks/use-execution"
import { ApiClient } from "@/lib/api-client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress"
import {
  Users,
  Target,
  AlertTriangle,
  WifiOff,
  Link as LinkIcon,
  MessageSquareWarning,
  CheckCircle2,
  XCircle,
  Activity,
  X,
  PlayCircle,
  Clock,
  Zap,
} from "lucide-react"

import { FinalAnswer } from "@/components/final-answer"

export default function ExecutionPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const rawId = searchParams?.get("id")
  const id: string | null = rawId || null
  
  const state = useExecution(id)
  
  // Handlers
  const handleCancel = async () => {
    if (id && confirm("Are you sure you want to cancel this execution?")) {
      await ApiClient.cancelExecution(id)
      router.push("/")
    }
  }

  // Format timer
  const formatTime = (secs: number | null) => {
    if (secs === null) return "--:--"
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}:${s.toString().padStart(2, "0")}`
  }

  // Agent State styling
  const getAgentStyles = (status: string) => {
    switch (status) {
      case "working": return "border-brand/50 bg-brand/5 text-brand"
      case "done": return "border-success/50 bg-success-subtle text-success"
      case "failed-replaced": return "border-danger/50 bg-danger-subtle text-danger"
      default: return "border-border bg-muted/50 text-muted-foreground"
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground pb-20 selection:bg-brand/30">
      {/* ─── Graceful Banners ────────────────────────────────────────────────── */}
      {state.connectionState !== "connected" && (
        <div className="bg-warning-subtle text-warning px-4 py-2 text-center text-sm font-medium flex items-center justify-center gap-2">
          <WifiOff className="size-4 animate-pulse" />
          {state.connectionState === "reconnecting" ? "Connection lost. Reconnecting..." : "WebSocket failed. Polling for updates..."}
        </div>
      )}
      {state.quotaWarning && (
        <div className="bg-danger-subtle text-danger px-4 py-2 text-center text-sm font-medium flex items-center justify-center gap-2">
          <AlertTriangle className="size-4" />
          {state.quotaWarning}
          {state.degradedMode && <Badge variant="outline" className="ml-2 border-danger text-danger">Degraded Mode</Badge>}
        </div>
      )}

      {/* ─── Header ──────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-border bg-card/80 backdrop-blur-xl">
        <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/10 text-brand shadow-inner">
              <Zap className="size-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">Research Team</h1>
              <p className="text-xs text-muted-foreground font-mono">ID: {id}</p>
            </div>
          </div>
          
          <div className="flex items-center gap-6">
            <div className="flex flex-col items-end">
              <span className="text-[10px] font-bold tracking-widest text-muted-foreground uppercase">Time Remaining</span>
              <div className="flex items-center gap-1.5 font-mono text-2xl font-semibold tracking-tight text-foreground tabular-nums">
                <Clock className="size-5 text-brand" />
                {formatTime(state.timerSeconds)}
              </div>
            </div>

            <Button variant="outline" size="sm" onClick={handleCancel} disabled={state.status === "completed" || state.status === "cancelled"}>
              <X className="size-4 mr-1.5" />
              Cancel
            </Button>
          </div>
        </div>
      </header>

      {/* ─── Main Content ────────────────────────────────────────────────────── */}
      <main className="mx-auto max-w-7xl px-6 pt-10 space-y-8">
        
        {/* ─── Top Row: Consensus & Final Answer ──────────────────────────────── */}
        <div className="grid gap-6 lg:grid-cols-3">
          
          {/* Consensus Meter */}
          <Card className="lg:col-span-1 overflow-hidden relative isolate bg-card flex flex-col justify-between">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-lg">
                <div className="flex items-center gap-2">
                  <Target className="size-5 text-brand" />
                  Consensus Meter
                </div>
                {state.round > 0 && <Badge variant="secondary">Round {state.round}</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center justify-center py-6 gap-4 flex-1">
              {state.consensusScore !== null ? (
                <>
                  <div className="relative flex items-center justify-center">
                    <svg className="size-32 -rotate-90 transform" viewBox="0 0 100 100">
                      <circle cx="50" cy="50" r="40" className="fill-none stroke-muted" strokeWidth="8" />
                      <circle 
                        cx="50" cy="50" r="40" 
                        className="fill-none stroke-brand transition-all duration-1000 ease-out" 
                        strokeWidth="8" strokeLinecap="round"
                        strokeDasharray={`${state.consensusScore * 251.2} 251.2`} 
                      />
                    </svg>
                    <div className="absolute flex flex-col items-center">
                      <span className="text-3xl font-bold tracking-tighter text-foreground">
                        {Math.round(state.consensusScore * 100)}%
                      </span>
                      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Agreement</span>
                    </div>
                  </div>
                  
                  {/* Trend sparkline (simple bars) */}
                  {state.consensusHistory.length > 1 && (
                    <div className="flex items-end gap-1.5 h-6">
                      {state.consensusHistory.map((score, i) => (
                        <div 
                          key={i} 
                          className="w-2 bg-brand/40 rounded-t-sm transition-all"
                          style={{ height: `${Math.max(10, score * 100)}%` }}
                          title={`Round ${i+1}: ${Math.round(score * 100)}%`}
                        />
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3 opacity-50">
                  <PlayCircle className="size-12 animate-pulse" />
                  <span className="text-sm">Awaiting first debate round...</span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Role List / Agents */}
          <Card className="lg:col-span-2 bg-card">
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-lg">
                <div className="flex items-center gap-2">
                  <Users className="size-5 text-brand" />
                  Active Team ({state.team.length})
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {state.team.length > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {state.team.map((agent) => (
                    <div key={agent.id} className={`flex flex-col rounded-xl border p-3.5 transition-colors ${getAgentStyles(agent.state)}`}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold tracking-tight">{agent.role}</span>
                        <Badge variant="outline" className="font-mono text-[10px] uppercase border-current bg-transparent opacity-80">
                          {agent.model_family}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        {agent.state === "working" && <span className="size-2 rounded-full bg-current animate-ping" />}
                        {agent.state === "done" && <CheckCircle2 className="size-3" />}
                        {agent.state === "failed-replaced" && <XCircle className="size-3" />}
                        {agent.state === "idle" && <div className="size-2 rounded-full border-2 border-current" />}
                        
                        <span className="truncate opacity-90 font-medium" title={agent.activity}>
                          {agent.activity}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-muted-foreground py-10">
                  Forming temporary team...
                </div>
              )}
            </CardContent>
          </Card>

        </div>

        {/* ─── Final Answer (Only shows when done) ───────────────────────────── */}
        {state.finalAnswer && (
          <FinalAnswer state={state} />
        )}

        {/* ─── Middle Row: Disagreements & Sources ───────────────────────────── */}
        <div className="grid gap-6 lg:grid-cols-2">
          
          {/* Disagreements */}
          <Card>
            <CardHeader className="pb-3 border-b border-border/50">
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageSquareWarning className="size-4 text-warning" />
                Cross-Examinations
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-border max-h-64 overflow-y-auto">
                {state.disagreements.length === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground">No conflicts detected yet.</div>
                ) : (
                  state.disagreements.map((d) => (
                    <div key={d.id} className="p-4 flex gap-3 items-start hover:bg-muted/30 transition-colors">
                      {d.resolved ? (
                        <CheckCircle2 className="size-4 shrink-0 text-success mt-0.5" />
                      ) : (
                        <AlertTriangle className="size-4 shrink-0 text-warning mt-0.5 animate-pulse" />
                      )}
                      <div>
                        <p className={`text-sm ${d.resolved ? 'text-muted-foreground' : 'text-foreground font-medium'}`}>
                          {d.issue}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-1 font-mono uppercase">
                          Source: {d.agent_id}
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          {/* Sources */}
          <Card>
            <CardHeader className="pb-3 border-b border-border/50">
              <CardTitle className="flex items-center gap-2 text-base">
                <LinkIcon className="size-4 text-info" />
                Verified Sources
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-border max-h-64 overflow-y-auto">
                {state.sources.length === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground">No external sources cited yet.</div>
                ) : (
                  state.sources.map((s, index) => (
                    <a 
                      key={s.id} 
                      id={`source-${index + 1}`}
                      href={s.url} 
                      target="_blank" 
                      rel="noreferrer"
                      className="p-4 flex gap-3 items-start group hover:bg-muted/30 transition-colors block"
                    >
                      {s.verified ? (
                        <CheckCircle2 className="size-4 shrink-0 text-success mt-0.5" />
                      ) : (
                        <span className="size-4 shrink-0 border-2 border-muted-foreground rounded-full mt-0.5 border-t-info animate-spin" />
                      )}
                      <div className="overflow-hidden">
                        <p className="text-sm text-foreground font-medium truncate group-hover:text-info transition-colors">
                          {s.title || new URL(s.url).hostname}
                        </p>
                        <p className="text-xs text-muted-foreground truncate mt-0.5">{s.url}</p>
                      </div>
                    </a>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ─── Bottom: Activity Feed ─────────────────────────────────────────── */}
        <Card className="bg-card shadow-sm border-border">
          <CardHeader className="pb-3 border-b border-border/50 bg-muted/20">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-wide uppercase text-muted-foreground">
              <Activity className="size-4" />
              Event Log
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="h-48 overflow-y-auto p-4 flex flex-col-reverse gap-3 text-sm font-mono">
              {state.feed.length === 0 ? (
                <div className="text-muted-foreground text-center">Awaiting events...</div>
              ) : (
                state.feed.map((entry) => (
                  <div key={entry.id} className="flex gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                    <span className="text-muted-foreground/60 shrink-0">
                      {new Date(entry.timestamp).toLocaleTimeString([], { hour12: false })}
                    </span>
                    <span className={`
                      ${entry.type === "error" ? "text-danger" : ""}
                      ${entry.type === "success" ? "text-success" : ""}
                      ${entry.type === "warning" ? "text-warning" : ""}
                      ${entry.type === "info" ? "text-foreground" : ""}
                    `}>
                      {entry.message}
                    </span>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

      </main>
    </div>
  )
}
