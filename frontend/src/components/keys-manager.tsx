"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { globalVault } from "@/lib/key-vault"
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
import { Shield, Key, Trash2, ExternalLink, Copy } from "lucide-react"

type KeyStatus = "unknown" | "valid" | "invalid" | "rate_limited" | "testing"

function maskKey(key: string): string {
  if (!key) return ""
  if (key.length <= 8) return "••••••••"
  return `${key.slice(0, 4)}••••••••${key.slice(-4)}`
}

export function KeysManager() {
  const { toast } = useToast()

  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [savedKeys, setSavedKeys] = useState<Record<string, string>>({})
  const [statuses, setStatuses] = useState<Record<string, KeyStatus>>({})
  const [remember, setRemember] = useState(false)
  const [passphrase, setPassphrase] = useState("")
  const [vaultLoaded, setVaultLoaded] = useState(false)
  const [tavilyInput, setTavilyInput] = useState("")

  useEffect(() => {
    async function load() {
      ApiClient.wakeup()
      try {
        setCatalog(await ApiClient.catalog())
      } catch {
        setCatalog(null)
      }
      setRemember(globalVault.remember)
      setSavedKeys(await globalVault.allKeys())
      setVaultLoaded(true)
    }
    load()
  }, [])

  useEffect(() => {
    globalVault.setRemember(remember)
    if (remember && globalVault.unlocked) {
      Object.entries(savedKeys).forEach(([p, k]) => {
        void globalVault.setKey(p, k)
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remember])

  const providers = catalog?.providers.filter((p) => p.enabled) ?? []
  const tavilySaved = !!savedKeys["tavily"]

  const handleSaveTavily = async () => {
    const rawKey = (tavilyInput || savedKeys["tavily"] || "").trim()
    if (!rawKey) return
    // No server-side probe exists for search keys: store only.
    await globalVault.setKey("tavily", rawKey)
    setSavedKeys((prev) => ({ ...prev, tavily: rawKey }))
    setTavilyInput("")
    toast({ title: "Search key saved", description: "Tavily key stored with your other keys.", variant: "success" })
  }

  const handleSaveAndTest = async (providerId: string) => {
    const rawKey = inputs[providerId] || savedKeys[providerId]
    if (!rawKey) return
    // Soft prefix hint never blocks saving (FR-30): validation is advisory only.
    void isKeyFormatOk(providerId, rawKey)
    await globalVault.setKey(providerId, rawKey)
    setSavedKeys((prev) => ({ ...prev, [providerId]: rawKey }))
    setInputs((prev) => ({ ...prev, [providerId]: "" }))
    setStatuses((prev) => ({ ...prev, [providerId]: "testing" }))
    try {
      const res = await ApiClient.testKey(providerId, rawKey)
      setStatuses((prev) => ({ ...prev, [providerId]: res.status }))
      if (res.status === "valid") {
        toast({ title: "Key verified", description: `Connected to ${providerId}.`, variant: "success" })
      } else if (res.status === "rate_limited") {
        toast({ title: "Rate limited", description: "Key is valid but rate-limited.", variant: "warning" })
      } else {
        toast({ title: "Invalid key", description: `Could not authenticate with ${providerId}.`, variant: "danger" })
      }
    } catch {
      setStatuses((prev) => ({ ...prev, [providerId]: "invalid" }))
    }
  }

  const handleClearAll = async () => {
    await globalVault.clearAll()
    try {
      await ApiClient.clearAllKeys()
    } catch {
      // Backend may not be reachable; frontend vault is already cleared.
    }
    setRemember(false)
    setSavedKeys({})
    setInputs({})
    setStatuses({})
    setPassphrase("")
    toast({ title: "Keys cleared", description: "All API keys removed from memory, disk, and system keyring." })
  }

  const readyFamilies = new Set<string>()
  providers.forEach((p) => {
    if (savedKeys[p.id] && statuses[p.id] !== "invalid") {
      p.models.forEach((m) => readyFamilies.add(m.family))
    }
  })
  const gate = evaluateGate(
    [...readyFamilies],
    providers.filter((p) => savedKeys[p.id]).length,
  )

  if (!vaultLoaded) return null

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
        </CardHeader>
      </Card>
      <Card className={gate.level === "OK" ? "border-success/30" : "border-warning/30"}>
        <CardHeader className="pb-3">
          <CardTitle>Team Readiness</CardTitle>
          <CardDescription data-testid="readiness-chip">{gateChipText(gate)}</CardDescription>
          {gate.level !== "OK" && (
            <CardDescription className="text-warning">{gate.reasons[0]}</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {gate.families_ready.map((f) => (
              <Badge key={f} variant="secondary" className="font-mono">{f}</Badge>
            ))}
            {gate.families_ready.length === 0 && <span className="text-sm opacity-60">No keys configured yet.</span>}
          </div>
        </CardContent>
      </Card>

      <div className="rounded-xl border border-border bg-card p-4 space-y-3">
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="accent-brand"
          />
          <div className="flex flex-col">
            <span className="font-medium">Remember on this device</span>
            <span className="text-xs text-muted-foreground">
              Encrypted with your passphrase (PBKDF2 + AES-GCM). In-memory only when off.
            </span>
          </div>
        </label>
        {remember && (
          <div className="flex gap-2">
            <input
              type="password"
              placeholder="Passphrase (min 8 chars)"
              value={passphrase}
              onChange={(e) => {
                setPassphrase(e.target.value)
                globalVault.unlock(e.target.value)
              }}
              autoComplete="off"
              className="flex-1 rounded-md border border-border bg-muted/50 px-3 py-2 text-sm"
            />
          </div>
        )}
        <Button variant="destructive" size="sm" onClick={handleClearAll} disabled={Object.keys(savedKeys).length === 0}>
          <Trash2 className="size-4 mr-2" />
          Clear all keys
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {providers.map((provider) => {
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
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium">API Key</label>
                    <div className="flex items-center gap-2">
                      {provider.key_url && (
                        <>
                          <a href={provider.key_url} target="_blank" rel="noreferrer noopener" className="text-xs flex items-center gap-1 text-brand hover:underline">
                            Get free key <ExternalLink className="size-3" />
                          </a>
                          <button
                            type="button"
                            aria-label={`Copy key link for ${provider.id}`}
                            data-testid={`copy-link-${provider.id}`}
                            className="text-xs text-brand hover:underline flex items-center gap-1"
                            onClick={() => void copyLink(provider.key_url)}
                          >
                            <Copy className="size-3" /> Copy link
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <input
                    type="password"
                    placeholder={hasSavedKey ? maskKey(savedKeys[provider.id]) : "paste key…"}
                    value={inputs[provider.id] || ""}
                    onChange={(e) => setInputs((prev) => ({ ...prev, [provider.id]: e.target.value }))}
                    autoComplete="off"
                    spellCheck="false"
                    className="w-full rounded-md border border-border bg-muted/50 px-3 py-2 text-sm font-mono"
                  />
                  <p data-testid={`prefix-hint-${provider.id}`} className="text-[10px] text-muted-foreground pt-1">
                    {hint} This hint never blocks saving.
                  </p>
                  {st !== "unknown" && st !== "testing" && (
                    <p data-testid={`test-result-${provider.id}`} className="text-xs">
                      Test result: {st}
                    </p>
                  )}
                  <p className="text-[10px] text-muted-foreground pt-1 flex items-start gap-1">
                    <Shield className="size-3 shrink-0" />
                    Keys never leave this device except to authenticate with the provider.
                  </p>
                </div>
              </CardContent>
              <CardFooter className="pt-0">
                <Button
                  variant={hasSavedKey ? "secondary" : "default"}
                  size="sm"
                  className="w-full"
                  disabled={st === "testing" || (!inputs[provider.id] && !hasSavedKey)}
                  onClick={() => handleSaveAndTest(provider.id)}
                >
                  {st === "testing" ? "Testing…" : inputs[provider.id] ? "Save & Test" : "Test Saved Key"}
                </Button>
              </CardFooter>
            </Card>
          )
        })}
      </div>

      <Card className="flex flex-col" data-testid="provider-card-tavily">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Key className="size-4 text-brand" />
            tavily <Badge variant="secondary">search · optional</Badge>
          </CardTitle>
          <CardDescription className="text-xs mt-1">
            Why this provider: web search for researchers. Without it
            Assembly uses keyless sources (Wikipedia, arXiv, Semantic
            Scholar, DuckDuckGo).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium">Search Key (Tavily)</label>
            <input
              type="password"
              placeholder={tavilySaved ? maskKey(savedKeys["tavily"]) : "paste key…"}
              value={tavilyInput}
              onChange={(e) => setTavilyInput(e.target.value)}
              autoComplete="off"
              spellCheck="false"
              data-testid="tavily-input"
              className="w-full rounded-md border border-border bg-muted/50 px-3 py-2 text-sm font-mono"
            />
            <p className="text-[10px] text-muted-foreground pt-1 flex items-start gap-1">
              <Shield className="size-3 shrink-0" />
              Stored with your other keys; sent only with your runs.
            </p>
          </div>
        </CardContent>
        <CardFooter className="pt-0">
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
        </CardFooter>
      </Card>
    </div>
  )
}
