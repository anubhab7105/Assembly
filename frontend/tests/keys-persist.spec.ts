import { test, expect, type Page } from "@playwright/test";

// P0 refresh regression: saved provider keys must survive a normal page
// reload via the canonical persistent vault. Only canary strings are typed;
// the key-test/preflight/run endpoints are mocked so this spec makes zero
// live provider calls.
const CANARY_GROQ = "gsk-CANARY-PERSIST-GROQ-01";
const CANARY_GEMINI = "AIza-CANARY-PERSIST-GEMINI-02";
const CANARY_OPENROUTER = "sk-or-CANARY-PERSIST-OR-03";

const CATALOG = {
  providers: [
    { id: "groq", enabled: true, key_url: "", models: [{ id: "openai/gpt-oss-20b", family: "gpt-oss", roles: ["solver"], scope: "model" }] },
    { id: "gemini", enabled: true, key_url: "", models: [{ id: "gemini-3.8-flash", family: "gemini", roles: ["solver"], scope: "model" }] },
    { id: "openrouter", enabled: true, key_url: "", models: [{ id: "google/gemma-4-26b-a4b-it:free", family: "gemma", roles: ["solver"], scope: "account" }] },
  ],
  families: ["gpt-oss", "gemini", "gemma"],
};

async function mockNetwork(page: Page) {
  await page.route("**/api/catalog", async route => {
    await route.fulfill({ json: CATALOG })
  })
  await page.route("**/api/keys/test", async route => {
    const body = route.request().postDataJSON() as { provider?: string } | null
    await route.fulfill({ json: { provider: body?.provider ?? "groq", valid: true, rate_limited: false } })
  })
  await page.route("**/api/preflight", async route => {
    await route.fulfill({ json: { feasible: true, explanation: "fits" } })
  })
}

async function saveKey(page: Page, provider: string, key: string) {
  const card = page.getByTestId(`provider-card-${provider}`)
  await card.locator('input[type="password"]').fill(key)
  await card.getByRole("button", { name: /Save & Test/i }).click()
  await expect(card.getByTestId(`test-result-${provider}`)).toContainText("valid", { timeout: 10000 })
}

test.describe("Keys survive refresh (P0)", () => {
  test.beforeEach(async ({ page }) => {
    await mockNetwork(page)
  })

  test("1. save one key, reload, configuration is restored", async ({ page }) => {
    await page.goto("/settings")
    await saveKey(page, "groq", CANARY_GROQ)
    await expect(page.getByTestId("readiness-chip")).toContainText("families ready")

    await page.reload()
    await expect(page.getByTestId("provider-card-groq")).toBeVisible({ timeout: 10000 })
    // Restored keys count toward readiness without re-testing this session.
    await expect(page.getByTestId("readiness-chip")).toContainText("gpt-oss", { timeout: 10000 })
    // Placeholder shows the masked restored key, not the empty prompt.
    await expect(page.getByTestId("provider-card-groq").locator('input[type="password"]')).toHaveAttribute(
      "placeholder", /gsk-•/,
    )
  })

  test("2. multiple providers all survive refresh", async ({ page }) => {
    await page.goto("/settings")
    await saveKey(page, "groq", CANARY_GROQ)
    await saveKey(page, "gemini", CANARY_GEMINI)
    await saveKey(page, "openrouter", CANARY_OPENROUTER)
    await expect(page.getByTestId("readiness-chip")).toContainText("3 families ready", { timeout: 10000 })

    await page.reload()
    await expect(page.getByTestId("readiness-chip")).toContainText("3 families ready", { timeout: 10000 })
  })

  test("3. reload with pre-existing saved values does not overwrite them", async ({ page }) => {
    await page.addInitScript((seed: string) => {
      window.localStorage.setItem("assembly:keys_v1", seed)
    }, JSON.stringify({ groq: CANARY_GROQ }))
    await page.goto("/settings")
    await expect(page.getByTestId("readiness-chip")).toContainText("gpt-oss", { timeout: 10000 })
    // A second reload with no interaction must keep the seeded value.
    await page.reload()
    await expect(page.getByTestId("readiness-chip")).toContainText("gpt-oss", { timeout: 10000 })
  })

  test("4. navigate away and back without losing configuration", async ({ page }) => {
    await page.goto("/settings")
    await saveKey(page, "groq", CANARY_GROQ)
    await page.locator('a[href="/"]').first().click()
    await expect(page).toHaveURL(/\/$/)
    await page.locator('a[href="/chat"]').first().click()
    await expect(page).toHaveURL(/\/chat/)
    // First visit shows the blocking privacy dialog: wait for it, then
    // acknowledge before using sidebar navigation.
    await expect(page.getByTestId("privacy-dialog")).toBeVisible({ timeout: 10000 })
    await page.getByLabel(/my question is sent to the model providers/i).check()
    await page.getByTestId("privacy-acknowledge").click()

    // The informational cookie notice is fixed to the viewport bottom and can
    // overlap the sidebar's bottom Settings link in browser automation.
    const cookieNotice = page.getByRole("region", { name: /Cookie notice/i })
    if (await cookieNotice.isVisible()) {
      await cookieNotice.getByRole("button", { name: /Got it/i }).click()
    }

    await page.getByRole("link", { name: /Settings/i }).click()
    await expect(page).toHaveURL(/\/settings/)
    await expect(page.getByTestId("readiness-chip")).toContainText("gpt-oss", { timeout: 10000 })
  })

  test("5. updating one provider keeps the others", async ({ page }) => {
    await page.goto("/settings")
    await saveKey(page, "groq", CANARY_GROQ)
    await saveKey(page, "gemini", CANARY_GEMINI)
    const groqCard = page.getByTestId("provider-card-groq")
    await groqCard.locator('input[type="password"]').fill("gsk-CANARY-PERSIST-GROQ-02")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByTestId("test-result-groq")).toContainText("valid", { timeout: 10000 })

    await page.reload()
    await expect(page.getByTestId("readiness-chip")).toContainText("2 families ready", { timeout: 10000 })
    await expect(page.getByTestId("readiness-chip")).toContainText("gemini", { timeout: 10000 })
  })

  test("6. removing one provider keeps the others configured", async ({ page }) => {
    await page.goto("/settings")
    await saveKey(page, "groq", CANARY_GROQ)
    await saveKey(page, "gemini", CANARY_GEMINI)
    await page.getByTestId("remove-groq").click()
    await expect(page.getByTestId("readiness-chip")).toContainText("gemini", { timeout: 10000 })
    await expect(page.getByTestId("readiness-chip")).not.toContainText("gpt-oss")

    await page.reload()
    await expect(page.getByTestId("readiness-chip")).toContainText("gemini", { timeout: 10000 })
    await expect(page.getByTestId("readiness-chip")).not.toContainText("gpt-oss")
  })

  test("7. picker and execution request agree on provider readiness", async ({ page }) => {
    let runBody: Record<string, unknown> | null = null
    let preflightBody: Record<string, unknown> | null = null
    await page.route("**/api/run", async route => {
      runBody = route.request().postDataJSON() as unknown as Record<string, unknown>
      const body = [
        `data: ${JSON.stringify({ event_type: "execution.completed", execution_id: "run-1", seq: 1, data: { status: "completed", answer: "Mock", sources: [], confidence_label: "Moderate", consensus_score: 0.9, agent_count: 2, providers_used: ["groq", "gemini"], tokens_used: 10, debate_rounds: 1, elapsed_seconds: 1 } })}`,
        `data: ${JSON.stringify({ event_type: "run.finished", run_id: "run-1", status: "completed", usage: [] })}`,
      ].join("\n\n")
      await route.fulfill({ contentType: "text/event-stream", body: body + "\n\n" })
    })
    await page.route("**/api/preflight", async route => {
      preflightBody = route.request().postDataJSON() as unknown as Record<string, unknown>
      await route.fulfill({ json: { feasible: true, explanation: "fits" } })
    })

    await page.goto("/settings")
    await saveKey(page, "groq", CANARY_GROQ)
    await saveKey(page, "gemini", CANARY_GEMINI)

    await page.reload()
    await page.locator('a[href="/"]').first().click()
    await page.locator('a[href="/chat"]').first().click()
    await expect(page.getByTestId("diversity-chip")).toContainText("gpt-oss", { timeout: 10000 })

    await expect(page.getByTestId("privacy-dialog")).toBeVisible({ timeout: 10000 })
    await page.getByLabel(/my question is sent to the model providers/i).check()
    await page.getByTestId("privacy-acknowledge").click()

    // Model selection is advanced configuration, so inspect it in its dialog.
    await page.getByRole("button", { name: /Open model and role settings/i }).click()
    await expect(page.getByTestId("picker-gate-chip")).toContainText("2 families ready", { timeout: 10000 })
    await page.getByRole("button", { name: /Done/i }).click()
    await page.locator("#research-question").fill("Does the picker agree with the run?")
    await page.getByRole("button", { name: /^Run$/i }).click()
    await expect(page).toHaveURL(/\/executions\?id=local-.+/, { timeout: 15000 })

    expect(preflightBody).not.toBeNull()
    expect(runBody).not.toBeNull()
    expect((preflightBody as unknown as Record<string, unknown>)["provider_keys"]).toEqual(
      expect.objectContaining({ groq: CANARY_GROQ, gemini: CANARY_GEMINI }),
    )
    expect((runBody as unknown as Record<string, unknown>)["provider_keys"]).toEqual(
      expect.objectContaining({ groq: CANARY_GROQ, gemini: CANARY_GEMINI }),
    )
  })

  test("8. storage failure is surfaced honestly", async ({ page }) => {
    await page.addInitScript(() => {
      const fail = () => {
        throw new Error("storage blocked")
      }
      try {
        const factory = window.indexedDB
        const proto = Object.getPrototypeOf(factory) as IDBFactory
        proto.open = (() => { throw new Error("storage blocked") }) as typeof proto.open
        void fail
      } catch { /* init-time access may itself throw; the save still fails below */ }
      try {
        Storage.prototype.setItem = () => {
          throw new Error("storage blocked")
        }
      } catch { /* ignore */ }
    })
    await page.goto("/settings")
    const card = page.getByTestId("provider-card-groq")
    await card.locator('input[type="password"]').fill(CANARY_GROQ)
    await card.getByRole("button", { name: /Save & Test/i }).click()
    await expect(card.getByTestId("save-error-groq")).toContainText(/Couldn't save|storage/i, { timeout: 10000 })
    // Nothing claimed saved: no readiness, no masked placeholder.
    await expect(page.getByTestId("readiness-chip")).toContainText("0 families ready")
  })

  test("9. keys never appear in URLs, console logs, or localStorage plaintext", async ({ page }) => {
    const consoleLogs: string[] = []
    page.on("console", msg => {
      consoleLogs.push(msg.text())
    })
    // Passive observer (no route interception, so mocked endpoints keep working).
    const seenUrls: string[] = []
    page.on("request", req => {
      seenUrls.push(req.url())
    })
    await page.goto("/settings")
    await saveKey(page, "groq", CANARY_GROQ)
    await page.reload()
    await expect(page.getByTestId("readiness-chip")).toContainText("gpt-oss", { timeout: 10000 })

    for (const url of seenUrls) expect(url).not.toContain(CANARY_GROQ)
    expect(page.url()).not.toContain(CANARY_GROQ)
    for (const log of consoleLogs) expect(log).not.toContain(CANARY_GROQ)
    // IndexedDB is the canonical store; the localStorage mirror stays empty
    // while IndexedDB is healthy, so plaintext must not leak there.
    const ls = await page.evaluate(() => JSON.stringify(window.localStorage))
    expect(ls).not.toContain(CANARY_GROQ)
  })
})
