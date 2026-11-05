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
            { id: "gemini", enabled: true, limits_ready: true, limits_issue: null, key_url: "", models: [{ id: "gemini-3.8-flash", family: "gemini", roles: ["solver"], scope: "model" }] },
            { id: "groq", enabled: true, limits_ready: true, limits_issue: null, key_url: "", models: [{ id: "openai/gpt-oss-20b", family: "gpt-oss", roles: ["solver"], scope: "model" }] },
            { id: "openrouter", enabled: true, limits_ready: true, limits_issue: null, key_url: "", models: [{ id: "google/gemma-4-26b-a4b-it:free", family: "gemma", roles: ["solver"], scope: "account" }] },
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

  test("restores a saved dark theme from the document head without a hydration flash", async ({ page }) => {
    await page.addInitScript(() => {
      const toggles: boolean[] = []
      Object.defineProperty(window, "__assemblyThemeToggles", {
        value: toggles,
        configurable: true,
      })
      const nativeToggle = DOMTokenList.prototype.toggle
      DOMTokenList.prototype.toggle = function (token, force) {
        if (this === document.documentElement.classList && token === "dark") {
          toggles.push(force === undefined ? !this.contains(token) : force)
        }
        return nativeToggle.call(this, token, force)
      }
      window.localStorage.setItem("assembly:theme", "dark")
    })

    await page.goto("/")
    await expect(page.locator("html")).toHaveClass(/dark/)
    await expect(page.locator("head #assembly-theme-bootstrap")).toHaveAttribute("src", "/theme-bootstrap.js")
    await expect(page.getByRole("button", { name: "Switch to light mode" }).first()).toBeVisible()

    const themeToggles = await page.evaluate(() =>
      (window as unknown as { __assemblyThemeToggles: boolean[] }).__assemblyThemeToggles,
    )
    expect(themeToggles.length).toBeGreaterThan(0)
    expect(themeToggles.every(Boolean)).toBe(true)
  })

  test("uses the system dark preference before hydration when no theme is saved", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" })
    await page.goto("/")
    await expect(page.locator("html")).toHaveClass(/dark/)
    await expect(page.locator("head #assembly-theme-bootstrap")).toHaveCount(1)
  })

  test("landing page explains the research workflow and remembers the chosen theme", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByRole("heading", { name: /one question/i })).toBeVisible()
    await expect(page.getByRole("link", { name: "Set up keys" })).toHaveAttribute("href", "/settings")

    const themeToggle = page.getByRole("button", { name: "Switch to dark mode" })
    await themeToggle.click()
    await expect(page.locator("html")).toHaveClass(/dark/)

    await page.getByRole("link", { name: "Start an investigation" }).first().click()
    await expect(page).toHaveURL(/\/chat$/)
    await expect(page.locator("html")).toHaveClass(/dark/)
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


  test("supported attachments show a removable chip before a run", async ({ page }) => {
    await page.goto("/chat")
    await expect(page.getByTestId("privacy-dialog")).toBeVisible({ timeout: 10000 })
    await page.getByLabel(/my question is sent to the model providers/i).check()
    await page.getByTestId("privacy-acknowledge").click()

    await page.locator('input[aria-label="Choose investigation attachments"]').setInputFiles({
      name: "analysis-notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Context for the next investigation."),
    })

    await expect(page.locator('[aria-label="Selected attachments"]')).toContainText("analysis-notes.txt")
    await expect(page.locator('[aria-label="Selected attachments"]')).toContainText("TXT")
    const remove = page.getByRole("button", { name: "Remove analysis-notes.txt" })
    await expect(remove).toBeVisible()
    await remove.click()
    await expect(page.locator('[aria-label="Selected attachments"]')).toHaveCount(0)
  })

  test("unsupported attachment types produce a clear validation error", async ({ page }) => {
    await page.goto("/chat")
    await expect(page.getByTestId("privacy-dialog")).toBeVisible({ timeout: 10000 })
    await page.getByLabel(/my question is sent to the model providers/i).check()
    await page.getByTestId("privacy-acknowledge").click()

    await page.locator('input[aria-label="Choose investigation attachments"]').setInputFiles({
      name: "scan.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.7 not supported by v1"),
    })

    await expect(page.locator("#question-status")).toContainText("unsupported type")
    await expect(page.locator('[aria-label="Selected attachments"]')).toHaveCount(0)
  })

  test("each application route exposes exactly one primary main landmark", async ({ page }) => {
    for (const route of ["/", "/chat", "/settings", "/executions"]) {
      await page.goto(route)

      if (route === "/chat") {
        const privacyDialog = page.getByTestId("privacy-dialog")
        await expect(privacyDialog).toBeVisible({ timeout: 10000 })
        await page.getByLabel(/my question is sent to the model providers/i).check()
        await page.getByTestId("privacy-acknowledge").click()
        await expect(privacyDialog).toBeHidden()
      }

      await expect(page.getByRole("main")).toHaveCount(1)
      await expect(page.locator("#main-content")).toHaveJSProperty("tagName", "MAIN")
    }
  })

  test("mobile navigation traps focus, closes on Escape, and restores its trigger", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto("/settings")

    // The modal makes the page background inert, so use a DOM locator
    // to inspect the trigger's expanded state while the dialog is open.
    const trigger = page.locator('button[aria-label="Open menu"]')
    await expect(trigger).toHaveAttribute("aria-expanded", "false")
    await expect(trigger).not.toHaveAttribute("aria-controls")
    await trigger.click()

    const dialog = page.getByRole("dialog", { name: "Navigation menu" })
    await expect(dialog).toBeVisible()
    await expect(trigger).toHaveAttribute("aria-expanded", "true")
    await expect(trigger).toHaveAttribute("aria-controls", "mobile-menu")
    await expect(dialog.locator("#mobile-menu")).toHaveCount(1)
    await expect.poll(() =>
      dialog.locator("#mobile-menu").evaluate((menu) => menu.contains(document.activeElement)),
    ).toBe(true)

    for (let index = 0; index < 12; index += 1) {
      await page.keyboard.press("Tab")
      await expect(dialog.locator(":focus")).toBeVisible()
    }

    await page.keyboard.press("Escape")
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    await expect(trigger).toHaveAttribute("aria-expanded", "false")
    await expect(trigger).not.toHaveAttribute("aria-controls")
  })

  test("privacy notice has accessible naming and remains until acknowledged", async ({ page }) => {
    await page.goto("/chat")
    const dialog = page.getByRole("dialog", { name: "Privacy notice" })
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute("aria-modal", "true")
    await expect(dialog).toHaveAttribute("aria-describedby", "privacy-dialog-description")
    await expect.poll(() =>
      dialog.evaluate((element) => element.contains(document.activeElement)),
    ).toBe(true)

    await page.keyboard.press("Escape")
    await expect(dialog).toBeVisible()
    await page.getByLabel(/my question is sent to the model providers/i).check()
    await page.getByTestId("privacy-acknowledge").click()
    await expect(dialog).toBeHidden()
  })
})
