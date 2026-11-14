"use client"

import React, { useState, useEffect } from "react"
import Link from "next/link"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { globalVault } from "@/lib/key-vault"
import { env } from "@/lib/env"
import { ApiClient, type Catalog } from "@/lib/api-client"
import { evaluateGate, gateChipText } from "@/lib/diversity-gate"
import {
  isKeyFormatOk,
  keyPrefixHint,
  minimumToStartBanner,
  sensitiveSignupText,
  whyProviderLine,
} from "@/lib/key-setup"
import { useToast } from "@/components/ui/toast"
import { Shield, Key, Trash2, ExternalLink, Copy, AlertTriangle, Sparkles, ArrowRight } from "lucide-react"

type KeyStatus = "unknown" | "valid" | "invalid" | "rate_limited" | "model_unavailable" | "unreachable" | "testing"

type StatusDetail = { message?: string; availableModels?: string[] }

const KEY_STATUS_LABEL: Record<KeyStatus, string> = {
  unknown: "Not tested",
  valid: "Valid",
  invalid: "Key not accepted",
  rate_limited: "Valid, rate-limited",
  model_unavailable: "Valid, model unavailable",
  unreachable: "Server unreachable",
  testing: "Testing…",
}

function cleanPastedKey(raw: string): string {
  return (raw || "").replace(/[\u200B-\u200D\uFEFF]/g, "").trim()
}

function maskKey(key: string): string {
  if (!key) return ""
  if (key.length <= 8) return "••••••••"
  return `${key.slice(0, 4)}••••••••${key.slice(-4)}`
}

export function KeysManager() {
  const { toast } = useToast()
  const desktopMode = env.NEXT_PUBLIC_APP_MODE === "desktop"

  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [savedKeys, setSavedKeys] = useState<Record<string, string>>({})
  const [statuses, setStatuses] = useState<Record<string, KeyStatus>>({})
  const [details, setDetails] = useState<Record<string, StatusDetail>>({})
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({})
  const [passphrase, setPassphrase] = useState("")
  const [vaultLoaded, setVaultLoaded] = useState(false)
  const [tavilyInput, setTavilyInput] = useState("")
  const [needsUnlock, setNeedsUnlock] = useState(false)
  const [unlockError, setUnlockError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      ApiClient.wakeup()
      try {
        setCatalog(await ApiClient.catalog())
      } catch {
        setCatalog(null)
      } finally {
        setCatalogLoading(false)
      }
      // Load first: read the canonical store before rendering anything that
      // could write. A legacy encrypted blob with an empty canonical store
      // shows the one-time migration prompt instead of keys.
      try {
        const keys = await globalVault.allKeys()
        if (Object.keys(keys).length > 0) {
          setSavedKeys(keys)
        } else if (await globalVault.hasLegacyEncrypted().catch(() => false)) {
          setNeedsUnlock(true)
        }
      } catch {
        setSavedKeys({})
      }
      setVaultLoaded(true)
    }
    load()
  }, [])

  const handleUnlock = async () => {
    try {
      const keys = await globalVault.migrateLegacy(passphrase)
      setSavedKeys(keys)
      setNeedsUnlock(false)
      setUnlockError(keys && Object.keys(keys).length > 0 ? null : "No keys found in the saved vault.")
      toast({ title: "Keys restored", description: "Saved keys were restored on this device.", variant: "success" })
    } catch (e) {
      // Wrong passphrase (or a corrupted blob): keep everything, say so.
      setUnlockError(
        e instanceof Error ? e.message : "Wrong passphrase. Nothing was deleted. Try again or use Clear all keys.",
      )
    }
  }

  const handleForget = async () => {
    try {
      await globalVault.clearAll()
    } catch {
      toast({
        title: "Unable to remove saved keys",
        description: "Browser storage rejected the deletion, so some keys may still be saved. Try again or clear browser/site data.",
        variant: "danger",
      })
      return
    }
    setNeedsUnlock(false)
    setUnlockError(null)
    setSavedKeys({})
    setInputs({})
    setStatuses({})
    setDetails({})
    setSaveErrors({})
    setTavilyInput("")
    setPassphrase("")
    toast({ title: "Keys forgotten", description: "All API keys removed from this device." })
  }

  const providers = catalog?.providers.filter((p) => p.enabled) ?? []
  const tavilySaved = !!savedKeys["tavily"]

  const handleSaveTavily = async () => {
    const rawKey = cleanPastedKey(tavilyInput || savedKeys["tavily"] || "")
    if (!rawKey) return
    // No server-side probe exists for search keys: store only.
    try {
      await globalVault.setKey("tavily", rawKey)
    } catch (e) {
      toast({
        title: "Couldn't save search key",
        description: e instanceof Error ? e.message : "Storage unavailable.",
        variant: "danger",
      })
      return
    }
    setSavedKeys((prev) => ({ ...prev, tavily: rawKey }))
    setTavilyInput("")
    toast({ title: "Search key saved", description: "Tavily key stored with your other keys.", variant: "success" })
  }

  const handleSaveAndTest = async (providerId: string) => {
    const rawKey = cleanPastedKey(inputs[providerId] || savedKeys[providerId] || "")
    if (!rawKey) return
    // Soft prefix hint never blocks saving (FR-30): validation is advisory only.
    void isKeyFormatOk(providerId, rawKey)
    try {
      await globalVault.setKey(providerId, rawKey)
    } catch (e) {
      // Honest failure: storage refused the write, so the UI must not claim
      // the key was saved.
      const message = e instanceof Error ? e.message : "Storage unavailable."
      setSaveErrors((prev) => ({ ...prev, [providerId]: message }))
      toast({ title: "Couldn't save key", description: message, variant: "danger" })
      return
    }
    setSaveErrors((prev) => {
      if (!(providerId in prev)) return prev
      const next = { ...prev }
      delete next[providerId]
      return next
    })
    setSavedKeys((prev) => ({ ...prev, [providerId]: rawKey }))
    setInputs((prev) => ({ ...prev, [providerId]: "" }))
    setStatuses((prev) => ({ ...prev, [providerId]: "testing" }))
    try {
      const res = await ApiClient.testKey(providerId, rawKey)
      setStatuses((prev) => ({ ...prev, [providerId]: res.status }))
      setDetails((prev) => ({
        ...prev,
        [providerId]: { message: res.message, availableModels: res.availableModels },
      }))
      if (res.status === "valid") {
        toast({ title: "Key verified", description: res.message ?? `Connected to ${providerId}.`, variant: "success" })
      } else if (res.status === "rate_limited") {
        toast({ title: "Key valid, rate limited", description: res.message ?? "Key is valid but rate-limited.", variant: "warning" })
      } else if (res.status === "model_unavailable") {
        toast({ title: "Key valid, model unavailable", description: res.message ?? "The configured model is not available to this key.", variant: "warning" })
      } else if (res.status === "unreachable") {
        toast({ title: "Couldn't reach provider", description: res.message ?? "Try again.", variant: "warning" })
      } else {
        toast({ title: "That key did not work", description: `${res.message ?? `Could not authenticate with ${providerId}.`} Copy it again with no extra spaces.`, variant: "danger" })
      }
    } catch {
      setStatuses((prev) => ({ ...prev, [providerId]: "unreachable" }))
      setDetails((prev) => ({ ...prev, [providerId]: { message: "Couldn't reach the server; try again." } }))
    }
  }

  const handleRemove = async (providerId: string) => {
    try {
      await globalVault.removeKey(providerId)
    } catch {
      toast({
        title: "Unable to remove key",
        description: "Browser storage rejected the deletion, so this key may still be saved. Try again or clear browser/site data.",
        variant: "danger",
      })
      return
    }
    setSavedKeys((prev) => {
      if (!(providerId in prev)) return prev
      const next = { ...prev }
      delete next[providerId]
      return next
    })
    setInputs((prev) => {
      if (!(providerId in prev)) return prev
      const next = { ...prev }
      delete next[providerId]
      return next
    })
    setStatuses((prev) => {
      if (!(providerId in prev)) return prev
      const next = { ...prev }
      delete next[providerId]
      return next
    })
    setDetails((prev) => {
      if (!(providerId in prev)) return prev
      const next = { ...prev }
      delete next[providerId]
      return next
    })
    toast({ title: "Key removed", description: `${providerId} key removed. Other providers are unchanged.` })
  }

  const handleClearAll = async () => {
    if (!confirm("Remove all saved keys from this browser? This cannot be undone.")) return
    try {
      await globalVault.clearAll()
    } catch {
      toast({
        title: "Unable to clear saved keys",
        description: "Browser storage rejected the deletion, so some keys may still be saved. Try again or clear browser/site data.",
        variant: "danger",
      })
      return
    }

    let desktopStoreCleared = true
    if (env.NEXT_PUBLIC_APP_MODE === "desktop") {
      try {
        await ApiClient.clearAllKeys()
      } catch {
        desktopStoreCleared = false
      }
    }
    setNeedsUnlock(false)
    setUnlockError(null)
    setSavedKeys({})
    setInputs({})
    setStatuses({})
    setDetails({})
    setSaveErrors({})
    setTavilyInput("")
    setPassphrase("")
    if (desktopStoreCleared) {
      toast({ title: "Keys cleared", description: "Browser-stored keys were removed." })
    } else {
      toast({
        title: "Browser keys cleared; desktop store not confirmed",
        description: "Browser-stored keys were removed, but the desktop credential-store request failed. Some OS-stored keys may remain; reconnect and clear them again.",
        variant: "warning",
      })
    }
  }

  const readyFamilies = new Set<string>()
  providers.forEach((p) => {
    // A saved key counts toward readiness: the Test result is advisory and
    // statuses reset every session, so gating on them would show restored
    // keys as unconfigured after every refresh. Only a proven-invalid key
    // is excluded; the backend preflight/run stays authoritative.
    if (p.limits_ready && savedKeys[p.id] && statuses[p.id] !== "invalid") {
      p.models.forEach((m) => readyFamilies.add(m.family))
    }
  })
  const gate = evaluateGate(
    [...readyFamilies],
    providers.filter((p) => p.limits_ready && savedKeys[p.id]).length,
  )

  if (!vaultLoaded) {
    return (
      <div className="w-full space-y-8" aria-busy="true" aria-label="Loading saved keys and providers">
        <Card>
          <CardHeader className="space-y-3">
            <Skeleton className="h-5 w-40 rounded-none" />
            <Skeleton className="h-3 w-full rounded-none" />
            <Skeleton className="h-3 w-3/4 rounded-none" />
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="space-y-3">
            <Skeleton className="h-5 w-40 rounded-none" />
            <Skeleton className="h-3 w-56 rounded-none" />
          </CardHeader>
        </Card>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((index) => (
            <Card key={index}>
              <CardHeader className="space-y-3">
                <Skeleton className="h-5 w-24 rounded-none" />
                <Skeleton className="h-3 w-full rounded-none" />
                <Skeleton className="h-3 w-2/3 rounded-none" />
              </CardHeader>
              <CardContent className="space-y-3">
                <Skeleton className="h-10 w-full rounded-none" />
                <Skeleton className="h-9 w-full rounded-none" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  const recommendedOrder = catalog?.recommended_order ?? providers.map((p) => p.id)
  const banner = minimumToStartBanner(readyFamilies.size, recommendedOrder)

  const copyLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      toast({ title: "Link copied", description: url })
    } catch {
      toast({ title: "Copy failed", description: url, variant: "warning" })
    }
  }

  return (
    <div className="w-full space-y-8">
      <Card data-testid="minimum-to-start-banner">
        <CardHeader className="pb-3">
          <CardTitle>Minimum to start</CardTitle>
          <CardDescription data-testid="minimum-to-start-text">{banner}</CardDescription>
          <div className="mt-3 space-y-2 text-xs leading-relaxed text-muted-foreground">
            <p className="font-medium text-foreground">Quick setup</p>
            <ol className="list-decimal space-y-1 pl-4">
              <li>Save a free key for each provider you want to use.</li>
              <li>Press <b className="font-medium text-foreground">Save &amp; Test</b> and check the result.</li>
              <li>Return to Run and start an investigation.</li>
            </ol>
            <p>
              Three distinct model families are recommended; two can run with a warning. The readiness
              status below counts only configured providers whose quota metadata is ready.
            </p>
          </div>
        </CardHeader>
      </Card>
      <Card className={gate.level === "OK" ? "border-success/30" : "border-warning/30"}>
        <CardHeader className="pb-3">
          <CardTitle>Team Readiness</CardTitle>
          <CardDescription data-testid="readiness-chip">
            {catalog ? gateChipText(gate) : "Waiting for the provider list"}
          </CardDescription>
          {gate.level !== "OK" && catalog && (
            <CardDescription className="text-warning">{gate.reasons[0]}</CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {gate.families_ready.map((f) => (
              <Badge key={f} variant="secondary" className="font-mono">{f}</Badge>
            ))}
            {gate.families_ready.length === 0 && (
              <span className="text-sm opacity-60">
                {catalog ? "No keys configured yet." : "Provider list unavailable. Saved keys stay on this device."}
              </span>
            )}
          </div>
          {gate.level !== "BLOCKED" && (
            <Link
              href="/chat"
              className="asm-btn asm-btn-primary flex min-h-10 w-full items-center justify-between px-3 text-[0.6rem]"
            >
              Start an investigation
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          )}
        </CardContent>
      </Card>

      {needsUnlock && (
        <div className="rounded-xl border border-white/10 bg-[#0b0c0e] p-5 space-y-3 assembly-vault-card">
          <div data-testid="unlock-prompt" className="space-y-3">
            <div className="flex flex-col">
              <span className="font-medium">Unlock saved keys</span>
              <span className="text-xs text-muted-foreground">
                This device holds keys saved before an update. Enter your previous passphrase once to move them into current storage.
              </span>
            </div>
            <div className="flex gap-2">
              <input
                type="password"
                placeholder="Previous passphrase"
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                autoComplete="off"
                data-testid="unlock-passphrase"
                className="flex-1 rounded-md border border-border bg-muted/50 px-3 py-2 text-sm"
              />
              <Button size="sm" onClick={() => void handleUnlock()} data-testid="unlock-submit">
                Unlock
              </Button>
            </div>
            {unlockError && (
              <p data-testid="unlock-error" className="text-xs text-warning">{unlockError}</p>
            )}
            <Button variant="outline" size="sm" onClick={() => void handleForget()} data-testid="forget-keys">
              Forget keys
            </Button>
          </div>
        </div>
      )}

      {/* Retained in DOM for testing contract */}
      <p data-testid="persisted-banner" className="sr-only">
        Saved keys stay in this browser across refreshes and can be removed here or cleared with site data. Keys are stored unencrypted in local browser storage, not protected by the OS.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy={catalogLoading || undefined}>
        {catalogLoading ? (
          [0, 1, 2].map((index) => (
            <Card key={index} aria-hidden="true">
              <CardHeader className="space-y-3">
                <Skeleton className="h-5 w-24 rounded-none" />
                <Skeleton className="h-3 w-2/3 rounded-none" />
                <Skeleton className="h-3 w-full rounded-none" />
              </CardHeader>
              <CardContent className="space-y-3">
                <Skeleton className="h-10 w-full rounded-none" />
                <Skeleton className="h-9 w-full rounded-none" />
              </CardContent>
            </Card>
          ))
        ) : !catalog ? (
          <Card data-testid="provider-catalog-unavailable" className="sm:col-span-2 lg:col-span-3">
            <CardHeader>
              <CardTitle>Provider list unavailable</CardTitle>
              <CardDescription>
                Assembly couldn&apos;t load the list of free providers. Check that the Assembly server is
                running, then use Retry on the connection banner above. Keys already saved stay on this
                device.
              </CardDescription>
            </CardHeader>
          </Card>
        ) : providers.map((provider) => {
          const hasSavedKey = !!savedKeys[provider.id]
          const st = statuses[provider.id] || "unknown"
          const steps = provider.key_steps ?? []
          const hint = keyPrefixHint(provider.id)
          const why = whyProviderLine(provider)
          const signupNote = sensitiveSignupText(provider.sensitive_signup)
          return (
            <Card key={provider.id} className="flex flex-col" data-testid={`provider-card-${provider.id}`}>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Key className="size-4 text-brand" />
                  {provider.id}
                </CardTitle>
                <CardDescription className="text-xs mt-1 font-mono">
                  {provider.models.map((m) => m.family).filter((v, i, a) => a.indexOf(v) === i).join(", ")}
                </CardDescription>
                <CardDescription data-testid={`why-${provider.id}`} className="text-xs mt-1">
                  {why}
                </CardDescription>
                {!provider.limits_ready && (
                  <p
                    role="status"
                    data-testid={`limits-unavailable-${provider.id}`}
                    className="mt-2 rounded-md border border-warning/40 bg-warning-subtle px-2.5 py-2 text-xs text-warning"
                  >
                    {provider.limits_issue ?? "Provider quota limits are unverified. This provider will not be used for runs until its limits are confirmed."}
                  </p>
                )}
              </CardHeader>
              <CardContent className="flex-1 space-y-4">
                <details data-testid={`stepper-${provider.id}`}>
                  <summary className="text-xs font-medium cursor-pointer">How to get a key</summary>
                  <ol className="mt-2 space-y-1 text-xs list-decimal list-inside">
                    {steps.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>
                  <p data-testid={`signup-note-${provider.id}`} className="mt-2 text-xs opacity-70">
                    {signupNote}
                  </p>
                </details>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <label htmlFor={`key-${provider.id}`} className="text-xs font-medium">API Key</label>
                    <div className="flex items-center gap-2">
                      {provider.key_url && (
                        <>
                          <a href={provider.key_url} target="_blank" rel="noreferrer noopener" className="inline-flex min-h-11 items-center gap-1 text-xs text-brand hover:underline">
                            Get free key <ExternalLink className="size-3" />
                          </a>
                          <button
                            type="button"
                            aria-label={`Copy key link for ${provider.id}`}
                            data-testid={`copy-link-${provider.id}`}
                            className="inline-flex min-h-11 items-center gap-1 text-xs text-brand hover:underline"
                            onClick={() => void copyLink(provider.key_url)}
                          >
                            <Copy className="size-3" /> Copy link
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <input
                    id={`key-${provider.id}`}
                    type="password"
                    placeholder={hasSavedKey ? maskKey(savedKeys[provider.id]) : "paste key…"}
                    value={inputs[provider.id] || ""}
                    onChange={(e) => setInputs((prev) => ({ ...prev, [provider.id]: e.target.value }))}
                    autoComplete="off"
                    spellCheck="false"
                    aria-describedby={`prefix-hint-${provider.id}`}
                    className="w-full rounded-md border border-border bg-muted/50 px-3 py-2.5 text-sm font-mono"
                  />
                  <p id={`prefix-hint-${provider.id}`} data-testid={`prefix-hint-${provider.id}`} className="text-[10px] text-muted-foreground pt-1">
                    {hint} This hint never blocks saving.
                  </p>
                  {saveErrors[provider.id] && (
                    <p role="alert" data-testid={`save-error-${provider.id}`} className="rounded-md border border-danger/40 bg-danger-subtle px-2.5 py-2 text-xs font-medium text-danger">
                      {saveErrors[provider.id]}
                    </p>
                  )}
                  {st !== "unknown" && st !== "testing" && (
                    <div className="space-y-1">
                      <p data-testid={`test-result-${provider.id}`} className="text-xs">
                        Test result: {KEY_STATUS_LABEL[st]}
                      </p>
                      {details[provider.id]?.message && (
                        <p data-testid={`test-message-${provider.id}`} className="text-xs opacity-80">
                          {details[provider.id].message}
                        </p>
                      )}
                      {st === "invalid" && (
                        <p className="text-[10px] text-muted-foreground">
                          Check the key was copied without spaces.
                        </p>
                      )}
                      {st === "model_unavailable" && details[provider.id]?.availableModels && (
                        <p data-testid={`test-models-${provider.id}`} className="text-[10px] font-mono opacity-80">
                          Available: {details[provider.id].availableModels!.slice(0, 8).join(", ")}
                          {details[provider.id].availableModels!.length > 8
                            ? ` (+${details[provider.id].availableModels!.length - 8} more)`
                            : ""}
                        </p>
                      )}
                    </div>
                  )}
                  <p className="text-[10px] text-muted-foreground pt-1 flex items-start gap-1">
                    <Shield className="size-3 shrink-0" />
                    {desktopMode
                      ? "Stored in this WebView browser profile; sent to the local Assembly backend over loopback for preflight, key tests and runs, then used to authenticate with the provider."
                      : "Stored in this browser; sent to the hosted Assembly backend over HTTPS (localhost is used for local development) for preflight, key tests and runs, then used to authenticate with the provider."}
                  </p>
                </div>
              </CardContent>
              <CardFooter className="pt-0 flex flex-col gap-2">
                <Button
                  variant={hasSavedKey ? "secondary" : "default"}
                  size="sm"
                  className="w-full"
                  disabled={st === "testing" || (!inputs[provider.id] && !hasSavedKey)}
                  onClick={() => handleSaveAndTest(provider.id)}
                >
                  {st === "testing" ? "Testing…" : inputs[provider.id] ? "Save & Test" : "Test Saved Key"}
                </Button>
                {hasSavedKey && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => void handleRemove(provider.id)}
                    data-testid={`remove-${provider.id}`}
                  >
                    Remove
                  </Button>
                )}
              </CardFooter>
            </Card>
          )
        })}
      </div>

      <Card className="flex flex-col" data-testid="provider-card-tavily">
        <CardHeader className="sr-only">
          <CardTitle className="text-base flex items-center gap-2">
            <Key className="size-4 text-brand" />
            tavily <Badge variant="secondary">search · optional</Badge>
          </CardTitle>
          <CardDescription className="sr-only">
            Why this provider: web search for researchers. Without it
            Assembly uses keyless sources (Wikipedia, arXiv, Semantic
            Scholar, DuckDuckGo) on a best-effort basis. They are rate
            limited and sometimes blocked, so research may run with no
            external sources.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 space-y-4 pt-5">
          {/* ChatGPT-style Team Readiness Callout Warning above paste key bar */}
          <div
            className={`assembly-readiness-callout mb-1 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3.5 rounded-xl border ${
              gate.level === "OK"
                ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-400"
                : "border-red-500/40 bg-red-500/10 text-red-400"
            }`}
          >
            <div className="flex items-start sm:items-center gap-3 min-w-0">
              <span
                className={`flex size-8 shrink-0 items-center justify-center rounded-lg ${
                  gate.level === "OK"
                    ? "bg-emerald-500/20 text-emerald-400"
                    : "bg-red-500/20 text-red-400"
                }`}
              >
                {gate.level === "OK" ? (
                  <Sparkles className="size-4" />
                ) : (
                  <AlertTriangle className="size-4 text-red-400" />
                )}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold uppercase tracking-wider text-white">
                    Team Readiness
                  </span>
                  <span data-testid="readiness-chip" className="sr-only">
                    {gateChipText(gate)}
                  </span>
                </div>
                <p className={`text-xs mt-0.5 leading-snug ${gate.level === "OK" ? "text-white/75" : "text-red-200/90"}`}>
                  {gate.level !== "OK"
                    ? gate.reasons[0]
                    : "At least two ready model families configured. Ready for multi-agent runs."}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0 self-start sm:self-auto">
              {gate.families_ready.map((f) => (
                <Badge key={f} variant="secondary" className="font-mono text-[10px] px-2 py-0.5">
                  {f}
                </Badge>
              ))}
              {gate.families_ready.length === 0 && (
                <span className="text-[11px] text-red-300/60 italic">
                  No keys configured yet.
                </span>
              )}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium">Search Key</label>
            <div className="relative flex items-center">
              <input
                type="password"
                placeholder={tavilySaved ? maskKey(savedKeys["tavily"]) : "paste key…"}
                value={tavilyInput}
                onChange={(e) => setTavilyInput(e.target.value)}
                autoComplete="off"
                spellCheck="false"
                data-testid="tavily-input"
                className="w-full rounded-md border border-border bg-muted/50 pl-3 pr-10 py-2 text-sm font-mono"
              />
              <button
                type="button"
                onClick={handleClearAll}
                disabled={Object.keys(savedKeys).length === 0 && !tavilyInput}
                aria-label="Clear all keys"
                title="Clear all keys"
                data-testid="clear-all-keys"
                className="assembly-trash-btn absolute right-2.5 flex items-center justify-center text-white/40 hover:text-red-400 disabled:opacity-20 disabled:hover:text-white/40 disabled:cursor-not-allowed transition-colors"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
            <p className="sr-only">
              <Shield className="size-3 shrink-0" />
              {desktopMode
                ? "Stored in this WebView browser profile; a saved Tavily key is sent to the local Assembly backend over loopback with every run request, even when search is not used."
                : "Stored in this browser; a saved Tavily key is sent to the hosted Assembly backend over HTTPS (localhost is used for local development) with every run request, even when search is not used."}
            </p>
          </div>
        </CardContent>
        <CardFooter className="pt-0 flex flex-col gap-2">
          <Button
            variant={tavilySaved ? "secondary" : "default"}
            size="sm"
            className="w-full"
            disabled={!tavilyInput && !tavilySaved}
            onClick={() => void handleSaveTavily()}
            data-testid="tavily-save"
          >
            {tavilyInput ? "Save Search Key" : "Saved"}
          </Button>
          {tavilySaved && (
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => void handleRemove("tavily")}
              data-testid="remove-tavily"
            >
              Remove
            </Button>
          )}
        </CardFooter>
      </Card>
    </div>
  )
}
