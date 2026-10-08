"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Progress,
  ProgressIndicator,
  ProgressLabel,
  ProgressTrack,
  ProgressValue,
} from "@/components/ui/progress"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Skeleton } from "@/components/ui/skeleton"
import { Toast, ToastProvider, useToast } from "@/components/ui/toast"
import {
  Zap,
  Brain,
  FlaskConical,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Info,
  Moon,
  Sun,
  ArrowRight,
  Sparkles,
  Users,
  MessageSquare,
} from "lucide-react"

/* ─── Dark mode toggle ───────────────────────────────────────────────────── */
function DarkModeToggle() {
  const [dark, setDark] = React.useState(false)
  React.useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
  }, [dark])
  return (
    <button
      id="dark-mode-toggle"
      onClick={() => setDark((d) => !d)}
      aria-label="Toggle dark mode"
      className="fixed right-5 top-5 z-50 flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-md transition-all hover:bg-muted"
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  )
}

/* ─── Section wrapper ────────────────────────────────────────────────────── */
function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="space-y-5">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">{title}</h2>
        <div className="h-px flex-1 bg-border" />
      </div>
      {children}
    </section>
  )
}

/* ─── Color swatch ───────────────────────────────────────────────────────── */
function ColorSwatch({ name, cssVar, textClass }: { name: string; cssVar: string; textClass?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div
        className="h-12 w-full rounded-lg border border-border/50 shadow-sm"
        style={{ background: `var(${cssVar})` }}
      />
      <div>
        <p className={`text-xs font-medium ${textClass ?? "text-foreground"}`}>{name}</p>
        <p className="font-mono text-[10px] text-muted-foreground">{cssVar}</p>
      </div>
    </div>
  )
}

/* ─── Toast demo ─────────────────────────────────────────────────────────── */
function ToastDemo() {
  const { toast } = useToast()
  const toasts = [
    { label: "Default", variant: "default" as const, title: "Run complete", description: "3 agents reached consensus." },
    { label: "Success", variant: "success" as const, title: "Consensus reached", description: "Agreement score: 0.91" },
    { label: "Warning", variant: "warning" as const, title: "Low confidence", description: "Only 2 of 4 agents agree." },
    { label: "Danger", variant: "danger" as const, title: "Provider error", description: "Gemini rate-limit hit." },
    { label: "Info", variant: "info" as const, title: "Research pass", description: "Verifier found 2 new sources." },
  ]
  return (
    <div className="flex flex-wrap gap-2">
      {toasts.map((t) => (
        <Button
          key={t.variant}
          id={`toast-trigger-${t.variant}`}
          variant="outline"
          size="sm"
          onClick={() => toast({ variant: t.variant, title: t.title, description: t.description })}
        >
          {t.label} toast
        </Button>
      ))}
    </div>
  )
}

/* ─── Main page ──────────────────────────────────────────────────────────── */
export default function StyleguidePage() {
  return (
    <ToastProvider>
      <DarkModeToggle />

      {/* Hero header */}
      <header className="border-b border-border bg-card">
        <div className="mx-auto max-w-5xl px-6 py-10">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-brand-foreground shadow-sm">
              <Zap className="size-5" />
            </span>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">Assembly Design System</h1>
              <p className="text-sm text-muted-foreground">
                Color tokens · Typography · 8 core components — light & dark
              </p>
            </div>
          </div>

          {/* Nav pills */}
          <nav className="mt-6 flex flex-wrap gap-2" aria-label="Section navigation">
            {["colors", "typography", "buttons", "cards", "badges", "progress", "dialog", "tabs", "toasts", "skeleton"].map(
              (id) => (
                <a
                  key={id}
                  href={`#${id}`}
                  className="rounded-full border border-border px-3 py-1 font-mono text-xs capitalize text-muted-foreground transition-colors hover:border-brand hover:text-brand"
                >
                  {id}
                </a>
              )
            )}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-14 px-6 py-12">
        {/* ── Colors ─────────────────────────────────────────────────────── */}
        <Section id="colors" title="Color Tokens">
          <div className="space-y-4">
            <p className="text-sm font-medium text-muted-foreground">Brand & Accent</p>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <ColorSwatch name="brand" cssVar="--brand" />
              <ColorSwatch name="brand-subtle" cssVar="--brand-subtle" />
              <ColorSwatch name="brand-hover" cssVar="--brand-hover" />
              <ColorSwatch name="brand-foreground" cssVar="--brand-foreground" />
            </div>
            <p className="text-sm font-medium text-muted-foreground">Backgrounds</p>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <ColorSwatch name="background" cssVar="--background" />
              <ColorSwatch name="card" cssVar="--card" />
              <ColorSwatch name="muted" cssVar="--muted" />
              <ColorSwatch name="border" cssVar="--border" />
            </div>
            <p className="text-sm font-medium text-muted-foreground">Semantic</p>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <ColorSwatch name="success" cssVar="--success" />
              <ColorSwatch name="warning" cssVar="--warning" />
              <ColorSwatch name="danger" cssVar="--danger" />
              <ColorSwatch name="info" cssVar="--info" />
            </div>
          </div>
        </Section>

        {/* ── Typography ──────────────────────────────────────────────────── */}
        <Section id="typography" title="Typography">
          <div className="rounded-xl border border-border bg-card p-6 space-y-5">
            <div className="space-y-1">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Display / 36px 700</p>
              <p className="text-4xl font-bold tracking-tight">The answer is consensus.</p>
            </div>
            <div className="space-y-1">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Heading 1 / 24px 600</p>
              <p className="text-2xl font-semibold">Assembly agent debate</p>
            </div>
            <div className="space-y-1">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Heading 2 / 18px 600</p>
              <p className="text-lg font-semibold">Round 2 — Cross-examination</p>
            </div>
            <div className="space-y-1">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Body / 14px 400</p>
              <p className="text-sm leading-relaxed text-foreground">
                Assembly turns one question into a temporary team of AI agents that reason independently,
                cross-examine each other, verify with live sources, and synthesise a final answer.
              </p>
            </div>
            <div className="space-y-1">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Caption / 12px 400</p>
              <p className="text-xs text-muted-foreground">Completed in 4m 12s · 3 debate rounds · 91% agreement</p>
            </div>
            <div className="space-y-1">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Code / 13px mono
              </p>
              <code className="block rounded-lg border border-border bg-muted p-3 font-mono text-sm text-foreground">
                {`{ "position": "Gemini outperforms GPT-4o on reasoning", "confidence": 0.82 }`}
              </code>
            </div>
          </div>
        </Section>

        {/* ── Buttons ─────────────────────────────────────────────────────── */}
        <Section id="buttons" title="Button">
          <div className="rounded-xl border border-border bg-card p-6 space-y-6">
            {/* Variants */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Variants</p>
              <div className="flex flex-wrap items-center gap-3">
                <Button id="btn-primary" variant="default">Primary</Button>
                <Button id="btn-secondary" variant="secondary">Secondary</Button>
                <Button id="btn-outline" variant="outline">Outline</Button>
                <Button id="btn-ghost" variant="ghost">Ghost</Button>
                <Button id="btn-destructive" variant="destructive">Destructive</Button>
                <Button id="btn-link" variant="link">Link</Button>
              </div>
            </div>
            {/* Sizes */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Sizes</p>
              <div className="flex flex-wrap items-center gap-3">
                <Button id="btn-xs" size="xs" variant="default">Extra Small</Button>
                <Button id="btn-sm" size="sm" variant="default">Small</Button>
                <Button id="btn-default-size" size="default" variant="default">Default</Button>
                <Button id="btn-lg" size="lg" variant="default">Large</Button>
              </div>
            </div>
            {/* With icons */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">With icons</p>
              <div className="flex flex-wrap items-center gap-3">
                <Button id="btn-icon-brain" variant="default">
                  <Brain className="size-4" />
                  Run analysis
                </Button>
                <Button id="btn-icon-arrow" variant="outline">
                  View results
                  <ArrowRight className="size-4" />
                </Button>
                <Button id="btn-icon-sparkles" variant="ghost">
                  <Sparkles className="size-4" />
                  Synthesise
                </Button>
              </div>
            </div>
            {/* States */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">States</p>
              <div className="flex flex-wrap items-center gap-3">
                <Button id="btn-disabled" variant="default" disabled>Disabled</Button>
                <Button id="btn-loading" variant="outline" disabled>
                  <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Running…
                </Button>
              </div>
            </div>
          </div>
        </Section>

        {/* ── Cards ───────────────────────────────────────────────────────── */}
        <Section id="cards" title="Card">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {/* Basic card */}
            <Card className="transition-all hover:glow-brand hover:-translate-y-0.5">
              <CardHeader>
                <CardTitle>Agent Alpha</CardTitle>
                <CardDescription>Gemini 2.0 Flash · family: gemini</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Quantum computing will achieve practical advantage within 5 years, driven by error-correction
                  breakthroughs at Google and IBM.
                </p>
              </CardContent>
            </Card>

            {/* Card with badge */}
            <Card className="transition-all hover:glow-brand hover:-translate-y-0.5">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  Consensus Engine
                  <span
                    className="rounded-full border border-green-500/30 bg-green-500/10 px-2 py-0.5 font-mono text-[10px] font-medium text-green-600 dark:text-green-400"
                  >
                    Agreed
                  </span>
                </CardTitle>
                <CardDescription>Round 3 · 4 agents</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold text-brand">0.91</span>
                  <span className="text-sm text-muted-foreground">agreement score</span>
                </div>
              </CardContent>
              <CardFooter>
                <p className="text-xs text-muted-foreground">Adversarial round skipped — agreement above threshold</p>
              </CardFooter>
            </Card>

            {/* Research card */}
            <Card className="border-info/20 bg-info-subtle transition-all hover:-translate-y-0.5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-info">
                  <FlaskConical className="size-4" />
                  Researcher Agent
                </CardTitle>
                <CardDescription className="text-info/60">Verifying with web sources…</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-info/80 leading-relaxed">
                  Found 3 peer-reviewed papers supporting the position. 1 source contradicts claim about timeline.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        {/* ── Badges ──────────────────────────────────────────────────────── */}
        <Section id="badges" title="Badge">
          <div className="rounded-xl border border-border bg-card p-6 space-y-6">
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Built-in shadcn variants
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Badge id="badge-default" variant="default">Default</Badge>
                <Badge id="badge-secondary" variant="secondary">Secondary</Badge>
                <Badge id="badge-outline" variant="outline">Outline</Badge>
                <Badge id="badge-destructive" variant="destructive">Destructive</Badge>
              </div>
            </div>
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Assembly semantic (CSS variable classes)
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <span id="badge-brand" className="inline-flex items-center gap-1 rounded-full border border-brand/30 bg-brand-subtle px-2.5 py-0.5 text-xs font-medium text-brand">
                  <Zap className="size-3" />Brand
                </span>
                <span id="badge-success" className="inline-flex items-center gap-1 rounded-full border border-success/30 bg-success-subtle px-2.5 py-0.5 text-xs font-medium text-success">
                  <CheckCircle2 className="size-3" />Consensus
                </span>
                <span id="badge-warning" className="inline-flex items-center gap-1 rounded-full border border-warning/30 bg-warning-subtle px-2.5 py-0.5 text-xs font-medium text-warning">
                  <AlertTriangle className="size-3" />Low confidence
                </span>
                <span id="badge-danger" className="inline-flex items-center gap-1 rounded-full border border-danger/30 bg-danger-subtle px-2.5 py-0.5 text-xs font-medium text-danger">
                  <XCircle className="size-3" />Disagreement
                </span>
                <span id="badge-info" className="inline-flex items-center gap-1 rounded-full border border-info/30 bg-info-subtle px-2.5 py-0.5 text-xs font-medium text-info">
                  <Info className="size-3" />Verifying
                </span>
              </div>
            </div>
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Model family tags
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {[
                  { name: "gemini", color: "#4285F4" },
                  { name: "llama", color: "#7C3AED" },
                  { name: "qwen", color: "#059669" },
                  { name: "deepseek", color: "#DC2626" },
                  { name: "mistral", color: "#EA580C" },
                  { name: "kimi", color: "#0EA5E9" },
                ].map((f) => (
                  <span
                    key={f.name}
                    className="inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-xs font-medium"
                    style={{
                      borderColor: f.color + "40",
                      background: f.color + "14",
                      color: f.color,
                    }}
                  >
                    {f.name}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </Section>

        {/* ── Progress ─────────────────────────────────────────────────────── */}
        <Section id="progress" title="Progress">
          <div className="rounded-xl border border-border bg-card p-6 space-y-6">
            <div className="space-y-4">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Determinate
              </p>
              {[
                { label: "Agent solving", value: 30 },
                { label: "Debate rounds", value: 66 },
                { label: "Consensus", value: 91 },
              ].map(({ label, value }) => (
                <Progress key={label} value={value} className="w-full">
                  <ProgressLabel>{label}</ProgressLabel>
                  <ProgressValue />
                  <ProgressTrack>
                    <ProgressIndicator className="bg-brand transition-all duration-700" />
                  </ProgressTrack>
                </Progress>
              ))}
            </div>
            <div className="space-y-4">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Indeterminate (null value)
              </p>
              <Progress value={null} className="w-full">
                <ProgressLabel>Waiting for providers…</ProgressLabel>
                <ProgressTrack className="h-1.5">
                  <ProgressIndicator className="animate-progress-indeterminate bg-brand" />
                </ProgressTrack>
              </Progress>
            </div>
          </div>
        </Section>

        {/* ── Dialog ──────────────────────────────────────────────────────── */}
        <Section id="dialog" title="Dialog">
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex flex-wrap gap-3">
              <Dialog>
                <DialogTrigger
                  render={
                    <Button id="dialog-trigger-default" variant="default">
                      <Brain className="size-4" />
                      Start new run
                    </Button>
                  }
                />
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Configure your run</DialogTitle>
                    <DialogDescription>
                      Set your question and time budget. Assembly will form a temporary team and begin reasoning
                      immediately.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-3 py-1">
                    <div className="space-y-1.5">
                      <label className="text-sm font-medium text-foreground" htmlFor="run-question">
                        Question
                      </label>
                      <textarea
                        id="run-question"
                        rows={3}
                        placeholder="Will quantum computing achieve commercial advantage before 2030?"
                        className="w-full resize-none rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
                      />
                    </div>
                    <div className="flex gap-2">
                      {[3, 5, 10, 15].map((min) => (
                        <button
                          key={min}
                          className="flex-1 rounded-lg border border-border py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:border-brand hover:bg-brand-subtle hover:text-brand"
                        >
                          {min}m
                        </button>
                      ))}
                    </div>
                  </div>
                  <DialogFooter showCloseButton>
                    <Button id="dialog-submit" variant="default" className="w-full sm:w-auto">
                      <Zap className="size-4" />
                      Launch
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              <Dialog>
                <DialogTrigger
                  render={
                    <Button id="dialog-trigger-outline" variant="outline">
                      View key details
                    </Button>
                  }
                />
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>API Key</DialogTitle>
                    <DialogDescription>
                      Your key is stored only in your browser and never leaves your machine.
                    </DialogDescription>
                  </DialogHeader>
                  <code className="block rounded-lg border border-border bg-muted px-3 py-2 font-mono text-xs text-muted-foreground">
                    sk-••••••••••••••••••••••••••••••••
                  </code>
                </DialogContent>
              </Dialog>
            </div>
          </div>
        </Section>

        {/* ── Tabs ────────────────────────────────────────────────────────── */}
        <Section id="tabs" title="Tabs">
          <div className="rounded-xl border border-border bg-card p-6 space-y-8">
            {/* Default pill tabs */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Default (pill)
              </p>
              <Tabs defaultValue="agents">
                <TabsList>
                  <TabsTrigger value="agents">
                    <Users className="size-3.5" />
                    Agents
                  </TabsTrigger>
                  <TabsTrigger value="debate">
                    <MessageSquare className="size-3.5" />
                    Debate
                  </TabsTrigger>
                  <TabsTrigger value="synthesis">
                    <Sparkles className="size-3.5" />
                    Synthesis
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="agents" className="pt-3">
                  <p className="text-sm text-muted-foreground">
                    4 agents formed · 3 distinct model families · Planner assigned roles based on question type.
                  </p>
                </TabsContent>
                <TabsContent value="debate" className="pt-3">
                  <p className="text-sm text-muted-foreground">
                    Round 2 complete · Critic challenged Agent Beta's timeline claim · Researcher found contradicting evidence.
                  </p>
                </TabsContent>
                <TabsContent value="synthesis" className="pt-3">
                  <p className="text-sm text-muted-foreground">
                    Final answer synthesised · 91% agreement · 3 web sources verified · Uncertainty note included.
                  </p>
                </TabsContent>
              </Tabs>
            </div>

            {/* Line variant */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Line (underline)
              </p>
              <Tabs defaultValue="output">
                <TabsList variant="line">
                  <TabsTrigger value="output">Output</TabsTrigger>
                  <TabsTrigger value="trace">Trace</TabsTrigger>
                  <TabsTrigger value="metrics">Metrics</TabsTrigger>
                </TabsList>
                <TabsContent value="output" className="pt-3">
                  <code className="block rounded-lg border border-border bg-muted p-3 font-mono text-xs text-foreground">
                    {"{ \"answer\": \"Quantum advantage likely by 2028–2030...\", \"confidence\": 0.82 }"}
                  </code>
                </TabsContent>
                <TabsContent value="trace" className="pt-3">
                  <p className="text-sm text-muted-foreground">
                    14 orchestration events · 4m 12s total · 3 WebSocket messages
                  </p>
                </TabsContent>
                <TabsContent value="metrics" className="pt-3">
                  <p className="text-sm text-muted-foreground">
                    Tokens: 28,400 · Rounds: 3 · New-info rate: 0.34
                  </p>
                </TabsContent>
              </Tabs>
            </div>
          </div>
        </Section>

        {/* ── Toast ───────────────────────────────────────────────────────── */}
        <Section id="toasts" title="Toast">
          <div className="rounded-xl border border-border bg-card p-6 space-y-4">
            <p className="text-sm text-muted-foreground">
              Toasts stack from the bottom-right. Hover to pause auto-dismiss (4s default).
            </p>
            <ToastDemo />
            {/* Static preview of each variant */}
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <Toast title="Run complete" description="3 agents reached consensus." variant="default" duration={999999} />
              <Toast title="Consensus reached" description="Agreement score: 0.91" variant="success" duration={999999} />
              <Toast title="Low confidence" description="Only 2 of 4 agents agree." variant="warning" duration={999999} />
              <Toast title="Provider error" description="Gemini rate-limit hit." variant="danger" duration={999999} />
              <Toast title="Research pass" description="Verifier found 2 new sources." variant="info" duration={999999} />
            </div>
          </div>
        </Section>

        {/* ── Skeleton ─────────────────────────────────────────────────────── */}
        <Section id="skeleton" title="Skeleton">
          <div className="rounded-xl border border-border bg-card p-6 space-y-6">
            {/* Card skeleton */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Card skeleton</p>
              <div className="grid gap-4 sm:grid-cols-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="space-y-3 rounded-xl border border-border bg-muted/50 p-4">
                    <div className="flex items-center gap-2">
                      <Skeleton className="h-8 w-8 rounded-full" />
                      <div className="space-y-1.5 flex-1">
                        <Skeleton className="h-3 w-3/4 animate-shimmer" />
                        <Skeleton className="h-2.5 w-1/2 animate-shimmer" />
                      </div>
                    </div>
                    <Skeleton className="h-3 w-full animate-shimmer" />
                    <Skeleton className="h-3 w-5/6 animate-shimmer" />
                    <Skeleton className="h-3 w-4/6 animate-shimmer" />
                  </div>
                ))}
              </div>
            </div>
            {/* Agent skeleton */}
            <div className="space-y-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Agent output skeleton
              </p>
              <div className="space-y-2 rounded-xl border border-border bg-muted/50 p-4">
                <div className="flex items-center gap-3">
                  <Skeleton className="h-5 w-5 rounded" />
                  <Skeleton className="h-4 w-32 animate-shimmer" />
                  <Skeleton className="ml-auto h-4 w-12 rounded-full animate-shimmer" />
                </div>
                <Skeleton className="h-3 w-full animate-shimmer" />
                <Skeleton className="h-3 w-full animate-shimmer" />
                <Skeleton className="h-3 w-3/4 animate-shimmer" />
                <div className="flex gap-2 pt-1">
                  <Skeleton className="h-5 w-16 rounded-full animate-shimmer" />
                  <Skeleton className="h-5 w-20 rounded-full animate-shimmer" />
                </div>
              </div>
            </div>
          </div>
        </Section>
      </main>

      {/* Footer */}
      <footer className="mt-8 border-t border-border py-6 text-center">
        <p className="text-xs text-muted-foreground">
          Assembly Design System · Next.js 16 · Tailwind v4 · shadcn/ui (base-ui) · Inter + JetBrains Mono
        </p>
      </footer>
    </ToastProvider>
  )
}
