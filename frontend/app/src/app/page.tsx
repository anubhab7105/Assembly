"use client"

import React, { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { globalVault } from "@/lib/key-vault"
import { ApiClient } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Zap, Send, Settings, Sparkles, Clock, AlertTriangle } from "lucide-react"

const EXAMPLES = [
  "Will quantum computing achieve commercial advantage before 2030?",
  "What are the most viable methods for replicating room-temperature superconductors?",
  "Analyse the timeline and economic impacts of AGI given current scaling laws.",
  "Which battery chemistry is most likely to replace Lithium-Ion in EVs by 2035?"
]

const TIME_BUDGETS = [3, 5, 10, 15]

// Same mapping as in KeysManager for capacity check
const PROVIDERS = [
  { id: "gemini", families: ["gemini"] },
  { id: "groq", families: ["llama", "mistral"] },
  { id: "cerebras", families: ["llama"] },
  { id: "openrouter", families: ["llama", "qwen", "mistral", "deepseek"] },
  { id: "mistral", families: ["mistral"] },
]

export default function Home() {
  const router = useRouter()
  
  // State
  const [question, setQuestion] = useState("")
  const [minutes, setMinutes] = useState(5)
  const [loading, setLoading] = useState(false)
  const [readyFamilies, setReadyFamilies] = useState<number>(0)
  const [keysLoaded, setKeysLoaded] = useState(false)
  
  // Dialog State
  const [preflightData, setPreflightData] = useState<{ open: boolean, reason?: string, bestPlan?: number }>({ open: false })
  
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Load configured families
  useEffect(() => {
    async function loadKeys() {
      const families = new Set<string>()
      for (const p of PROVIDERS) {
        const k = await globalVault.getKey(p.id)
        if (k) {
          p.families.forEach(f => families.add(f))
        }
      }
      setReadyFamilies(families.size)
      setKeysLoaded(true)
    }
    loadKeys()
  }, [])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [question])

  const handleLaunch = async (overrideMinutes?: number) => {
    const finalMinutes = overrideMinutes || minutes
    if (!question.trim()) return

    setLoading(true)
    try {
      // 1. Preflight
      const preflight = await ApiClient.preflightExecution(question, finalMinutes)
      
      if (!preflight.feasible) {
        setPreflightData({
          open: true,
          reason: preflight.reason,
          bestPlan: preflight.best_smaller_plan
        })
        setLoading(false)
        return
      }

      // 2. Start Execution
      const exec = await ApiClient.startExecution(question, finalMinutes)
      router.push(`/executions/${exec.id}`)
    } catch (err) {
      console.error(err)
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (readyFamilies >= 2) handleLaunch()
    }
  }

  const hasCapacity = readyFamilies >= 2

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6 py-12">
      <main className="w-full max-w-2xl space-y-12">
        {/* Header */}
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

        {/* Capacity Indicator */}
        {keysLoaded && !hasCapacity && (
          <div className="rounded-xl border border-warning/30 bg-warning-subtle p-4 flex flex-col sm:flex-row items-center justify-between gap-4 text-center sm:text-left">
            <div className="flex items-center gap-3">
              <AlertTriangle className="size-5 text-warning shrink-0" />
              <div>
                <p className="text-sm font-medium text-warning">Insufficient Model Diversity</p>
                <p className="text-xs text-warning/80">Assembly requires at least 2 distinct model families to function.</p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => router.push("/setup")} className="shrink-0 border-warning/50 text-warning hover:bg-warning/10">
              <Settings className="size-4 mr-2" />
              Configure Keys
            </Button>
          </div>
        )}

        {/* Input Area */}
        <div className="space-y-4">
          <div className="relative rounded-2xl border border-border bg-card p-2 shadow-sm transition-shadow focus-within:border-brand focus-within:ring-1 focus-within:ring-brand/50">
            <textarea
              ref={textareaRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="What do you want the team to research?"
              className="w-full resize-none bg-transparent px-4 pt-3 pb-12 text-base text-foreground placeholder:text-muted-foreground focus:outline-none"
              rows={2}
            />
            
            {/* Toolbar inside input */}
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
                <Badge variant="secondary" className="bg-muted px-2 py-1 font-mono font-medium rounded-md text-muted-foreground">
                  Mode: Auto
                </Badge>
                
                <div className="flex items-center rounded-md border border-border bg-background p-0.5">
                  <Clock className="size-3.5 text-muted-foreground ml-2 mr-1" />
                  {TIME_BUDGETS.map(m => (
                    <button
                      key={m}
                      onClick={() => setMinutes(m)}
                      className={`px-2 py-1 text-xs font-medium rounded-sm transition-colors ${minutes === m ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                    >
                      {m}m
                    </button>
                  ))}
                </div>

                {keysLoaded && (
                  <div 
                    onClick={() => router.push("/setup")}
                    className="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
                    title={`${readyFamilies} families configured`}
                  >
                    <div className={`size-2 rounded-full ${readyFamilies >= 3 ? "bg-success" : readyFamilies >= 2 ? "bg-brand" : "bg-warning"}`} />
                    {readyFamilies} ready
                  </div>
                )}
              </div>

              <Button 
                size="sm" 
                onClick={() => handleLaunch()} 
                disabled={loading || !question.trim() || !hasCapacity}
                className="shrink-0 h-8 rounded-lg"
              >
                {loading ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Send className="size-4 mr-1.5" />}
                Launch Team
              </Button>
            </div>
          </div>
          <div className="flex justify-between px-2 text-[10px] text-muted-foreground">
            <span>Shift + Enter for new line</span>
            <span>Enter to send</span>
          </div>
        </div>

        {/* Examples */}
        <div className="grid gap-3 sm:grid-cols-2">
          {EXAMPLES.map((ex, i) => (
            <Card 
              key={i} 
              className="cursor-pointer transition-all hover:-translate-y-0.5 hover:glow-brand bg-card"
              onClick={() => {
                setQuestion(ex)
                textareaRef.current?.focus()
              }}
            >
              <CardContent className="p-4 flex gap-3">
                <Sparkles className="size-4 shrink-0 text-brand mt-0.5" />
                <p className="text-sm text-muted-foreground">{ex}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>

      {/* Preflight Error Dialog */}
      <Dialog open={preflightData.open} onOpenChange={(open) => setPreflightData(prev => ({ ...prev, open }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Time Budget Exceeded</DialogTitle>
            <DialogDescription className="pt-2">
              {preflightData.reason}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setPreflightData({ open: false })}>
              Cancel
            </Button>
            {preflightData.bestPlan && (
              <Button 
                onClick={() => {
                  setMinutes(preflightData.bestPlan!)
                  setPreflightData({ open: false })
                  handleLaunch(preflightData.bestPlan)
                }}
              >
                Downgrade to {preflightData.bestPlan}m
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
