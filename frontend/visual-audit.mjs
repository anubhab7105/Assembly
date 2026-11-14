import { chromium } from "playwright"
import fs from "node:fs"
import path from "node:path"

const BASE = "http://localhost:3100"
const OUT = "C:/Users/Arkap/AppData/Local/Temp/opencode/assembly_visual"
fs.mkdirSync(OUT, { recursive: true })

const history = [
  {
    id: "local-visual-1",
    question: "Should we move the primary database to a multi-region deployment now, or wait until traffic grows?",
    answer:
      "**Wait for now.** At the current scale, a single primary with read replicas is cheaper and simpler.\n\n- Read replicas cover the read-heavy path without cross-region write coordination.\n- The operational cost of multi-region failover is hard to justify below roughly 10x current traffic.\n- Revisit when latency targets or uptime requirements demand it.\n\n### What changes the answer\n\nA hard regional-uptime requirement or a latency SLO below 120 ms for a second continent would move the recommendation toward multi-region.",
    status: "completed",
    created_at: new Date().toISOString(),
    minutes: 10,
    consensus: 0.72,
    confidence: "Moderate",
    agentCount: 5,
    providers: ["gemini", "groq", "openrouter"],
    debateRounds: 2,
    tokens: 18450,
    elapsedSeconds: 548,
    modelFamilies: ["gemini", "gpt-oss", "gemma"],
    verification: { agents: 5, families: 3, rounds: 2, disagreements_resolved: 1, sources_verified: 3 },
    disagreements: [
      { id: "d1", agent_id: "sk-1", issue: "The cost estimate ignores cross-region egress.", resolved: true },
      { id: "d2", agent_id: "sk-2", issue: "No agent checked the real traffic curve.", resolved: false },
    ],
    attachments: [],
  },
  {
    id: "local-visual-2",
    question: "Summarize the EU AI Act duties for a small open-source model provider.",
    answer: "A short answer.",
    status: "completed",
    created_at: new Date(Date.now() - 86_400_000).toISOString(),
    minutes: 5,
    consensus: 0.81,
    confidence: "High",
    agentCount: 4,
    providers: ["gemini", "groq"],
    debateRounds: 1,
    tokens: 9200,
    elapsedSeconds: 241,
    verification: { agents: 4, families: 2, rounds: 1, disagreements_resolved: 0, sources_verified: 4 },
  },
  {
    id: "local-visual-3",
    question: "Best way to cache API responses for a read-heavy dashboard?",
    answer: "Cache at the edge.",
    status: "completed",
    created_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    minutes: 3,
    consensus: 0.58,
    confidence: "Low",
    agentCount: 3,
    providers: ["groq", "openrouter"],
    debateRounds: 1,
    tokens: 4100,
    elapsedSeconds: 171,
    verification: { agents: 3, families: 2, rounds: 1, disagreements_resolved: 1, sources_verified: 2 },
  },
]

const catalog = {
  providers: [
    {
      id: "gemini",
      enabled: true,
      limits_ready: true,
      key_url: "https://aistudio.google.com/app/apikey",
      models: [
        { id: "gemini-3.8-flash", family: "gemini", roles: ["planner", "synthesizer"], scope: "model" },
        { id: "gemini-3.8-pro", family: "gemini", roles: ["solver", "researcher"], scope: "model" },
      ],
    },
    {
      id: "groq",
      enabled: true,
      limits_ready: true,
      key_url: "https://console.groq.com/keys",
      models: [
        { id: "openai/gpt-oss-20b", family: "gpt-oss", roles: ["solver"], scope: "model" },
        { id: "llama-4-scout", family: "llama", roles: ["critic"], scope: "model" },
      ],
    },
    {
      id: "openrouter",
      enabled: true,
      limits_ready: true,
      key_url: "https://openrouter.ai/keys",
      models: [
        { id: "google/gemma-4-26b-a4b-it:free", family: "gemma", roles: ["solver", "critic"], scope: "account" },
      ],
    },
    {
      id: "mistral",
      enabled: true,
      limits_ready: false,
      limits_issue: "Free-tier limits are unverified for this deployment.",
      key_url: "https://console.mistral.ai/api-keys/",
      models: [{ id: "mistral-small", family: "mistral", roles: ["solver"], scope: "model" }],
    },
  ],
  families: ["gemini", "gpt-5", "gemma", "llama", "mistral"],
  recommended_order: ["gemini", "groq", "openrouter", "mistral"],
  minimum_families: 2,
}

async function seed(page) {
  await page.evaluate(async ({ history }) => {
    await new Promise((resolve, reject) => {
      const req = indexedDB.open("assembly", 1)
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains("kv")) req.result.createObjectStore("kv")
      }
      req.onerror = () => reject(req.error)
      req.onsuccess = () => {
        const db = req.result
        const tx = db.transaction("kv", "readwrite")
        const store = tx.objectStore("kv")
        store.put(history, "history")
        store.put(
          JSON.stringify({ version: 2, acknowledged_at: new Date().toISOString() }),
          "setting:privacy_notice_ack",
        )
        tx.oncomplete = () => resolve()
        tx.onerror = () => reject(tx.error)
      }
    })
  }, { history })
}

async function run(theme, viewport, label) {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 })
  await context.addInitScript(({ theme }) => {
    window.localStorage.setItem("assembly:theme", theme)
    window.localStorage.setItem("assembly:cookie-choice", "dismissed")
  }, { theme })
  await context.route("**/api/catalog", (route) => route.fulfill({ json: catalog }))
  await context.route("**/api/keys/test", (route) =>
    route.fulfill({ json: { provider: "gemini", valid: true, rate_limited: false, message: "Connected to gemini." } }),
  )

  const page = await context.newPage()
  await page.goto(`${BASE}/`, { waitUntil: "load" })
  await seed(page)

  const routes = [
    ["landing", "/"],
    ["chat", "/chat"],
    ["history", "/history"],
    ["executions", "/executions?id=local-visual-1"],
    ["models", "/models"],
    ["settings", "/settings"],
  ]

  for (const [name, route] of routes) {
    await page.goto(`${BASE}${route}`, { waitUntil: "load" })
    await page.waitForTimeout(1200)
    const fullPage = name === "landing"
    await page.screenshot({
      path: path.join(OUT, `${label}-${name}.png`),
      fullPage,
    })
    console.log(`shot ${label}-${name}`, await page.viewportSize())
  }

  await browser.close()
}

await run("light", { width: 1440, height: 1000 }, "desktop-light")
await run("dark", { width: 1440, height: 1000 }, "desktop-dark")
await run("light", { width: 390, height: 844 }, "mobile-light")
await run("dark", { width: 390, height: 844 }, "mobile-dark")
console.log("done", OUT)
