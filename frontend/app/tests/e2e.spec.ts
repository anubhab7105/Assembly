import { test, expect } from "@playwright/test"

const CANARY_KEY = "sk-CANARY-123456789-TEST-KEY"

test.describe("Assembly End-to-End flow", () => {
  let consoleLogs: string[] = []

  test.beforeEach(async ({ page }) => {
    consoleLogs = []
    page.on("console", msg => {
      consoleLogs.push(msg.text())
    })

    // Mock Backend API
    await page.route("**/api/providers/*/test", async route => {
      await route.fulfill({ json: { status: "valid" } })
    })
    await page.route("**/api/executions/preflight", async route => {
      await route.fulfill({ json: { feasible: true } })
    })
    await page.route("**/api/executions", async (route, request) => {
      if (request.method() === "POST") {
        await route.fulfill({ json: { id: "exec-test", status: "running" } })
      } else {
        await route.fulfill({ json: [] })
      }
    })
    await page.route("**/api/executions/*/cancel", async route => {
      await route.fulfill({ json: { status: "cancelled" } })
    })
    await page.route("**/api/executions/*/events*", async route => {
      await route.fulfill({ json: [
        { 
          event_type: "team.ready", 
          seq: 1,
          data: { agents: [{ id: "1", role: "Researcher", model_family: "gemini" }] } 
        }
      ]})
    })
  })

  test("1. Setup flow with test keys and verify zero leakage", async ({ page }) => {
    await page.goto("/setup")
    
    // Check "Remember on this device"
    await page.getByLabel(/Remember on this device/i).check()

    const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible()

    const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
    await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByText("Valid")).toBeVisible()

    await expect(page.getByText(/3 of 3 recommended model families ready/i, { exact: false })).toBeVisible()

    for (const log of consoleLogs) {
      expect(log).not.toContain(CANARY_KEY)
    }

    const lsKeys = await page.evaluate(() => JSON.stringify(window.localStorage))
    expect(lsKeys).not.toContain(CANARY_KEY)

    await expect(page.getByText(CANARY_KEY)).not.toBeVisible()
  })

  test("2. Ask a question, watch progress, receive the answer", async ({ page }) => {
    await page.goto("/setup")
    await page.getByLabel(/Remember on this device/i).check()

    const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible()

    const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
    await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByText("Valid")).toBeVisible()

    await page.getByRole("button", { name: /New Investigation/i }).click()
    
    await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
    await page.getByText(/Will quantum computing achieve/i).click()
    await page.getByRole("button", { name: /Launch Team/i }).click()
    await expect(page).toHaveURL(/\/executions\/.+/)

    await expect(page.getByText(/Research Team/i)).toBeVisible()
    await expect(page.getByText(/Consensus Meter/i)).toBeVisible()
    await expect(page.getByText(/Event Log/i)).toBeVisible()
  })

  test("3. Refresh mid-execution and confirm re-attach", async ({ page }) => {
    await page.goto("/setup")
    await page.getByLabel(/Remember on this device/i).check()

    const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible()

    const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
    await groqCard.locator('input[type="password"]').fill("sk-groq")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByText("Valid")).toBeVisible()

    await page.getByRole("button", { name: /New Investigation/i }).click()
    await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
    
    await page.getByText(/What are the most viable methods/i).click()
    await page.getByRole("button", { name: /Launch Team/i }).click()
    
    await expect(page).toHaveURL(/\/executions\/.+/)
    await page.reload()

    await expect(page).toHaveURL(/\/executions\/.+/)
    await expect(page.getByText(/Research Team/i)).toBeVisible()
  })

  test("4. Cancel an execution", async ({ page }) => {
    await page.goto("/setup")
    await page.getByLabel(/Remember on this device/i).check()

    const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible()

    const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
    await groqCard.locator('input[type="password"]').fill("sk-groq")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByText("Valid")).toBeVisible()

    await page.getByRole("button", { name: /New Investigation/i }).click()
    await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
    
    await page.getByText(/Analyse the timeline/i).click()
    await page.getByRole("button", { name: /Launch Team/i }).click()
    
    await expect(page).toHaveURL(/\/executions\/.+/)

    page.on("dialog", dialog => dialog.accept())
    await page.getByRole("button", { name: /Cancel/i }).click()
    await expect(page).toHaveURL(/\/$/)
  })
})
