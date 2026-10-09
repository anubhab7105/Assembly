"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { globalVault } from "@/lib/key-vault"
import { ApiClient, type Catalog } from "@/lib/api-client"
import { useToast } from "@/components/ui/toast"
import { Shield, Key, CheckCircle2, Trash2, ExternalLink } from "lucide-react"

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

  const handleSaveAndTest = async (providerId: string) => {
    const rawKey = inputs[providerId] || savedKeys[providerId]
    if (!rawKey) return
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

  if (!vaultLoaded) return null

  return (
    <div className="w-full space-y-8">
      <Card className={readyFamilies.size >= 3 ? "border-success/30" : "border-warning/30"}>
        <CardHeader className="pb-3">
          <CardTitle>Team Readiness</CardTitle>
          <CardDescription>{readyFamilies.size} of 3 recommended model families ready.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {Array.from(readyFamilies).map((f) => (
              <Badge key={f} variant="secondary" className="font-mono">{f}</Badge>
            ))}
            {readyFamilies.size === 0 && <span className="text-sm opacity-60">No keys configured yet.</span>}
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
          return (
            <Card key={provider.id} className="flex flex-col">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Key className="size-4 text-brand" />
                  {provider.id}
                </CardTitle>
                <CardDescription className="text-xs mt-1 font-mono">
                  {provider.models.map((m) => m.family).filter((v, i, a) => a.indexOf(v) === i).join(", ")}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1 space-y-4">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium">API Key</label>
                    {provider.key_url && (
                      <a href={provider.key_url} target="_blank" rel="noreferrer noopener" className="text-xs flex items-center gap-1 text-brand hover:underline">
                        Get free key <ExternalLink className="size-3" />
                      </a>
                    )}
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
    </div>
  )
}
