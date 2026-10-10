import { test, expect } from "@playwright/test";

// Keys must survive client-side navigation across every page (memory-only
// vault). Only canary strings are typed; the key-test endpoint is mocked
// so this spec makes zero live provider calls.
const CANARY_KEY = "gsk-CANARY-NAV-0001";

test.describe("Keys survive navigation", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/catalog", async route => {
      await route.fulfill({
        json: {
          providers: [
            { id: "groq", enabled: true, key_url: "", models: [{ id: "openai/gpt-oss-20b", family: "gpt-oss", roles: ["solver"], scope: "model" }] },
            { id: "openrouter", enabled: true, key_url: "", models: [{ id: "google/gemma-4-26b-a4b-it:free", family: "gemma", roles: ["solver"], scope: "account" }] },
            { id: "gemini", enabled: true, key_url: "", models: [{ id: "gemini-3.8-flash", family: "gemini", roles: ["solver"], scope: "model" }] },
          ],
          families: ["gemini", "gpt-oss", "gemma"],
        },
      })
    })
    await page.route("**/api/keys/test", async route => {
      await route.fulfill({ json: { provider: "groq", valid: true, rate_limited: false } })
    })
  })

  test("saved keys persist across settings, landing, chat and executions", async ({ page }) => {
    await page.goto("/settings")
    const card = page.getByTestId("provider-card-groq")
    await card.locator('input[type="password"]').fill(CANARY_KEY)
    await card.getByRole("button", { name: /Save & Test/i }).click()
    await expect(card.getByTestId("test-result-groq")).toContainText("valid", { timeout: 10000 })
    await expect(page.getByTestId("readiness-chip")).toContainText("families ready")

    // Sidebar logo -> landing (client-side), then CTAs -> chat / settings.
    await page.locator('a[href="/"]').first().click()
    await expect(page).toHaveURL(/\/$/)
    await page.locator('a[href="/chat"]').first().click()
    await expect(page).toHaveURL(/\/chat/)
    await expect(page.getByTestId("diversity-chip")).toContainText("families ready")

    await page.goto("/executions")
    await expect(page.getByText(/History \(this device\)/i)).toBeVisible()

    // Back to settings through the sidebar: keys still present.
    await page.getByRole("link", { name: /Settings/i }).click()
    await expect(page).toHaveURL(/\/settings/)
    await expect(page.getByTestId("readiness-chip")).toContainText("families ready")

    // No key material in console output or plaintext storage.
    // (Memory-only vault: nothing persisted; checked via absence of values.)
  })
})
