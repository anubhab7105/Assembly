"use client"

import React, { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import rehypeHighlight from "rehype-highlight"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Copy, Download, Layers, ShieldAlert, Sparkles, Info, CheckCircle2 } from "lucide-react"
import { useToast } from "@/components/ui/toast"
import { ExecutionState } from "@/hooks/use-execution"
import "katex/dist/katex.min.css"
import "highlight.js/styles/github-dark.css" // Or any other style

interface FinalAnswerProps {
  state: ExecutionState
}

export function FinalAnswer({ state }: FinalAnswerProps) {
  const { toast } = useToast()
  const [verificationOpen, setVerificationOpen] = useState(false)

  const handleCopy = async () => {
    if (!state.finalAnswer) return
    try {
      await navigator.clipboard.writeText(state.finalAnswer)
      toast({ title: "Copied to clipboard", description: "Markdown copied successfully." })
    } catch {
      toast({
        title: "Clipboard unavailable",
        description: "Your browser blocked clipboard access. Use Export Markdown to download the answer instead.",
        variant: "warning",
      })
    }
  }

  const handleExport = () => {
    if (!state.finalAnswer) return
    try {
      const blob = new Blob([state.finalAnswer], { type: "text/markdown;charset=utf-8" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `assembly-answer-${Date.now()}.md`
      a.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      toast({
        title: "Download unavailable",
        description: "The browser could not create the Markdown download.",
        variant: "warning",
      })
    }
  }

  const confidenceColors = {
    High: "bg-success/20 text-success border-success/30",
    Moderate: "bg-warning/20 text-warning border-warning/30",
    Low: "bg-danger/20 text-danger border-danger/30",
    "Not assessed": "bg-muted/40 text-muted-foreground border-border",
  } as const
  // Missing data is not a confidence assessment. In particular, never turn a
  // legacy history record or incomplete backend event into a positive claim.
  const conf = state.confidence ?? "Not assessed"
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
                data-testid="confidence-label"
                data-confidence={state.confidence ?? "unknown"}
                aria-label={`Confidence assessment: ${conf}. ${verificationOpen ? "Hide" : "Show"} verification details`}
                aria-expanded={verificationOpen}
                aria-controls="final-answer-verification"
                onClick={() => setVerificationOpen(!verificationOpen)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors hover:opacity-80 ${confColor}`}
              >
                Confidence: {conf}
                <Info className="size-3 ml-1" />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
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
          <div id="final-answer-verification" className="bg-muted/30 border-b border-border/50 p-4 text-sm grid sm:grid-cols-4 gap-4 animate-in slide-in-from-top-2">
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
          <div className="prose prose-invert max-w-full min-w-0 overflow-x-auto prose-pre:max-w-full prose-pre:overflow-x-auto prose-pre:bg-muted/50 prose-pre:border prose-pre:border-border">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex, rehypeHighlight]}
              components={{
                a: ({ ...props }) => {
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

    </>
  )
}
