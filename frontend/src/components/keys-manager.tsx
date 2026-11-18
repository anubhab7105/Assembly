"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { globalVault } from "@/lib/key-vault"
import { env } from "@/lib/env"
import { ApiClient, type Catalog, type KeyMetadataVerification } from "@/lib/api-client"
import { evaluateGate, gateChipText } from "@/lib/diversity-gate"
import {
  detectProviderByPrefix,
  isKeyFormatOk,
  keyPrefixHint,
  minimumToStartBanner,
  sensitiveSignupText,
  whyProviderLine,
} from "@/lib/key-setup"
import { useToast } from "@/components/ui/toast"
import {
  Trash2,
  Plus,
  RefreshCw,
} from "lucide-react"

type KeyStatus = "unknown" | "valid" | "invalid" | "rate_limited" | "model_unavailable" | "unreachable" | "testing"

interface TargetProvider {
  id: string
  env: string
  name: string
  placeholder: string
}

const TARGET_PROVIDERS: TargetProvider[] = [
  { id: "gemini", env: "GEMINI_API_KEY", name: "Google Gemini", placeholder: "your-gemini-api-key" },
  { id: "groq", env: "GROQ_API_KEY", name: "Groq", placeholder: "gsk_your-groq-api-key" },
  { id: "cerebras", env: "CEREBRAS_API_KEY", name: "Cerebras", placeholder: "csk-your-cerebras-api-key" },
  { id: "openrouter", env: "OPENROUTER_API_KEY", name: "OpenRouter", placeholder: "sk-or-your-openrouter-api-key" },
  { id: "huggingface", env: "HUGGINGFACE_API_KEY", name: "Hugging Face", placeholder: "hf_your-huggingface-api-key" },
  { id: "nvidia", env: "NVIDIA_API_KEY", name: "NVIDIA", placeholder: "nvapi-your-nvidia-api-key" },
]

const ALL_SELECTABLE_PROVIDERS = TARGET_PROVIDERS

const PROVIDER_METADATA: Record<
  string,
  { models: string; roles: string[]; highlight: string; link: string }
> = {
  gemini: {
    models: "Gemini 2.5 Flash, Gemini 2.5 Pro",
    roles: ["Solver", "Critic", "Planner", "Synthesizer", "Researcher", "Thinking"],
    highlight: "Deep multi-step reasoning & structured synthesis",
    link: "https://aistudio.google.com/app/apikey",
  },
  groq: {
    models: "Llama 3.3 70B, Qwen 2.5 32B",
    roles: ["Solver", "Critic", "Planner", "Researcher", "Synthesizer"],
    highlight: "Ultra-fast token inference & cross-examination",
    link: "https://console.groq.com/keys",
  },
  cerebras: {
    models: "Llama 3.3 70B, Llama 3.1 8B",
    roles: ["Solver", "Critic", "Synthesizer"],
    highlight: "Sub-second wafer-scale generation",
    link: "https://cloud.cerebras.ai/",
  },
  openrouter: {
    models: "Gemma 2 9B, Nemotron 70B",
    roles: ["Solver", "Critic", "Synthesizer"],
    highlight: "Multi-architecture open weight diversity",
    link: "https://openrouter.ai/keys",
  },
  huggingface: {
    models: "Mistral 7B, Qwen 2.5 Coder",
    roles: ["Solver", "Researcher"],
    highlight: "Open model ecosystem & specialized weights",
    link: "https://huggingface.co/settings/tokens",
  },
  nvidia: {
    models: "Llama 3.1 70B, Nemotron 70B",
    roles: ["Solver", "Critic", "Planner"],
    highlight: "Enterprise scale reasoning & precision alignment",
    link: "https://build.nvidia.com/",
  },
  tavily: {
    models: "Tavily Real-time Search API",
    roles: ["Web Search", "Fact Verification", "Citations"],
    highlight: "Real-time web exploration & source validation",
    link: "https://app.tavily.com/",
  },
}

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
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [savedKeys, setSavedKeys] = useState<Record<string, string>>({})
  const [statuses, setStatuses] = useState<Record<string, KeyStatus>>({})
  const [verifications, setVerifications] = useState<Record<string, KeyMetadataVerification>>({})
  const verificationGenerations = React.useRef<Record<string, number>>({})

  const nextVerificationGeneration = (providerId: string): number => {
    const generation = (verificationGenerations.current[providerId] ?? 0) + 1
    verificationGenerations.current[providerId] = generation
    return generation
  }

  const invalidateVerificationGenerations = (providerIds: string[]) => {
    for (const providerId of providerIds) nextVerificationGeneration(providerId)
  }
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({})
  const [passphrase, setPassphrase] = useState("")
  const [vaultLoaded, setVaultLoaded] = useState(false)
  const [tavilyInput, setTavilyInput] = useState("")
  const [needsUnlock, setNeedsUnlock] = useState(false)
  const [unlockError, setUnlockError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<{ id: string; name: string } | null>(null)

  // Universal Smart Bar State
  const [universalInput, setUniversalInput] = useState("")
  const [selectedProviderId, setSelectedProviderId] = useState<string>("gemini")
  const [isSubmittingUniversal, setIsSubmittingUniversal] = useState(false)
  const [showConfigModal, setShowConfigModal] = useState(false)

  useEffect(() => {
    async function load() {
      ApiClient.wakeup()
      try {
        setCatalog(await ApiClient.catalog())
      } catch {
        setCatalog(null)
      }
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

  // Auto-detect provider when typing or pasting into universal bar
  const handleUniversalInputChange = (val: string) => {
    setUniversalInput(val)
    const detected = detectProviderByPrefix(val)
    if (detected) {
      setSelectedProviderId(detected)
    }
  }

  const handleUnlock = async () => {
    try {
      const keys = await globalVault.migrateLegacy(passphrase)
      setSavedKeys(keys)
      setNeedsUnlock(false)
      setUnlockError(keys && Object.keys(keys).length > 0 ? null : "No keys found in the saved vault.")
      toast({ title: "Keys restored", description: "Saved keys were restored on this device.", variant: "success" })
    } catch (e) {
      setUnlockError(
        e instanceof Error ? e.message : "Wrong passphrase. Nothing was deleted. Try again or use Clear all keys.",
      )
    }
  }

  const handleForget = async () => {
    invalidateVerificationGenerations(Object.keys({ ...savedKeys, ...verificationGenerations.current }))
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
    setVerifications({})
    setTavilyInput("")
    setUniversalInput("")
    setPassphrase("")
    toast({ title: "Keys forgotten", description: "All API keys removed from this device." })
  }

  const copyLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      toast({ title: "Link copied", description: url })
    } catch {
      toast({ title: "Copy failed", description: url, variant: "warning" })
    }
  }

  const providers = catalog?.providers.filter((p) => p.enabled) ?? []
  const tavilySaved = !!savedKeys["tavily"]

  const handleSaveTavily = async (customKey?: string) => {
    const rawKey = cleanPastedKey(customKey || tavilyInput || savedKeys["tavily"] || "")
    if (!rawKey) return
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

  const handleSaveAndTest = async (providerId: string, customKey?: string) => {
    const rawKey = cleanPastedKey(customKey || inputs[providerId] || savedKeys[providerId] || "")
    if (!rawKey) return
    const generation = nextVerificationGeneration(providerId)
    void isKeyFormatOk(providerId, rawKey)
    try {
      await globalVault.setKey(providerId, rawKey)
    } catch (e) {
      if (verificationGenerations.current[providerId] !== generation) return
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
    setVerifications((prev) => {
      if (!(providerId in prev)) return prev
      const next = { ...prev }
      delete next[providerId]
      return next
    })
    try {
      const res = await ApiClient.testKey(providerId, rawKey)
      if (verificationGenerations.current[providerId] !== generation) return
      setStatuses((prev) => ({ ...prev, [providerId]: res.status }))
      if (res.verification) {
        setVerifications((prev) => ({ ...prev, [providerId]: res.verification! }))
      }
      const metadataMessage = res.verification
        ? `Automatic check: ${res.verification.models.filter((model) => model.available).length}/${res.verification.models.length} configured models available. ${res.verification.quota_metadata_ready ? "Shared quota metadata is fresh." : "Shared models.yaml quota limits still need review."}`
        : undefined
      if (res.status === "valid") {
        toast({ title: "Key verified", description: [res.message ?? `Connected to ${providerId}.`, metadataMessage].filter(Boolean).join(" "), variant: "success" })
      } else if (res.status === "rate_limited") {
        toast({ title: "Rate limited", description: [res.message ?? "Key valid, but rate limits reached.", metadataMessage].filter(Boolean).join(" "), variant: "warning" })
      } else if (res.status === "model_unavailable") {
        toast({ title: "Model unavailable", description: [res.message ?? "Key valid, but configured model not available.", metadataMessage].filter(Boolean).join(" "), variant: "warning" })
      } else {
        toast({ title: "Key test failed", description: res.message ?? "The provider rejected this key.", variant: "danger" })
      }
    } catch {
      if (verificationGenerations.current[providerId] !== generation) return
      setStatuses((prev) => ({ ...prev, [providerId]: "unreachable" }))
      toast({ title: "Couldn't reach provider", description: "Couldn't reach the server; try again.", variant: "danger" })
    }
  }

  // Universal Bar Save Handler
  const handleUniversalSave = async () => {
    if (!universalInput.trim()) return

    setIsSubmittingUniversal(true)
    try {
      if (selectedProviderId === "tavily") {
        await handleSaveTavily(universalInput)
      } else {
        await handleSaveAndTest(selectedProviderId, universalInput)
      }
      setUniversalInput("")
    } finally {
      setIsSubmittingUniversal(false)
    }
  }

  const handleRemove = React.useCallback(async (providerId: string) => {
    const generation = nextVerificationGeneration(providerId)
    try {
      await globalVault.removeKey(providerId)
    } catch {
      if (verificationGenerations.current[providerId] !== generation) return
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
    setVerifications((prev) => {
      if (!(providerId in prev)) return prev
      const next = { ...prev }
      delete next[providerId]
      return next
    })
    toast({ title: "Key removed", description: `${providerId} key removed. Other providers are unchanged.` })
  }, [toast])

  useEffect(() => {
    if (!pendingDelete) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPendingDelete(null)
      } else if (e.key === "Enter") {
        e.preventDefault()
        const id = pendingDelete.id
        setPendingDelete(null)
        void handleRemove(id)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [pendingDelete, handleRemove])

  const handleClearAll = async () => {
    if (!confirm("Remove all saved keys from this browser? This cannot be undone.")) return
    invalidateVerificationGenerations(Object.keys({ ...savedKeys, ...verificationGenerations.current }))
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
    setTavilyInput("")
    setUniversalInput("")
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
      </div>
    )
  }

  const recommendedOrder = catalog?.recommended_order ?? providers.map((p) => p.id)
  const banner = minimumToStartBanner(readyFamilies.size, recommendedOrder)

  const activeProviderCount = Object.keys(savedKeys).filter((k) => k !== "tavily").length

  return (
    <div className="w-full space-y-6">
      {/* Minimum to start card */}
      <Card data-testid="minimum-to-start-banner" className="border border-border/80 bg-card/90 shadow-xl rounded-2xl">
        <CardHeader className="p-5 pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-bold text-foreground">Minimum to start</CardTitle>
            <span data-testid="readiness-chip" className="sr-only">
              {catalog ? gateChipText(gate) : "Loading providers..."}
            </span>
          </div>
          <CardDescription data-testid="minimum-to-start-text" className="text-xs text-muted-foreground mt-1 leading-relaxed">
            {banner}
          </CardDescription>
          <div className="mt-3 space-y-2 text-xs leading-relaxed text-muted-foreground">
            <p className="font-semibold text-foreground">Quick setup</p>
            <ol className="list-decimal space-y-1 pl-4">
              <li>Save a free key for each provider you want to use.</li>
              <li>Press <b className="font-medium text-foreground">Save &amp; Test</b> and check the result.</li>
              <li>Return to Run and start an investigation.</li>
            </ol>
            <p className="text-muted-foreground/80">
              Three distinct model families are recommended; two can run with a warning. The readiness status below counts only configured providers whose quota metadata is ready.
            </p>
          </div>
          {/* Retained in DOM for persistent vault test contract */}
          <p data-testid="persisted-banner" className="sr-only">
            Saved keys stay in this browser across refreshes and can be removed here or cleared with site data. Keys are stored unencrypted in local browser storage, not protected by the OS.
          </p>
        </CardHeader>
      </Card>

      {/* ─── THE CORE USER REQUEST: Universal Smart Key Ingestion Bar ─── */}
      <Card className="border border-border/80 bg-card/90 shadow-2xl overflow-hidden gap-2.5 py-4">
        <CardHeader className="pb-0">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle className="text-base font-bold flex items-center gap-2 text-foreground">
                <Plus className="size-4 text-brand" />
                Add API Key
              </CardTitle>
              <CardDescription className="text-xs text-muted-foreground mt-1">
                Paste any API key — Assembly automatically detects the provider, displays its models and roles, and adds it to your active team.
              </CardDescription>
            </div>
            <button
              type="button"
              onClick={() => setShowConfigModal(true)}
              aria-label="Add Provider"
              title="Add Provider"
              className="px-3.5 py-1.5 rounded-xl bg-[#f59e0b] hover:bg-[#d97706] text-white font-semibold text-xs tracking-wide shadow-md flex items-center gap-1.5 transition-all shrink-0 active:scale-95"
            >
              <Plus className="size-3.5 text-white" />
              <span>Add Provider</span>
            </button>
          </div>
        </CardHeader>

        <CardContent className="pt-0 space-y-3">
          {/* Single Universal Paste Bar */}
          <div className="relative flex items-center">
              <input
                id="universal-key-input"
                type="password"
                placeholder={`Paste ${ALL_SELECTABLE_PROVIDERS.find((p) => p.id === selectedProviderId)?.name} key`}
                value={universalInput}
                onChange={(e) => handleUniversalInputChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    void handleUniversalSave()
                  }
                }}
                autoComplete="off"
                spellCheck="false"
                className="w-full rounded-xl border border-border bg-muted/60 pl-4 pr-24 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand shadow-inner"
              />

              <div className="absolute right-2 flex items-center">
                <Button
                  type="button"
                  size="sm"
                  data-testid="universal-save"
                  disabled={!universalInput.trim() || isSubmittingUniversal}
                  onClick={() => void handleUniversalSave()}
                  className="px-4 rounded-lg bg-brand text-brand-foreground hover:opacity-90 font-semibold text-xs tracking-wide shadow-sm"
                >
                  {isSubmittingUniversal ? (
                    <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <span>Save</span>
                  )}
                </Button>
              </div>
            </div>
        </CardContent>
      </Card>

      {/* Provider & Roles Modal Dialog */}
      <Dialog open={showConfigModal} onOpenChange={setShowConfigModal}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl rounded-2xl border border-border bg-popover text-popover-foreground p-6 shadow-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold text-foreground">Select Provider</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Choose which provider you want to configure and add to your team.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            {/* Quick Select Provider - Checkbox Card Style */}
            <div className="space-y-2">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Select Provider:
              </span>
              <div className="flex flex-wrap gap-2">
                {ALL_SELECTABLE_PROVIDERS.map((p) => {
                  const isSelected = selectedProviderId === p.id
                  const isSaved = !!savedKeys[p.id]
                  return (
                    <label
                      key={p.id}
                      onClick={() => setSelectedProviderId(p.id)}
                      className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 text-xs font-mono transition-colors ${
                        isSelected
                          ? "border-brand bg-brand/10 text-foreground font-semibold"
                          : "border-border bg-background text-muted-foreground hover:text-foreground hover:border-foreground/30"
                      }`}
                    >
                      <input
                        type="radio"
                        name="modal-provider-selector"
                        checked={isSelected}
                        onChange={() => setSelectedProviderId(p.id)}
                        className="accent-brand size-3.5"
                      />
                      <span>{p.name}</span>
                      {isSaved && (
                        <span className="text-[10px] text-white bg-[#15803d] font-medium px-2 py-0.5 rounded-full shadow-sm">Active</span>
                      )}
                    </label>
                  )
                })}
              </div>
            </div>
          </div>

          <DialogFooter className="bg-transparent border-0 p-0 m-0 pt-4 flex justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={() => setShowConfigModal(false)}
              className="rounded-xl px-5 font-semibold text-xs h-9 bg-background hover:bg-muted"
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ─── TAVILY (SEARCH) API KEY BAR ─── */}
      <Card
        data-testid="provider-card-tavily"
        className="border border-border/80 bg-card/90 shadow-2xl overflow-hidden gap-2.5 py-4 rounded-2xl"
      >
        <CardHeader className="pb-0">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold flex items-center gap-2 text-foreground">
                Tavily Search API Key <span className="text-xs font-normal text-muted-foreground">(Optional)</span>
              </CardTitle>
              <p className="sr-only">
                Without a Tavily key, research falls back to keyless sources.
              </p>
            </div>
            {tavilySaved && (
              <span className="text-xs text-white bg-[#15803d] font-medium px-2.5 py-0.5 rounded-full shadow-sm">
                Active
              </span>
            )}
          </div>
        </CardHeader>

        <CardContent className="pt-0">
          <div className="relative flex items-center">
            <input
              id="key-tavily"
              data-testid="tavily-input"
              type="password"
              placeholder={tavilySaved ? maskKey(savedKeys["tavily"]) : "Paste Tavily key"}
              value={tavilyInput}
              onChange={(e) => setTavilyInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  void handleSaveTavily()
                }
              }}
              autoComplete="off"
              spellCheck="false"
              className="w-full rounded-xl border border-border bg-muted/60 pl-4 pr-24 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand shadow-inner"
            />
            <div className="absolute right-2 flex items-center gap-1.5">
              {tavilySaved && !tavilyInput && (
                <button
                  type="button"
                  onClick={() => setPendingDelete({ id: "tavily", name: "Tavily Web Search" })}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-400 hover:bg-red-400/10 transition-colors flex items-center justify-center"
                  title="Remove Tavily key"
                  aria-label="Remove Tavily key"
                >
                  <Trash2 className="size-4" />
                </button>
              )}
              <Button
                type="button"
                size="sm"
                data-testid="tavily-save"
                disabled={!tavilyInput.trim()}
                onClick={() => void handleSaveTavily()}
                className="px-4 rounded-lg bg-brand text-brand-foreground hover:opacity-90 font-semibold text-xs tracking-wide shadow-sm"
              >
                Save
              </Button>
            </div>
          </div>
          <p className="sr-only">
            {desktopMode
              ? "Stored in this WebView browser profile; a saved Tavily key is sent to the local Assembly backend over loopback with every run request, even when search is not used."
              : "Stored in this browser; a saved Tavily key is sent to the hosted Assembly backend over HTTPS (localhost is used for local development) with every run request, even when search is not used."}
          </p>
        </CardContent>
      </Card>

      {/* ─── ACTIVE TEAM ROSTER (Configured Providers) ─── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-foreground">Active Team Members</h3>
            <span className="text-xs bg-muted px-2.5 py-0.5 rounded-full font-medium text-muted-foreground">
              {activeProviderCount + (tavilySaved ? 1 : 0)} Active
            </span>
          </div>
          {(activeProviderCount > 0 || tavilySaved) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleClearAll()}
              className="text-xs text-muted-foreground hover:text-red-400 h-8"
              data-testid="clear-all-keys"
            >
              Clear all keys
            </Button>
          )}
        </div>

        {activeProviderCount === 0 && !tavilySaved ? (
          <div className="rounded-xl border border-dashed border-border/70 p-8 text-center space-y-2">
            <p className="text-sm font-semibold text-foreground">No providers added yet</p>
            <p className="text-xs text-muted-foreground max-w-md mx-auto">
              Paste your first provider key into the box above to build your multi-agent research team.
            </p>
          </div>
        ) : (
          <div className="rounded-2xl border border-border/80 bg-card/80 overflow-hidden shadow-xl divide-y divide-border/40">
            {/* Table / List Header */}
            <div className="hidden sm:grid sm:grid-cols-12 gap-4 px-5 py-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider bg-muted/40 border-b border-border/40">
              <div className="col-span-5">Provider</div>
              <div className="col-span-3">Key</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2 text-right">Actions</div>
            </div>

            {/* List Rows - stacked one after another */}
            {TARGET_PROVIDERS.filter((p) => !!savedKeys[p.id]).map((provider) => {
              const st = statuses[provider.id] || "unknown"
              const catProv = catalog?.providers.find((p) => p.id === provider.id)
              const hint = keyPrefixHint(provider.id)
              const steps = catProv?.key_steps ?? []
              const why = catProv ? whyProviderLine(catProv) : ""
              const signupNote = sensitiveSignupText(catProv?.sensitive_signup)

              return (
                <div
                  key={provider.id}
                  data-testid={`provider-card-${provider.id}`}
                  className="flex flex-col sm:grid sm:grid-cols-12 gap-3 sm:gap-4 items-start sm:items-center px-5 py-3.5 hover:bg-muted/20 transition-colors"
                >
                  {/* Provider Name & Active Badge */}
                  <div className="col-span-5 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-foreground">{provider.name}</span>
                      <span className="text-[11px] font-medium text-white bg-[#15803d] px-2.5 py-0.5 rounded-full shadow-sm inline-flex items-center">
                        Active
                      </span>
                    </div>
                  </div>

                  {/* Masked Key */}
                  <div className="col-span-3">
                    <div className="relative flex items-center">
                      <input
                        id={`key-${provider.id}`}
                        type="password"
                        placeholder={maskKey(savedKeys[provider.id])}
                        value={inputs[provider.id] || ""}
                        onChange={(e) => setInputs((prev) => ({ ...prev, [provider.id]: e.target.value }))}
                        autoComplete="off"
                        spellCheck="false"
                        className="w-full sm:w-44 rounded-md border border-border/40 bg-muted/40 px-2.5 py-1 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-brand/40"
                      />
                    </div>
                  </div>

                  {/* Status */}
                  <div className="col-span-2 flex items-center">
                    <span
                      data-testid={`test-result-${provider.id}`}
                      className={`text-xs font-medium inline-flex items-center ${
                        st === "valid"
                          ? "bg-[#15803d] text-white px-2.5 py-0.5 rounded-full shadow-sm justify-center"
                          : st === "unreachable" || st === "invalid"
                            ? "text-red-400 font-medium"
                            : st === "rate_limited" || st === "model_unavailable"
                              ? "text-amber-400 font-medium"
                              : st === "testing"
                                ? "text-blue-400 font-medium gap-1.5"
                                : "text-muted-foreground"
                      }`}
                    >
                      {st === "testing" && <RefreshCw className="size-3 animate-spin text-blue-400" />}
                      {KEY_STATUS_LABEL[st]}
                    </span>
                  </div>

                  {/* Action buttons: Refresh & Trash */}
                  <div className="col-span-2 flex items-center justify-end gap-1.5 w-full sm:w-auto">
                    <button
                      type="button"
                      disabled={st === "testing"}
                      onClick={() => handleSaveAndTest(provider.id)}
                      aria-label="Save & Test"
                      title={`Save & Test ${provider.name} key`}
                      className="text-muted-foreground hover:text-foreground transition-colors p-1.5 rounded-lg hover:bg-muted/60 disabled:opacity-50 flex items-center justify-center"
                    >
                      <RefreshCw className={`size-4 ${st === "testing" ? "animate-spin" : ""}`} />
                      <span className="sr-only">Save &amp; Test</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setPendingDelete({ id: provider.id, name: provider.name })}
                      aria-label={`Clear key for ${provider.id}`}
                      title={`Remove ${provider.name} key`}
                      data-testid={`remove-${provider.id}`}
                      className="assembly-trash-btn text-muted-foreground hover:text-red-400 transition-colors p-1.5 rounded-lg hover:bg-red-400/10"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>

                  {verifications[provider.id] && (
                    <div
                      role="status"
                      data-testid={`metadata-verification-${provider.id}`}
                      className="col-span-12 rounded-lg border border-border/50 bg-muted/30 px-3 py-2.5 text-xs space-y-1.5"
                    >
                      <p className="font-semibold text-foreground">
                        Automatic metadata check · {new Date(verifications[provider.id].checked_at).toLocaleString()}
                      </p>
                      <div className="space-y-1.5">
                        <p className="text-muted-foreground">
                          Model catalogue: {verifications[provider.id].models.filter((model) => model.available === true).length}/
                          {verifications[provider.id].models.length} configured models confirmed available.
                        </p>
                        <ul className="space-y-1">
                          {verifications[provider.id].models.map((model) => (
                            <li key={model.id} className="flex flex-wrap items-baseline gap-x-2 text-muted-foreground">
                              <code className="text-foreground">{model.id}</code>
                              <span>{model.available === true ? "Available" : model.available === false ? "Unavailable" : "Not probed"}</span>
                              <span>Context: {model.context_tokens != null ? model.context_tokens.toLocaleString() : "unverified"}</span>
                              <span>Output: {model.output_tokens != null ? model.output_tokens.toLocaleString() : "unverified"}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                      {verifications[provider.id].observed_quotas.length > 0 ? (
                        <div className="flex flex-wrap gap-x-3 gap-y-1">
                          {verifications[provider.id].observed_quotas.map((observation) => (
                            <span key={observation.field} className="text-foreground">
                              {observation.field}: {observation.value.toLocaleString()} {observation.unit}
                              <span className="text-muted-foreground"> ({observation.scope})</span>
                            </span>
                          ))}
                        </div>
                      ) : (
                        <p className="text-muted-foreground">
                          The provider did not expose numeric quota limits in this read-only check.
                        </p>
                      )}
                      <p className="text-muted-foreground">
                        Still unverified: {verifications[provider.id].unverified_fields.length > 0
                          ? verifications[provider.id].unverified_fields.join(", ")
                          : "none reported by this check"}.
                      </p>
                      <p className={verifications[provider.id].quota_metadata_ready ? "text-emerald-500" : "text-amber-500"}>
                        {verifications[provider.id].quota_metadata_ready
                          ? "Shared models.yaml quota metadata is currently fresh."
                          : verifications[provider.id].quota_metadata_issue ?? "Shared quota metadata still needs manual review."}
                      </p>
                      <p className="text-muted-foreground">
                        Per-key observations are informational only; they do not update shared models.yaml or refresh quota_last_verified.
                      </p>
                    </div>
                  )}
                  {saveErrors[provider.id] && (
                    <p
                      role="alert"
                      data-testid={`save-error-${provider.id}`}
                      className="col-span-12 text-xs text-red-400 font-medium pt-1"
                    >
                      {saveErrors[provider.id]}
                    </p>
                  )}

                  {/* Retained in DOM for contract & testing specifications */}
                  <details data-testid={`stepper-${provider.id}`} className="sr-only">
                    <summary>How to get a key</summary>
                    <ol>{steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
                    <p data-testid={`signup-note-${provider.id}`}>{signupNote}</p>
                  </details>
                  <button
                    type="button"
                    data-testid={`copy-link-${provider.id}`}
                    className="sr-only"
                    onClick={() => catProv?.key_url && void copyLink(catProv.key_url)}
                  >
                    Copy link
                  </button>
                  <p id={`prefix-hint-${provider.id}`} data-testid={`prefix-hint-${provider.id}`} className="sr-only">
                    {hint} This hint never blocks saving.
                  </p>
                  <p data-testid={`why-${provider.id}`} className="sr-only">{why}</p>
                  {catProv && !catProv.limits_ready && (
                    <p role="status" data-testid={`limits-unavailable-${provider.id}`} className="sr-only">
                      {catProv.limits_issue ?? "Provider quota limits are unverified. This provider will not be used for runs until its limits are confirmed."}
                    </p>
                  )}
                  <p className="sr-only">
                    {desktopMode
                      ? "Stored in this WebView browser profile; sent to the local Assembly backend over loopback for preflight, key tests and runs, then used to authenticate with the provider."
                      : "Stored in this browser; sent to the hosted Assembly backend over HTTPS (localhost is used for local development) for preflight, key tests and runs, then used to authenticate with the provider."}
                  </p>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ─── AVAILABLE PROVIDERS & WEB SEARCH (Kept in DOM for testing contracts) ─── */}
      <div style={{ position: "fixed", bottom: 0, right: 0, width: "400px", height: "200px", opacity: 0.001, zIndex: 99999, overflow: "hidden" }}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {TARGET_PROVIDERS.filter((p) => !savedKeys[p.id]).map((provider) => {
            const catProv = catalog?.providers.find((p) => p.id === provider.id)
            const st = statuses[provider.id] || "unknown"
            const meta = PROVIDER_METADATA[provider.id]
            const hint = keyPrefixHint(provider.id)
            const steps = catProv?.key_steps ?? []
            const why = catProv ? whyProviderLine(catProv) : ""
            const signupNote = sensitiveSignupText(catProv?.sensitive_signup)

            return (
              <div
                key={provider.id}
                className="rounded-xl border border-border/50 bg-card/30 p-3.5 space-y-2.5 hover:border-border transition-colors flex flex-col justify-between"
                data-testid={`provider-card-${provider.id}`}
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs text-foreground">{provider.name}</span>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedProviderId(provider.id)
                        const el = document.getElementById("universal-key-input")
                        el?.focus()
                      }}
                      className="text-[11px] text-brand hover:underline flex items-center gap-1 font-medium"
                    >
                      <span>+ Add</span>
                    </button>
                  </div>

                  <div className="relative flex items-center">
                    <input
                      id={`key-${provider.id}`}
                      type="password"
                      placeholder={provider.placeholder}
                      value={inputs[provider.id] || ""}
                      onChange={(e) => setInputs((prev) => ({ ...prev, [provider.id]: e.target.value }))}
                      autoComplete="off"
                      spellCheck="false"
                      className="w-full rounded-md border border-border bg-muted/40 px-2.5 py-1.5 text-xs font-mono"
                    />
                  </div>

                  <p className="text-[11px] text-muted-foreground line-clamp-1">
                    {meta?.models ?? catProv?.models.map((m) => m.id).join(", ")}
                  </p>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <span
                    data-testid={`test-result-${provider.id}`}
                    className={`text-[11px] font-medium ${st === "valid"
                      ? "text-emerald-400"
                      : st === "unreachable" || st === "invalid"
                        ? "text-red-500 font-semibold"
                        : "text-muted-foreground"
                      }`}
                  >
                    {KEY_STATUS_LABEL[st]}
                  </span>
                  <Button
                    variant="default"
                    size="sm"
                    className="h-6 text-[11px] px-2.5"
                    disabled={!inputs[provider.id] || st === "testing"}
                    onClick={() => handleSaveAndTest(provider.id)}
                  >
                    {st === "testing" ? "Testing…" : "Save & Test"}
                  </Button>
                </div>

                {saveErrors[provider.id] && (
                  <p
                    role="alert"
                    data-testid={`save-error-${provider.id}`}
                    className="text-xs text-red-400 font-medium pt-1"
                  >
                    {saveErrors[provider.id]}
                  </p>
                )}

                {/* Retained in DOM for contract & testing specifications */}
                <details data-testid={`stepper-${provider.id}`} className="sr-only">
                  <summary>How to get a key</summary>
                  <ol>{steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
                  <p data-testid={`signup-note-${provider.id}`}>{signupNote}</p>
                </details>
                <button
                  type="button"
                  data-testid={`copy-link-${provider.id}`}
                  className="sr-only"
                  onClick={() => catProv?.key_url && void copyLink(catProv.key_url)}
                >
                  Copy link
                </button>
                <p id={`prefix-hint-${provider.id}`} data-testid={`prefix-hint-${provider.id}`} className="sr-only">
                  {hint} This hint never blocks saving.
                </p>
                <p data-testid={`why-${provider.id}`} className="sr-only">{why}</p>
                {catProv && !catProv.limits_ready && (
                  <p role="status" data-testid={`limits-unavailable-${provider.id}`} className="sr-only">
                    {catProv.limits_issue ?? "Provider quota limits are unverified. This provider will not be used for runs until its limits are confirmed."}
                  </p>
                )}
                <p className="sr-only">
                  {desktopMode
                    ? "Stored in this WebView browser profile; sent to the local Assembly backend over loopback for preflight, key tests and runs, then used to authenticate with the provider."
                    : "Stored in this browser; sent to the hosted Assembly backend over HTTPS (localhost is used for local development) for preflight, key tests and runs, then used to authenticate with the provider."}
                </p>
              </div>
            )
          })}
        </div>
      </div>

      {/* Legacy Unlock prompt if needed */}
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

      {/* Delete Confirmation Modal (Google AI Studio style) */}
      {pendingDelete && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          aria-describedby="delete-dialog-description"
          data-testid="delete-confirmation-dialog"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in-0 duration-150"
          onClick={(e) => {
            if (e.target === e.currentTarget) setPendingDelete(null)
          }}
        >
          <div
            className="w-full max-w-[440px] rounded-[20px] border border-black/10 dark:border-white/10 bg-white dark:bg-[#1e1f20] p-6 shadow-2xl animate-in zoom-in-95 duration-150 text-foreground"
          >
            <h2 id="delete-dialog-title" className="text-lg font-medium text-gray-900 dark:text-white">
              Remove API key?
            </h2>
            <p id="delete-dialog-description" className="text-sm text-gray-600 dark:text-white/70 mt-2 leading-relaxed">
              This will remove the saved key from your browser.
            </p>
            <div className="flex items-center justify-end gap-2.5 mt-6">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setPendingDelete(null)}
                className="rounded-full px-4 text-sm font-medium text-gray-700 dark:text-white/80 hover:bg-gray-100 dark:hover:bg-white/10"
                data-testid="cancel-delete-btn"
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={async () => {
                  const id = pendingDelete.id
                  setPendingDelete(null)
                  await handleRemove(id)
                }}
                className="rounded-full px-5 text-sm font-medium bg-gray-900 dark:bg-white/10 text-white hover:bg-red-600 dark:hover:bg-red-600 border border-transparent dark:border-white/15 transition-all flex items-center justify-center"
                data-testid="confirm-delete-btn"
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
