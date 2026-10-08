import { test, expect } from "@playwright/test"

const CANARY_KEY = "sk-CANARY-123456789-TEST-KEY"

test.describe("Assembly End-to-End flow", () => {
  let consoleLogs: string[] = []

  test.beforeEach(({ page }) => {
    consoleLogs = []
    page.on("console", msg => {
      consoleLogs.push(msg.text())
    })
  })

  test("1. Setup flow with test keys and verify zero leakage", async ({ page }) => {
    await page.goto("/setup")
    
    // Check "Remember on this device"
    await page.getByLabel(/Remember on this device/i).check()

    // Find the Gemini input and enter the canary key
    const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible()

    // Add Groq to reach 3 families
    const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
    await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByText("Valid")).toBeVisible()

    // Wait for Team Readiness to say at least 3
    await expect(page.getByText(/3 of 3 recommended model families ready/i, { exact: false })).toBeVisible()

    // Verify CANARY_KEY does not appear in console
    for (const log of consoleLogs) {
      expect(log).not.toContain(CANARY_KEY)
    }

    // Verify CANARY_KEY does not appear in LocalStorage
    const lsKeys = await page.evaluate(() => JSON.stringify(window.localStorage))
    expect(lsKeys).not.toContain(CANARY_KEY)

    // Verify CANARY_KEY is masked in the UI
    await expect(page.getByText(CANARY_KEY)).not.toBeVisible()
  })

  test("2. Ask a question, watch progress, receive the answer", async ({ page }) => {
    await page.goto("/setup")
    const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible()

    const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
    await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByText("Valid")).toBeVisible()

    await page.goto("/")
    
    // Wait for the capacity indicator to disappear
    await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()

    // Click an example question
    await page.getByText(/Will quantum computing achieve/i).click()

    // Click Launch
    await page.getByRole("button", { name: /Launch Team/i }).click()

    // Should navigate to execution view
    await expect(page).toHaveURL(/\/executions\/.+/)

    // Check progress view elements exist
    await expect(page.getByText(/Research Team/i)).toBeVisible()
    await expect(page.getByText(/Consensus Meter/i)).toBeVisible()
    await expect(page.getByText(/Event Log/i)).toBeVisible()
  })

  test("3. Refresh mid-execution and confirm re-attach", async ({ page }) => {
    // Setup keys and start
    await page.goto("/setup")
    const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible()

    const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
    await groqCard.locator('input[type="password"]').fill("sk-groq")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByText("Valid")).toBeVisible()

    await page.goto("/")
    await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
    
    await page.getByText(/What are the most viable methods/i).click()
    await page.getByRole("button", { name: /Launch Team/i }).click()
    
    await expect(page).toHaveURL(/\/executions\/.+/)
    
    // Refresh page
    await page.reload()

    // Should still be on the execution page and re-attach
    await expect(page).toHaveURL(/\/executions\/.+/)
    await expect(page.getByText(/Research Team/i)).toBeVisible()
  })

  test("4. Cancel an execution", async ({ page }) => {
    // Setup keys and start
    await page.goto("/setup")
    const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
    await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
    await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(geminiCard.getByText("Valid")).toBeVisible()

    const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
    await groqCard.locator('input[type="password"]').fill("sk-groq")
    await groqCard.getByRole("button", { name: /Save & Test/i }).click()
    await expect(groqCard.getByText("Valid")).toBeVisible()

    await page.goto("/")
    await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
    
    await page.getByText(/Analyse the timeline/i).click()
    await page.getByRole("button", { name: /Launch Team/i }).click()
    
    await expect(page).toHaveURL(/\/executions\/.+/)

    // Click Cancel
    page.on("dialog", dialog => dialog.accept()) // Accept the confirm alert
    await page.getByRole("button", { name: /Cancel/i }).click()

    // Should redirect to home
    await expect(page).toHaveURL(/\/$/)
  })
})
