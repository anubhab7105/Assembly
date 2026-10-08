"use client"

import React, { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import rehypeHighlight from "rehype-highlight"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Copy, Download, Layers, ShieldAlert, Sparkles, Scale, Info, CheckCircle2 } from "lucide-react"
import { useToast } from "@/components/ui/toast"
import { ApiClient } from "@/lib/api-client"
import { ExecutionState } from "@/hooks/use-execution"
import "katex/dist/katex.min.css"
import "highlight.js/styles/github-dark.css" // Or any other style

interface FinalAnswerProps {
  state: ExecutionState
}

export function FinalAnswer({ state }: FinalAnswerProps) {
  const { toast } = useToast()
  const [comparing, setComparing] = useState(false)
  const [singleModelAnswer, setSingleModelAnswer] = useState<string | null>(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [verificationOpen, setVerificationOpen] = useState(false)

  const handleCopy = () => {
    if (state.finalAnswer) {
      navigator.clipboard.writeText(state.finalAnswer)
      toast({ title: "Copied to clipboard", description: "Markdown copied successfully." })
    }
  }

  const handleExport = () => {
    if (!state.finalAnswer) return
    const blob = new Blob([state.finalAnswer], { type: "text/markdown" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `assembly-answer-${Date.now()}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleCompare = async () => {
    if (!state.question) {
      toast({ title: "Cannot compare", description: "Original question is missing.", variant: "danger" })
      return
    }
    setComparing(true)
    if (!singleModelAnswer) {
      setCompareLoading(true)
      const res = await ApiClient.runSingleModel(state.question)
      setSingleModelAnswer(res.answer)
      setCompareLoading(false)
    }
  }

  const confidenceColors = {
    High: "bg-success/20 text-success border-success/30",
    Moderate: "bg-warning/20 text-warning border-warning/30",
    Low: "bg-danger/20 text-danger border-danger/30"
  }
  const conf = state.confidence || "High"
  const confColor = confidenceColors[conf]

  const distinctFamilies = new Set(state.team.map(a => a.model_family)).size
  const resolvedCount = state.disagreements.filter(d => d.resolved).length

  return (
    <>
      <Card className="border-brand/30 bg-card shadow-lg relative overflow-hidden isolate">
        {/* Subtle glow background */}
        <div className="absolute inset-0 bg-brand/5 pointer-events-none -z-10" />

        <CardHeader className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 border-b border-border/50 pb-4">
          <div className="space-y-1">
            <CardTitle className="text-2xl font-bold flex items-center gap-2">
              <Sparkles className="size-6 text-brand" />
              Final Synthesis
            </CardTitle>
            <div className="flex items-center gap-3 mt-2">
              <button 
                onClick={() => setVerificationOpen(!verificationOpen)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors hover:opacity-80 ${confColor}`}
              >
                Confidence: {conf}
                <Info className="size-3 ml-1" />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleCompare} className="h-8">
              <Scale className="size-4 mr-2" />
              Compare
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={handleCopy} title="Copy Markdown">
              <Copy className="size-4" />
            </Button>
            <Button variant="outline" size="icon" className="h-8 w-8" onClick={handleExport} title="Export Markdown">
              <Download className="size-4" />
            </Button>
          </div>
        </CardHeader>

        {/* Expandable Verification Panel */}
        {verificationOpen && (
          <div className="bg-muted/30 border-b border-border/50 p-4 text-sm grid sm:grid-cols-4 gap-4 animate-in slide-in-from-top-2">
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Team Size</p>
              <p className="font-semibold text-foreground flex items-center gap-2">
                <Layers className="size-4 text-brand" /> {state.team.length} Agents
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Diversity</p>
              <p className="font-semibold text-foreground">{distinctFamilies} Model Families</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Rounds</p>
              <p className="font-semibold text-foreground">{state.round} Debate Rounds</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Conflicts Resolved</p>
              <p className="font-semibold text-foreground text-success flex items-center gap-1">
                <CheckCircle2 className="size-4" /> {resolvedCount} / {state.disagreements.length}
              </p>
            </div>
          </div>
        )}

        <CardContent className="pt-6">
          {/* Uncertainty Note */}
          {conf !== "High" && state.uncertaintyNote && (
            <div className="mb-6 rounded-lg border border-warning/50 bg-warning-subtle p-4 flex gap-3 text-warning">
              <ShieldAlert className="size-5 shrink-0" />
              <div>
                <h4 className="font-semibold text-sm">Areas of Uncertainty</h4>
                <p className="text-sm mt-1 opacity-90">{state.uncertaintyNote}</p>
              </div>
            </div>
          )}

          {/* Markdown Content */}
          <div className="prose prose-invert max-w-none prose-pre:bg-muted/50 prose-pre:border prose-pre:border-border">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex, rehypeHighlight]}
              components={{
                a: ({ node, ...props }) => {
                  // Custom handler for inline citations like [1]
                  if (props.href?.startsWith("#source-")) {
                    return (
                      <a 
                        {...props} 
                        className="inline-flex items-center justify-center w-5 h-5 ml-1 text-[10px] font-bold text-brand bg-brand/10 rounded hover:bg-brand hover:text-white transition-colors no-underline"
                        onClick={(e) => {
                          e.preventDefault()
                          document.querySelector(props.href!)?.scrollIntoView({ behavior: 'smooth' })
                        }}
                      />
                    )
                  }
                  return <a {...props} target="_blank" rel="noreferrer" className="text-brand hover:underline" />
                }
              }}
            >
              {state.finalAnswer || ""}
            </ReactMarkdown>
          </div>
        </CardContent>
      </Card>

      {/* Compare Dialog */}
      <Dialog open={comparing} onOpenChange={setComparing}>
        <DialogContent className="max-w-6xl w-full max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-2xl">Compare with Single Model</DialogTitle>
            <DialogDescription>
              Comparing Assembly's multi-agent synthesis against a single zero-shot model (e.g. Gemini 1.5 Flash).
            </DialogDescription>
          </DialogHeader>
          
          <div className="grid grid-cols-2 gap-6 mt-4 flex-1 overflow-hidden min-h-[500px]">
            {/* Single Model */}
            <div className="flex flex-col rounded-xl border bg-muted/20 overflow-hidden">
              <div className="bg-muted p-3 border-b flex items-center justify-between">
                <span className="font-semibold text-sm">Single Model (Zero-shot)</span>
                <Badge variant="secondary">Baseline</Badge>
              </div>
              <div className="p-6 overflow-y-auto flex-1 prose prose-sm prose-invert max-w-none">
                {compareLoading ? (
                  <div className="flex items-center justify-center h-full text-muted-foreground animate-pulse">
                    Running model...
                  </div>
                ) : (
                  <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
                    {singleModelAnswer || ""}
                  </ReactMarkdown>
                )}
              </div>
            </div>

            {/* Assembly */}
            <div className="flex flex-col rounded-xl border border-brand/30 bg-brand/5 overflow-hidden shadow-lg">
              <div className="bg-brand/10 p-3 border-b border-brand/20 flex items-center justify-between">
                <span className="font-semibold text-brand text-sm flex items-center gap-2">
                  <Sparkles className="size-4" /> Assembly Synthesis
                </span>
                <Badge className="bg-brand text-white hover:bg-brand/90">Multi-Agent</Badge>
              </div>
              <div className="p-6 overflow-y-auto flex-1 prose prose-sm prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
                  {state.finalAnswer || ""}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
