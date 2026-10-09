"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { globalVault } from "@/lib/key-vault"
import { ApiClient } from "@/lib/api-client"
import { useToast } from "@/components/ui/toast"
import { Shield, Key, AlertTriangle, CheckCircle2, Zap, Trash2, ExternalLink } from "lucide-react"

// Define the providers we support (must include Gemini, Groq, Cerebras, OpenRouter, Mistral)
const PROVIDERS = [
  {
    id: "gemini",
    name: "Google Gemini",
    families: ["gemini"],
    bestFor: "Complex reasoning, massive context windows (up to 2M tokens), and fast generation.",
    link: "https://aistudio.google.com/app/apikey",
  },
  {
    id: "groq",
    name: "Groq",
    families: ["llama", "mistral"], // Groq hosts open source models
    bestFor: "Lightning-fast inference (LPU), great for real-time debate and rapid drafting.",
    link: "https://console.groq.com/keys",
  },
  {
    id: "cerebras",
    name: "Cerebras",
    families: ["llama"],
    bestFor: "Extreme speed on LLaMA models, ideal for rapid-fire cross-examination.",
    link: "https://cloud.cerebras.ai/",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    families: ["llama", "qwen", "mistral", "deepseek"],
    bestFor: "Access to dozens of free-tier models; provides excellent model diversity.",
    link: "https://openrouter.ai/keys",
  },
  {
    id: "mistral",
    name: "Mistral",
    families: ["mistral"],
    bestFor: "Strong reasoning capabilities, good for critical analysis and verification.",
    link: "https://console.mistral.ai/api-keys/",
  },
]

type KeyStatus = "unknown" | "valid" | "invalid" | "rate_limited" | "testing"

function maskKey(key: string): string {
  if (!key) return ""
  if (key.length <= 8) return "••••••••"
  return `${key.slice(0, 4)}••••••••${key.slice(-4)}`
}

export function KeysManager() {
  const { toast } = useToast()
  
  // State for keys: what's typed vs what's saved
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [savedKeys, setSavedKeys] = useState<Record<string, string>>({})
  const [statuses, setStatuses] = useState<Record<string, KeyStatus>>({})
  
  // Vault settings
  const [remember, setRemember] = useState(false)
  const [vaultLoaded, setVaultLoaded] = useState(false)

  // Load from vault on mount
  useEffect(() => {
    async function load() {
      // Wake up the backend in case it is sleeping on a free host
      ApiClient.wakeup()
      
      // By default vault is in-memory, but if we wanted to persist preference, we'd load it here.
      // For simplicity, we just check what's in the vault.
      const loaded: Record<string, string> = {}
      for (const p of PROVIDERS) {
        const k = await globalVault.getKey(p.id)
        if (k) loaded[p.id] = k
      }
      setSavedKeys(loaded)
      setVaultLoaded(true)
    }
    load()
  }, [])

  // Update vault settings when remember changes
  useEffect(() => {
    globalVault.setRemember(remember)
    // If turning on remember, persist existing keys
    if (remember) {
      Object.entries(savedKeys).forEach(([p, k]) => {
        globalVault.setKey(p, k)
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remember])

  const handleSaveAndTest = async (providerId: string) => {
    const rawKey = inputs[providerId] || savedKeys[providerId]
    if (!rawKey) return

    // Save to vault (avoids logging rawKey)
    await globalVault.setKey(providerId, rawKey)
    setSavedKeys(prev => ({ ...prev, [providerId]: rawKey }))
    setInputs(prev => ({ ...prev, [providerId]: "" })) // Clear input field

    // Test the key
    setStatuses(prev => ({ ...prev, [providerId]: "testing" }))
    try {
      const res = await ApiClient.testKey(providerId, rawKey)
      setStatuses(prev => ({ ...prev, [providerId]: res.status }))
      
      if (res.status === "valid") {
        toast({ title: "Key verified", description: `Successfully connected to ${providerId}.`, variant: "success" })
      } else if (res.status === "rate_limited") {
        toast({ title: "Rate limited", description: `Key is valid but currently rate-limited.`, variant: "warning" })
      } else {
        toast({ title: "Invalid key", description: `Could not authenticate with ${providerId}.`, variant: "danger" })
      }
    } catch (err) {
      // Intentionally not logging err details to avoid leaking keys in stack traces
      setStatuses(prev => ({ ...prev, [providerId]: "invalid" }))
      toast({ title: "Connection error", description: "Failed to verify key.", variant: "danger" })
    }
  }

  const handleClearAll = async () => {
    globalVault.setRemember(false)
    setRemember(false)
    setSavedKeys({})
    setInputs({})
    setStatuses({})
    toast({ title: "Keys cleared", description: "All API keys have been removed from memory and disk." })
  }

  // Calculate Team Readiness (distinct model families with valid/untested keys)
  const readyFamilies = new Set<string>()
  PROVIDERS.forEach(p => {
    const hasKey = !!savedKeys[p.id]
    const status = statuses[p.id]
    // Consider it ready if it has a key and hasn't explicitly failed
    if (hasKey && status !== "invalid") {
      p.families.forEach(f => readyFamilies.add(f))
    }
  })

  const familyCount = readyFamilies.size
  const isReady = familyCount >= 3

  if (!vaultLoaded) return null

  return (
    <div className="w-full space-y-8">
      {/* Team Readiness Panel */}
      <Card className={`transition-colors ${isReady ? "border-success/30 bg-success-subtle" : "border-warning/30 bg-warning-subtle"}`}>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <CardTitle className={`flex items-center gap-2 ${isReady ? "text-success" : "text-warning"}`}>
                {isReady ? <CheckCircle2 className="size-5" /> : <AlertTriangle className="size-5" />}
                Team Readiness
              </CardTitle>
              <CardDescription className={isReady ? "text-success/80" : "text-warning/80"}>
                {familyCount} of 3 recommended model families ready.
              </CardDescription>
            </div>
            {!isReady && (
              <Badge variant="outline" className="bg-background/50 text-warning border-warning/30">
                Action Required
              </Badge>
            )}
            {isReady && (
              <Badge variant="outline" className="bg-background/50 text-success border-success/30">
                Ready for debate
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {Array.from(readyFamilies).map(f => (
              <Badge key={f} variant="secondary" className="bg-background/50 font-mono">
                {f}
              </Badge>
            ))}
            {familyCount === 0 && <span className="text-sm opacity-60">No keys configured yet.</span>}
          </div>
        </CardContent>
      </Card>

      {/* Global Actions */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card p-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="rounded border-border text-brand focus:ring-brand accent-brand"
          />
          <div className="flex flex-col">
            <span className="font-medium">Remember on this device</span>
            <span className="text-xs text-muted-foreground">
              Encrypts keys using WebCrypto and stores in browser DB. Turn off for pure in-memory (safest).
            </span>
          </div>
        </label>
        
        <Button variant="destructive" size="sm" onClick={handleClearAll} disabled={Object.keys(savedKeys).length === 0}>
          <Trash2 className="size-4 mr-2" />
          Clear all keys
        </Button>
      </div>

      {/* Provider Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PROVIDERS.map(provider => {
          const hasSavedKey = !!savedKeys[provider.id]
          const status = statuses[provider.id] || (hasSavedKey ? "unknown" : "unknown")
          const isTesting = status === "testing"
          
          return (
            <Card key={provider.id} className="flex flex-col">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Key className="size-4 text-brand" />
                    {provider.name}
                  </CardTitle>
                  {status === "valid" && <Badge className="bg-success-subtle text-success border-success/20">Valid</Badge>}
                  {status === "invalid" && <Badge className="bg-danger-subtle text-danger border-danger/20">Invalid</Badge>}
                  {status === "rate_limited" && <Badge className="bg-warning-subtle text-warning border-warning/20">Rate Limited</Badge>}
                </div>
                <CardDescription className="text-xs mt-1">
                  {provider.bestFor}
                </CardDescription>
              </CardHeader>
              
              <CardContent className="flex-1 space-y-4">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-foreground">API Key</label>
                    <a 
                      href={provider.link} 
                      target="_blank" 
                      rel="noreferrer noopener"
                      className="text-xs flex items-center gap-1 text-brand hover:underline"
                    >
                      Get free key <ExternalLink className="size-3" />
                    </a>
                  </div>
                  
                  <div className="relative">
                    <input
                      type="password"
                      placeholder={hasSavedKey ? maskKey(savedKeys[provider.id]) : "sk-..."}
                      value={inputs[provider.id] || ""}
                      onChange={(e) => setInputs(prev => ({ ...prev, [provider.id]: e.target.value }))}
                      autoComplete="off"
                      spellCheck="false"
                      className="w-full rounded-md border border-border bg-muted/50 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring font-mono"
                    />
                  </div>
                  
                  <p className="text-[10px] text-muted-foreground pt-1 flex items-start gap-1">
                    <Shield className="size-3 shrink-0" />
                    Free tiers may use inputs to improve models. Keys never leave this device except to authenticate.
                  </p>
                </div>
              </CardContent>
              
              <CardFooter className="pt-0">
                <Button 
                  variant={hasSavedKey ? "secondary" : "default"} 
                  size="sm" 
                  className="w-full"
                  disabled={isTesting || (!inputs[provider.id] && !hasSavedKey)}
                  onClick={() => handleSaveAndTest(provider.id)}
                >
                  {isTesting ? (
                    <><span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" /> Testing...</>
                  ) : inputs[provider.id] ? (
                    "Save & Test"
                  ) : (
                    "Test Saved Key"
                  )}
                </Button>
              </CardFooter>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
