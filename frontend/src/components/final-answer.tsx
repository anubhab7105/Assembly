"use client"

import React, { useState } from "react"
import Link from "next/link"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import rehypeHighlight from "rehype-highlight"
import rehypeSanitize, { defaultSchema } from "rehype-sanitize"
import { Copy, Download, Layers, ShieldAlert, Sparkles, Info, CheckCircle2, ArrowRight, Link2 } from "lucide-react"
import { useToast } from "@/components/ui/toast"
import { useComfort } from "@/components/cinematic/comfort"
import { ExecutionState } from "@/hooks/use-execution"
import "katex/dist/katex.min.css"
import "highlight.js/styles/github-dark.css"

// Keep Markdown rendering intentionally narrower than arbitrary HTML. KaTeX and
// highlight.js add generated markup before sanitization; allow only the classes,
// MathML elements, and inert SVG geometry those renderers need. KaTeX's inline
// styles are retained only on generated spans (raw HTML stays disabled).
const markdownSanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    "math", "semantics", "mrow", "mi", "mn", "mo", "mtext", "mspace",
    "msup", "msub", "msubsup", "mfrac", "msqrt", "mroot", "mover",
    "munder", "munderover", "mstyle", "merror", "mpadded", "mphantom",
    "mfenced", "menclose", "mmultiscripts", "mprescripts", "none",
    "mtable", "mlabeledtr", "mtr", "mtd", "maction", "annotation",
    "svg", "path",
  ],
  attributes: {
    ...defaultSchema.attributes,
    code: [["className", "hljs", /^language-[a-z0-9_-]+$/]],
    div: [
      ...(defaultSchema.attributes?.div ?? []),
      ["className", "katex-display"],
    ],
    span: [
      ...(defaultSchema.attributes?.span ?? []),
      ["className", /^hljs-[a-z0-9_-]+$/],
      ["className", /^katex(?:-mathml|-html)?$/],
      ["className", "katex-display"],
      ["className", /^(?:base|strut|mord|mop|mbin|mrel|mopen|mclose|mpunct|minner|mfrac|mroot|msup|msub|msubsup|mspace|sizing|reset-size[0-9]+|size[0-9]+|mstyle|mtight|vlist(?:-[tr][0-9]?)?|pstrut|text|mathrm|mathbf|mathit|mathnormal|mathbb|mathcal|mathfrak|mathscr|op-symbol|op-limits|accent|accentunder|delimcenter|delim-size[1-4]|nulldelimiter|stretchy|hide-tail|halfarrow|brace(?:-left|-right)?|enclosing|cancel|sout|underline|overline|col-align-[cl]|arraycolsep|cd|tag|eqn-num|rule|llap|rlap|vbox|ams(?:rm|bb|cal|frak|math)|main(?:rm|it|bf|bb|cal|frak|mi|mord|mop|mbin|mrel|mopen|mclose|mpunct|minner))$/],
      "style",
      "aria-hidden",
    ],
    math: ["xmlns", "display"],
    semantics: [],
    annotation: [["encoding", "application/x-tex"]],
    mi: ["mathvariant"],
    mstyle: ["mathvariant", "displaystyle", "scriptlevel"],
    mfenced: ["open", "close", "separators"],
    menclose: ["notation"],
    mpadded: ["width", "height", "depth", "lspace", "voffset"],
    mo: ["fence", "separator", "stretchy", "symmetric", "maxsize", "minsize", "lspace", "rspace", "form", "largeop", "movablelimits", "accent"],
    mspace: ["width", "height", "depth", "linebreak"],
    mfrac: ["linethickness"],
    mtable: ["columnalign", "rowspacing", "columnspacing"],
    mtd: ["columnspan", "rowspan", "rowalign", "columnalign"],
    svg: ["xmlns", "width", "height", "viewBox", "preserveAspectRatio", "role", "focusable"],
    path: ["d", "fill", "stroke", "strokeWidth", "transform"],
  },
  protocols: { ...defaultSchema.protocols, href: ["http", "https", "mailto"] },
}

interface FinalAnswerProps {
  state: ExecutionState
}

function hostFor(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

export function FinalAnswer({ state }: FinalAnswerProps) {
  const { toast } = useToast()
  const { settings } = useComfort()
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

  const completed = state.status === "completed"
  const distinctFamilies = completed
    ? state.summary?.familyCount ?? null
    : new Set(state.team.map((agent) => agent.model_family)).size
  const resolvedCount = state.disagreements.filter((d) => d.resolved).length
  const teamCount = completed
    ? state.summary?.verification?.agents ?? state.summary?.agentCount ?? null
    : state.team.length
  const roundCount = completed
    ? state.summary?.verification?.rounds ?? state.summary?.debateRounds ?? null
    : state.round
  const resolvedDisagreementCount = completed
    ? state.summary?.resolvedDisagreementCount ??
      state.summary?.verification?.disagreements_resolved ??
      null
    : resolvedCount

  const sourcesFirst = settings.sourcesFirst && state.sources.length > 0
  const sourceStrip = state.sources.length > 0 ? (
    <div className="cin-answer-sources" aria-label="Sources cited in this answer">
      {state.sources.map((source, index) => (
        <a
          key={source.id}
          href={`#source-${index + 1}`}
          className="cin-answer-source"
          title={source.title || source.url}
        >
          <Link2 className="size-3.5" aria-hidden />
          [{index + 1}] {source.title || hostFor(source.url)}
        </a>
      ))}
    </div>
  ) : (
    <span className="text-xs text-muted-foreground">No external sources were cited in this run.</span>
  )

  return (
    <article id="final-answer" className="cin-window cin-answer-card assembly-answer-card">
      <header className="cin-answer-head">
        <div>
          <h2>
            <Sparkles className="size-6" aria-hidden />
            Final synthesis
          </h2>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              data-testid="confidence-label"
              data-confidence={state.confidence ?? "unknown"}
              aria-label={`Confidence assessment: ${conf}. ${verificationOpen ? "Hide" : "Show"} verification details`}
              aria-expanded={verificationOpen}
              aria-controls="final-answer-verification"
              onClick={() => setVerificationOpen(!verificationOpen)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors hover:opacity-80 ${confColor}`}
            >
              Confidence: {conf}
              <Info className="ml-1 size-3" aria-hidden />
            </button>
            <span className="cin-chip">
              <CheckCircle2 className="size-3.5" aria-hidden />
              {resolvedDisagreementCount === null
                ? "verification unavailable"
                : `${resolvedDisagreementCount} point${resolvedDisagreementCount === 1 ? "" : "s"} resolved`}
            </span>
          </div>
        </div>
        <div className="cin-answer-head-actions">
          <button
            type="button"
            className="cin-btn cin-btn-sm cin-btn-outline"
            onClick={() => void handleCopy()}
            title="Copy Markdown"
          >
            <Copy className="size-4" aria-hidden />
            Copy answer
          </button>
          <button
            type="button"
            className="cin-btn cin-btn-sm cin-btn-outline"
            onClick={handleExport}
            title="Export Markdown"
          >
            <Download className="size-4" aria-hidden />
            Export
          </button>
        </div>
      </header>

      {verificationOpen && (
        <div id="final-answer-verification" className="cin-verification">
          <div>
            <p>Team Size</p>
            <p>
              <Layers className="size-4 text-brand" aria-hidden />{" "}
              {teamCount === null ? "Unavailable" : `${teamCount} Agents`}
            </p>
          </div>
          <div>
            <p>Diversity</p>
            <p>{distinctFamilies === null ? "Unavailable" : `${distinctFamilies} Model Families`}</p>
          </div>
          <div>
            <p>Rounds</p>
            <p>{roundCount === null ? "Unavailable" : `${roundCount} Debate Rounds`}</p>
          </div>
          <div>
            <p>Conflicts Resolved</p>
            <p className="text-success">
              <CheckCircle2 className="size-4" aria-hidden />{" "}
              {resolvedDisagreementCount === null
                ? "Unavailable"
                : `${resolvedDisagreementCount} resolved`}
            </p>
          </div>
        </div>
      )}

      {sourcesFirst && (
        <div className="cin-answer-foot" style={{ marginTop: 20 }}>
          {sourceStrip}
        </div>
      )}

      <div className="cin-answer-body">
        {conf !== "High" && state.uncertaintyNote && (
          <div className="cin-uncertainty">
            <ShieldAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
            <div>
              <h3>What we are unsure about</h3>
              <p>{state.uncertaintyNote}</p>
            </div>
          </div>
        )}

        <div className="assembly-answer-prose max-w-full min-w-0 overflow-x-auto">
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex, rehypeHighlight, [rehypeSanitize, markdownSanitizeSchema]]}
            components={{
              a: ({ ...props }) => {
                // Custom handler for inline citations like [1]
                if (props.href?.startsWith("#source-")) {
                  return (
                    <a
                      {...props}
                      className="ml-1 inline-flex size-5 items-center justify-center rounded bg-brand/10 text-[10px] font-bold text-brand no-underline transition-colors hover:bg-brand hover:text-white"
                      onClick={(e) => {
                        e.preventDefault()
                        document.querySelector(props.href!)?.scrollIntoView({ behavior: "smooth" })
                      }}
                    />
                  )
                }
                return <a {...props} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline" />
              },
            }}
          >
            {state.finalAnswer || ""}
          </ReactMarkdown>
        </div>
      </div>

      <footer className="cin-answer-foot">
        {!sourcesFirst ? sourceStrip : <span className="text-xs text-muted-foreground">Answer cited above.</span>}
        <Link href="/chat" className="cin-btn cin-btn-sm cin-btn-primary">
          Ask another
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      </footer>
    </article>
  )
}
