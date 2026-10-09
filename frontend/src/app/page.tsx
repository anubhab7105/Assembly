"use client"

import React, { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { globalVault } from "@/lib/key-vault"
import { ApiClient, type UsageEntry } from "@/lib/api-client"
import { storage } from "@/lib/storage"
import { ModelPicker, type ModelSelection } from "@/components/model-picker"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Zap, Send, Settings, Sparkles, Clock } from "lucide-react"

const EXAMPLES = [
  "Will quantum computing achieve commercial advantage before 2030?",
  "What are the most viable methods for replicating room-temperature superconductors?",
  "Analyse the timeline and economic impacts of AGI given current scaling laws.",
  "Which battery chemistry is most likely to replace Lithium-Ion in EVs by 2035?"
]

const TIME_BUDGETS = [3, 5, 10, 15]

export default function Home() {
  const router = useRouter()

  const [question, setQuestion] = useState("")
  const [minutes, setMinutes] = useState(5)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [selection, setSelection] = useState<ModelSelection>({ selected: [], pins: {} })
  const [hasKeys, setHasKeys] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    globalVault.allKeys().then((k) => setHasKeys(Object.keys(k).length > 0)).catch(() => {})
  }, [])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [question])

  const handleLaunch = async () => {
    if (!question.trim() || loading) return
    setLoading(true)
    setStatus("Checking capacity…")
    try {
      const keys = await globalVault.allKeys()
      const usage: UsageEntry[] = await storage.getUsage()
      const preflight = await ApiClient.preflight(question, minutes, usage)
      if (!preflight.feasible) {
        setStatus(`Not feasible: ${preflight.explanation ?? "quota exhausted"}`)
        setLoading(false)
        return
      }
      setStatus("Running team… (streaming)")
      let finalAnswer = ""
      let consensus: number | null = null
      const runId = `local-${Date.now()}`
      const result = await ApiClient.startRunStream(
        {
          question,
          minutes,
          providerKeys: keys,
          selection: { selected: selection.selected, pins: selection.pins },
          usage,
        },
        (event: { event_type?: string; data?: { answer?: string; consensus_score?: number }; usage?: UsageEntry[] }) => {
          if (event.event_type === "execution.completed") {
            finalAnswer = event.data?.answer ?? ""
            consensus = event.data?.consensus_score ?? null
          }
          if (event.event_type === "run.finished" && Array.isArray(event.usage)) {
            void storage.setUsage(event.usage)
          }
        },
      )
      await storage.saveHistory({
        id: runId,
        question,
        answer: finalAnswer,
        status: result.status,
        created_at: new Date().toISOString(),
        minutes,
        consensus,
      })
      router.push(`/executions?id=${runId}`)
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Run failed")
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6 py-12">
      <main className="w-full max-w-2xl space-y-8">
        <div className="text-center space-y-4">
          <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-brand/10 text-brand mb-4">
            <Zap className="size-8" />
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
            Assembly
          </h1>
          <p className="text-lg text-muted-foreground mx-auto max-w-xl">
            Turn one question into a temporary team of AI agents that reason, debate, and verify to find the best answer.
          </p>
        </div>

        {!hasKeys && (
          <div className="rounded-xl border border-warning/30 bg-warning-subtle p-4 flex items-center justify-between gap-4">
            <p className="text-sm text-warning">Add provider keys first — runs use your keys, never a server account.</p>
            <Button variant="outline" size="sm" onClick={() => router.push("/setup")}>
              <Settings className="size-4 mr-2" />
              Configure Keys
            </Button>
          </div>
        )}

        <div className="space-y-4">
          <div className="relative rounded-2xl border border-border bg-card p-2 shadow-sm focus-within:border-brand">
            <textarea
              ref={textareaRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What do you want the team to research?"
              className="w-full resize-none bg-transparent px-4 pt-3 pb-12 text-base text-foreground placeholder:text-muted-foreground focus:outline-none"
              rows={2}
              maxLength={2000}
            />
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="bg-muted px-2 py-1 font-mono text-muted-foreground">
                  Mode: Auto
                </Badge>
                <div className="flex items-center rounded-md border border-border bg-background p-0.5">
                  <Clock className="size-3.5 text-muted-foreground ml-2 mr-1" />
                  {TIME_BUDGETS.map((m) => (
                    <button
                      key={m}
                      onClick={() => setMinutes(m)}
                      className={`px-2 py-1 text-xs font-medium rounded-sm ${minutes === m ? "bg-muted text-foreground" : "text-muted-foreground"}`}
                    >
                      {m}m
                    </button>
                  ))}
                </div>
              </div>
              <Button size="sm" onClick={handleLaunch} disabled={loading || !question.trim()} className="shrink-0 h-8 rounded-lg">
                {loading ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Send className="size-4 mr-1.5" />}
                Launch Team
              </Button>
            </div>
          </div>
          {status && <p className="px-2 text-xs text-muted-foreground">{status}</p>}
        </div>

        <ModelPicker value={selection} onChange={setSelection} />

        <div className="grid gap-3 sm:grid-cols-2">
          {EXAMPLES.map((ex, i) => (
            <Card key={i} className="cursor-pointer hover:-translate-y-0.5 bg-card" onClick={() => { setQuestion(ex); textareaRef.current?.focus() }}>
              <CardContent className="p-4 flex gap-3">
                <Sparkles className="size-4 shrink-0 text-brand mt-0.5" />
                <p className="text-sm text-muted-foreground">{ex}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  )
}
