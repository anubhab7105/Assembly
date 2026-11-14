"use client"

import React, { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { ApiClient, type Catalog, type CatalogProvider } from "@/lib/api-client"
import { globalVault } from "@/lib/key-vault"
import { useToast } from "@/components/ui/toast"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ArrowRight, CheckCircle2, ExternalLink, KeyRound, ShieldCheck, SlidersHorizontal } from "lucide-react"

const PROVIDER_LABEL: Record<string, string> = {
  gemini: "Google Gemini",
  google: "Google",
  groq: "Groq",
  openrouter: "OpenRouter",
  mistral: "Mistral",
  cerebras: "Cerebras",
  nvidia: "NVIDIA",
  together: "Together AI",
  hyperbolic: "Hyperbolic",
  tavily: "Tavily Search",
}

function providerLabel(id: string) {
  return PROVIDER_LABEL[id] ?? id.charAt(0).toUpperCase() + id.slice(1)
}

function providerRoles(provider: CatalogProvider): string[] {
  const roles = new Set<string>()
  provider.models.forEach((model) => model.roles.forEach((role) => roles.add(role)))
  return [...roles].map((role) => role.charAt(0).toUpperCase() + role.slice(1))
}

function familyList(provider: CatalogProvider): string[] {
  return [...new Set(provider.models.map((model) => model.family))]
}

export default function ModelsPage() {
  const { toast } = useToast()
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [savedKeys, setSavedKeys] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [provider, setProvider] = useState<CatalogProvider | null>(null)
  const [keyInput, setKeyInput] = useState("")
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [messageTone, setMessageTone] = useState<"success" | "warning" | "danger">("success")

  const load = useCallback(async () => {
    setLoading(true)
    const [nextCatalog, keys] = await Promise.all([
      ApiClient.catalog().catch(() => null),
      globalVault.allKeys().catch(() => ({}) as Record<string, string>),
    ])
    setCatalog(nextCatalog)
    setSavedKeys(keys)
    setLoading(false)
  }, [])

  useEffect(() => {
    let active = true
    // Defer the first state write so the effect only starts the external fetch.
    queueMicrotask(() => {
      if (active) void load()
    })
    return () => {
      active = false
    }
  }, [load])

  const providers = catalog?.providers.filter((item) => item.enabled) ?? []
  const connected = providers.filter((item) => !!savedKeys[item.id]).length
  const families = catalog?.families.length ?? 0
  const minimum = catalog?.minimum_families ?? 2

  const openKeyDialog = (nextProvider: CatalogProvider) => {
    setProvider(nextProvider)
    setKeyInput("")
    setMessage(null)
    setMessageTone("success")
  }

  const saveKey = async () => {
    if (!provider || !keyInput.trim() || testing) return
    const key = keyInput.replace(/[\u200B-\u200D\uFEFF]/g, "").trim()
    setTesting(true)
    setMessage(null)
    try {
      await globalVault.setKey(provider.id, key)
      setSavedKeys((current) => ({ ...current, [provider.id]: key }))
    } catch (error) {
      setTesting(false)
      setMessageTone("danger")
      setMessage(error instanceof Error ? error.message : "Could not save this key on the device.")
      return
    }

    try {
      const result = await ApiClient.testKey(provider.id, key)
      setTesting(false)
      if (result.status === "valid") {
        setMessageTone("success")
        setMessage(result.message ?? `Connected to ${providerLabel(provider.id)}. The key is stored on this device only.`)
        toast({ title: "Key verified", description: result.message ?? `Connected to ${provider.id}.`, variant: "success" })
      } else if (result.status === "rate_limited") {
        setMessageTone("warning")
        setMessage(result.message ?? "The key is valid, but the provider is rate-limiting right now.")
      } else if (result.status === "model_unavailable") {
        setMessageTone("warning")
        setMessage(result.message ?? "The key is valid, but the configured model is unavailable to it.")
      } else if (result.status === "unreachable") {
        setMessageTone("warning")
        setMessage(result.message ?? "The key was saved, but the server could not be reached to test it.")
      } else {
        setMessageTone("danger")
        setMessage(result.message ?? "That key did not authenticate. Copy it again with no extra spaces.")
      }
    } catch {
      setTesting(false)
      setMessageTone("warning")
      setMessage("The key was saved, but the test request failed. Try Save & Test again from Settings.")
    }
  }

  return (
    <div className="cin-page cin-models-page">
      <main id="main-content" tabIndex={-1} className="cin-main">
        <div className="cin-shell cin-page-inner">
          <header className="cin-page-head">
            <div className="cin-page-head-copy">
              <span className="cin-kicker">Models</span>
              <h1 className="cin-title">Models and providers</h1>
              <p className="cin-lede">
                Assembly runs on free tiers only. Each provider you connect contributes a distinct model
                family, and a critic always comes from a different family than the position it attacks.
              </p>
            </div>
            <div className="cin-page-head-aside">
              <span className="cin-page-number">07 / 08</span>
              <Link href="/settings" className="cin-btn cin-btn-sm cin-btn-outline">
                <SlidersHorizontal className="size-4" aria-hidden />
                Manage keys
              </Link>
            </div>
          </header>

          {!loading && catalog && (
            <div className="cin-run-summary" aria-live="polite">
              <span>{connected} connected</span>
              <span>
                {families} famil{families === 1 ? "y" : "ies"} available
              </span>
              <span>{minimum} families minimum</span>
              <span>No quota percentages are guessed</span>
            </div>
          )}

          {loading ? (
            <div className="cin-model-grid" aria-busy="true" aria-label="Loading model providers">
              {[0, 1, 2, 3].map((index) => (
                <div key={index} className="cin-model-card">
                  <Skeleton className="mx-auto mt-2 h-[130px] w-[130px] rounded-full" />
                  <Skeleton className="mt-5 h-5 w-28" />
                  <Skeleton className="mt-3 h-3 w-full" />
                  <Skeleton className="mt-2 h-3 w-2/3" />
                </div>
              ))}
            </div>
          ) : !catalog ? (
            <div className="cin-empty-state">
              <span className="cin-kicker !mb-0">Unavailable</span>
              <h2>Provider list unavailable</h2>
              <p>
                Assembly could not load the free-provider catalog. Check that the local server is running,
                then retry. Keys already saved on this device are untouched.
              </p>
              <button type="button" className="cin-btn cin-btn-primary mt-6" onClick={() => void load()}>
                Retry
              </button>
            </div>
          ) : providers.length === 0 ? (
            <div className="cin-empty-state">
              <h2>No providers enabled</h2>
              <p>The backend catalog returned no enabled free providers. Check the server configuration.</p>
            </div>
          ) : (
            <div className="cin-model-grid">
              {providers.map((item) => {
                const isConnected = !!savedKeys[item.id]
                const roles = providerRoles(item)
                const familiesForProvider = familyList(item)
                return (
                  <article key={item.id} className="cin-model-card">
                    <div
                      className="cin-model-ring"
                      style={{ "--cin-value": isConnected ? 100 : 0 } as React.CSSProperties}
                      aria-hidden
                    >
                      <div className="cin-model-ring-center">
                        <strong>{item.models.length}</strong>
                        <span>model{item.models.length === 1 ? "" : "s"}</span>
                      </div>
                    </div>

                    <h2>{providerLabel(item.id)}</h2>
                    <p className="cin-model-roles">
                      {roles.length > 0 ? roles.join(" · ") : "Solver"}
                    </p>
                    <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                      {familiesForProvider.join(", ") || "unknown family"}
                      {!item.limits_ready && " · limits unverified"}
                    </p>

                    <div className="cin-model-foot">
                      {isConnected ? (
                        <span className="cin-model-state">
                          <CheckCircle2 className="mr-1.5 size-3.5" aria-hidden />
                          Connected
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="cin-model-state is-idle bg-transparent"
                          onClick={() => openKeyDialog(item)}
                        >
                          <KeyRound className="mr-1.5 size-3.5" aria-hidden />
                          Add key
                        </button>
                      )}
                      {item.key_url && !isConnected && (
                        <a
                          href={item.key_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="cin-model-key hover:text-brand"
                        >
                          free key
                          <ExternalLink className="ml-1 inline size-3" aria-hidden />
                        </a>
                      )}
                      {isConnected && (
                        <Link href="/settings" className="cin-model-key hover:text-brand">
                          manage
                        </Link>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          )}

          <section className="cin-cta mt-8" aria-label="Free tier policy">
            <div>
              <span className="cin-kicker">Free by design</span>
              <h2>Bring your own key.</h2>
              <p>
                There is no shared operator key and no billing path. A provider&apos;s limits are checked
                before it can join a run, and every key stays in this browser or the desktop credential
                store.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link href="/settings" className="cin-btn cin-btn-primary">
                <ShieldCheck className="size-4" aria-hidden />
                Open key settings
              </Link>
              <Link href="/chat" className="cin-btn cin-btn-outline">
                Start an investigation
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
          </section>
        </div>
      </main>

      <Dialog open={!!provider} onOpenChange={(open) => !open && !testing && setProvider(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add {provider ? providerLabel(provider.id) : "provider"} key</DialogTitle>
            <DialogDescription>
              Stored in this browser&apos;s key vault. It is sent only to the provider to authenticate a
              test or a run, never written to the backend or a log.
            </DialogDescription>
          </DialogHeader>

          <div className="cin-add-key-form">
            <label htmlFor="model-provider-key" className="text-xs font-semibold text-foreground">
              API key
            </label>
            <input
              id="model-provider-key"
              type="password"
              value={keyInput}
              onChange={(event) => setKeyInput(event.target.value)}
              placeholder="Paste the free key…"
              autoComplete="off"
              spellCheck="false"
            />
            {message && (
              <p
                role="status"
                className={`text-xs leading-relaxed ${
                  messageTone === "danger"
                    ? "text-danger"
                    : messageTone === "warning"
                      ? "text-warning"
                      : "text-success"
                }`}
              >
                {message}
              </p>
            )}
            <button
              type="button"
              className="cin-btn cin-btn-primary w-full"
              onClick={() => void saveKey()}
              disabled={!keyInput.trim() || testing}
            >
              {testing ? "Testing…" : "Test & save"}
            </button>
            {provider?.key_url && (
              <a
                href={provider.key_url}
                target="_blank"
                rel="noreferrer noopener"
                className="text-center text-xs text-brand hover:underline"
              >
                Get a free {providerLabel(provider.id)} key
              </a>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
