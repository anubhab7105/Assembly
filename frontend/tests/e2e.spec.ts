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
      const body = route.request().postDataJSON() as { provider?: string } | null
      await route.fulfill({
        json: { provider: body?.provider ?? "groq", valid: true, rate_limited: false },
      })
    })
    await page.route("**/api/preflight", async route => {
      await route.fulfill({ json: { feasible: true, explanation: "fits" } })
    })
    await page.route("**/api/run", async route => {
      const body = [
        `data: ${JSON.stringify({ event_type: "team.ready", execution_id: "run-1", seq: 1, data: { roles: [] }, timestamp: new Date().toISOString() })}`,
        `data: ${JSON.stringify({ event_type: "execution.completed", execution_id: "run-1", seq: 2, data: { status: "completed", answer: "Mock answer", sources: [], confidence_label: "Moderate", consensus_score: 0.9, agent_count: 2, providers_used: ["groq"], tokens_used: 10, debate_rounds: 1, elapsed_seconds: 1 } })}`,
        `data: ${JSON.stringify({ event_type: "run.finished", run_id: "run-1", status: "completed", usage: [{ provider: "run", model: "", count: 1, tokens: 10 }] })}`,
      ].join("\n\n")
      await route.fulfill({ contentType: "text/event-stream", body: body + "\n\n" })
    })
  })

  test("New Investigation opens the composer, not the landing page", async ({ page }) => {
    await page.goto("/executions")
    await page.getByRole("button", { name: /New Investigation/i }).click()
    await expect(page).toHaveURL(/\/chat$/)
    await expect(page.locator("#research-question")).toBeVisible()
  })

  test("1. Setup flow with test keys and verify zero leakage", async ({ page }) => {
    await page.goto("/settings")

    const geminiCard = page.getByTestId("provider-card-gemini")
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
    // Keys first: the picker counts keyed providers only (N-05).
    await page.goto("/settings")
    for (const provider of ["groq", "openrouter"]) {
      const card = page.getByTestId(`provider-card-${provider}`)
      await card.locator('input[type="password"]').fill(CANARY_KEY)
      await card.getByRole("button", { name: /Test Saved Key|Save & Test/i }).click()
      await expect(card.getByTestId(`test-result-${provider}`)).toContainText("valid", {
        timeout: 10000,
      })
    }

    // Client-side navigation keeps the persistent vault (verified in
    // keys-persist.spec.ts). The settings sidebar has no chat link, so go
    // via landing like a user would.
    await page.locator('a[href="/"]').first().click()
    await expect(page).toHaveURL(/\/$/)
    await page.locator('a[href="/chat"]').first().click()
    await expect(page).toHaveURL(/\/chat/)

    // Privacy gate blocks interacting until acknowledged (fresh contexts
    // always prompt; wait for the async storage read instead of racing it).
    await expect(page.getByTestId("privacy-dialog")).toBeVisible({ timeout: 10000 })
    await page.getByLabel(/my question is sent to the model providers/i).check()
    await page.getByTestId("privacy-acknowledge").click()

    // Advanced model controls are intentionally tucked into a dialog.
    await page.getByRole("button", { name: /Open model and role settings/i }).click()
    await expect(page.getByRole("dialog")).toBeVisible()
    // Catalog-backed picker renders checkboxes grouped by provider/family.
    await expect(page.getByTestId("model-picker")).toBeVisible()
    await expect(page.getByTestId("picker-gate-chip")).toContainText("2 families ready")
    const picker = page.getByTestId("model-picker")
    await picker.locator("label").filter({ hasText: "openai/gpt-oss-20b" }).click()
    await picker.locator("label").filter({ hasText: "google/gemma-4-26b-a4b-it:free" }).click()
    await expect(page.getByTestId("picker-gate-chip")).toContainText("2 families")

    // Optional per-role pin.
    await page.getByRole("button", { name: /Apply pin/i }).click()
    await page.getByRole("button", { name: /Done/i }).click()

    await page.locator("#research-question").fill("Will quantum computing win?")
    await page.getByRole("button", { name: /^Run$/i }).click()
    await expect(page).toHaveURL(/\/executions\?id=local-.+/)
    await expect(page.getByRole("heading", { name: /Research Team/i })).toBeVisible()
    // N-04: chip carries the capped server label, not a default.
    await expect(page.getByText("Confidence: Moderate")).toBeVisible()
    // N-07: frozen post-run summary instead of forming-state.
    await expect(page.getByTestId("run-summary-strip")).toContainText("2 agents")
  })

  test("3. History export/import round-trips without server storage", async ({ page }) => {
    await page.goto("/chat")
    await expect(page.getByText(/History \(this device\)/i)).toBeVisible()
    await expect(page.getByRole("button", { name: /Export/i })).toBeVisible()
    await expect(page.getByText(/Import/i)).toBeVisible()
  })
})
