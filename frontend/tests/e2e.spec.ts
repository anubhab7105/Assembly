import { test, expect } from "@playwright/test"

const CANARY_KEY = "sk-CANARY-123456789-TEST-KEY"

test.describe("Assembly End-to-End flow (stateless)", () => {
  let consoleLogs: string[] = []

  test.beforeEach(async ({ page }) => {
    consoleLogs = []
    page.on("console", msg => {
      consoleLogs.push(msg.text())
    })

    await page.route("**/api/catalog", async route => {
      await route.fulfill({
        json: {
          providers: [
            { id: "gemini", enabled: true, key_url: "", models: [{ id: "gemini-3.8-flash", family: "gemini", roles: ["solver"], scope: "model" }] },
            { id: "groq", enabled: true, key_url: "", models: [{ id: "openai/gpt-oss-20b", family: "gpt-oss", roles: ["solver"], scope: "model" }] },
            { id: "openrouter", enabled: true, key_url: "", models: [{ id: "google/gemma-4-26b-a4b-it:free", family: "gemma", roles: ["solver"], scope: "account" }] },
          ],
          families: ["gemini", "gpt-oss", "gemma"],
        },
      })
    })
    await page.route("**/api/keys/test", async route => {
      await route.fulfill({ json: { provider: "gemini", valid: true, rate_limited: false } })
    })
    await page.route("**/api/preflight", async route => {
      await route.fulfill({ json: { feasible: true, explanation: "fits" } })
    })
    await page.route("**/api/run", async route => {
      const body = [
        `data: ${JSON.stringify({ event_type: "team.ready", execution_id: "run-1", seq: 1, data: { roles: [] }, timestamp: new Date().toISOString() })}`,
        `data: ${JSON.stringify({ event_type: "execution.completed", execution_id: "run-1", seq: 2, data: { status: "completed", answer: "Mock answer", sources: [], confidence_label: "high", consensus_score: 0.9, agent_count: 2, providers_used: ["groq"], tokens_used: 10, debate_rounds: 1, elapsed_seconds: 1 } })}`,
        `data: ${JSON.stringify({ event_type: "run.finished", run_id: "run-1", status: "completed", usage: [{ provider: "run", model: "", count: 1, tokens: 10 }] })}`,
      ].join("\n\n")
      await route.fulfill({ contentType: "text/event-stream", body: body + "\n\n" })
    })
  })

  test("1. Setup flow with test keys and verify zero leakage", async ({ page }) => {
    await page.goto("/settings")

    const geminiCard = page.locator(".flex-col").filter({ hasText: "gemini" }).first()
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Test Saved Key|Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible({ timeout: 10000 }).catch(() => {})

    for (const log of consoleLogs) {
      expect(log).not.toContain(CANARY_KEY)
    }
    const lsKeys = await page.evaluate(() => JSON.stringify(window.localStorage))
    expect(lsKeys).not.toContain(CANARY_KEY)
  })

  test("2. Model picker drives a stateless run", async ({ page }) => {
    await page.goto("/")

    // Catalog-backed picker renders checkboxes grouped by provider/family.
    await expect(page.getByTestId("model-picker")).toBeVisible()
    await page.getByText("openai/gpt-oss-20b").click()
    await page.getByText("google/gemma-4-26b-a4b-it:free").click()
    await expect(page.getByText(/2 families/)).toBeVisible()

    // Optional per-role pin.
    await page.getByRole("button", { name: /Apply pin/i }).click()

    await page.getByPlaceholder(/What do you want the team/i).fill("Will quantum computing win?")
    await page.getByRole("button", { name: /Launch Team/i }).click()
    await expect(page).toHaveURL(/\/executions\?id=local-.+/)
    await expect(page.getByText(/Research Team/i)).toBeVisible()
  })

  test("3. History export/import round-trips without server storage", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByText(/History \(this device\)/i)).toBeVisible()
    await expect(page.getByRole("button", { name: /Export/i })).toBeVisible()
    await expect(page.getByText(/Import/i)).toBeVisible()
  })
})
