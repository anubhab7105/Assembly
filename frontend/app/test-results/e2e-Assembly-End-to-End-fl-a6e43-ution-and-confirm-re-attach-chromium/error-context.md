# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e.spec.ts >> Assembly End-to-End flow >> 3. Refresh mid-execution and confirm re-attach
- Location: tests\e2e.spec.ts:69:7

# Error details

```
Error: expect(page).toHaveURL(expected) failed

Expected pattern: /\/executions\/.+/
Received string:  "http://localhost:3000/"
Timeout: 5000ms

Call log:
  - Expect "toHaveURL" with timeout 5000ms
    13 × locator resolved to <html lang="en" class="inter_8db6fa51-module__MMaAbG__variable jetbrains_mono_9a2f2d6c-module__wsyXyG__variable h-full antialiased">…</html>
       - unexpected value "http://localhost:3000/"

```

```yaml
- complementary:
  - link "Assembly":
    - /url: /
  - button "New Investigation"
  - text: History
  - textbox "Search..."
  - link "Will quantum computing achieve commercial advantage before 2030? 10/8/2026 completed":
    - /url: /executions/exec-1
    - paragraph: Will quantum computing achieve commercial advantage before 2030?
    - text: 10/8/2026 completed
    - button "Delete execution"
  - link "Timeline for AGI? 10/7/2026 failed":
    - /url: /executions/exec-2
    - paragraph: Timeline for AGI?
    - text: 10/7/2026 failed
    - button "Delete execution"
  - link "Settings":
    - /url: /settings
- main:
  - main:
    - heading "Assembly" [level=1]
    - paragraph: Turn one question into a temporary team of AI agents that reason, debate, and verify to find the best answer.
    - textbox "What do you want the team to research?": What are the most viable methods for replicating room-temperature superconductors?
    - text: "Mode: Auto"
    - button "3m"
    - button "5m"
    - button "10m"
    - button "15m"
    - text: 3 ready
    - button "Launch Team" [disabled]
    - text: Shift + Enter for new line Enter to send
    - paragraph: Will quantum computing achieve commercial advantage before 2030?
    - paragraph: What are the most viable methods for replicating room-temperature superconductors?
    - paragraph: Analyse the timeline and economic impacts of AGI given current scaling laws.
    - paragraph: Which battery chemistry is most likely to replace Lithium-Ion in EVs by 2035?
- alert
```

# Test source

```ts
  1   | import { test, expect } from "@playwright/test"
  2   | 
  3   | const CANARY_KEY = "sk-CANARY-123456789-TEST-KEY"
  4   | 
  5   | test.describe("Assembly End-to-End flow", () => {
  6   |   let consoleLogs: string[] = []
  7   | 
  8   |   test.beforeEach(({ page }) => {
  9   |     consoleLogs = []
  10  |     page.on("console", msg => {
  11  |       consoleLogs.push(msg.text())
  12  |     })
  13  |   })
  14  | 
  15  |   test("1. Setup flow with test keys and verify zero leakage", async ({ page }) => {
  16  |     await page.goto("/setup")
  17  |     
  18  |     // Check "Remember on this device"
  19  |     await page.getByLabel(/Remember on this device/i).check()
  20  | 
  21  |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  22  |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  23  |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  24  |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  25  | 
  26  |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  27  |     await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
  28  |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  29  |     await expect(groqCard.getByText("Valid")).toBeVisible()
  30  | 
  31  |     await expect(page.getByText(/3 of 3 recommended model families ready/i, { exact: false })).toBeVisible()
  32  | 
  33  |     for (const log of consoleLogs) {
  34  |       expect(log).not.toContain(CANARY_KEY)
  35  |     }
  36  | 
  37  |     const lsKeys = await page.evaluate(() => JSON.stringify(window.localStorage))
  38  |     expect(lsKeys).not.toContain(CANARY_KEY)
  39  | 
  40  |     await expect(page.getByText(CANARY_KEY)).not.toBeVisible()
  41  |   })
  42  | 
  43  |   test("2. Ask a question, watch progress, receive the answer", async ({ page }) => {
  44  |     await page.goto("/setup")
  45  |     await page.getByLabel(/Remember on this device/i).check()
  46  | 
  47  |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  48  |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  49  |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  50  |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  51  | 
  52  |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  53  |     await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
  54  |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  55  |     await expect(groqCard.getByText("Valid")).toBeVisible()
  56  | 
  57  |     await page.getByRole("button", { name: /New Investigation/i }).click()
  58  |     
  59  |     await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
  60  |     await page.getByText(/Will quantum computing achieve/i).click()
  61  |     await page.getByRole("button", { name: /Launch Team/i }).click()
  62  |     await expect(page).toHaveURL(/\/executions\/.+/)
  63  | 
  64  |     await expect(page.getByText(/Research Team/i)).toBeVisible()
  65  |     await expect(page.getByText(/Consensus Meter/i)).toBeVisible()
  66  |     await expect(page.getByText(/Event Log/i)).toBeVisible()
  67  |   })
  68  | 
  69  |   test("3. Refresh mid-execution and confirm re-attach", async ({ page }) => {
  70  |     await page.goto("/setup")
  71  |     await page.getByLabel(/Remember on this device/i).check()
  72  | 
  73  |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  74  |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  75  |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  76  |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  77  | 
  78  |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  79  |     await groqCard.locator('input[type="password"]').fill("sk-groq")
  80  |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  81  |     await expect(groqCard.getByText("Valid")).toBeVisible()
  82  | 
  83  |     await page.getByRole("button", { name: /New Investigation/i }).click()
  84  |     await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
  85  |     
  86  |     await page.getByText(/What are the most viable methods/i).click()
  87  |     await page.getByRole("button", { name: /Launch Team/i }).click()
  88  |     
> 89  |     await expect(page).toHaveURL(/\/executions\/.+/)
      |                        ^ Error: expect(page).toHaveURL(expected) failed
  90  |     await page.reload()
  91  | 
  92  |     await expect(page).toHaveURL(/\/executions\/.+/)
  93  |     await expect(page.getByText(/Research Team/i)).toBeVisible()
  94  |   })
  95  | 
  96  |   test("4. Cancel an execution", async ({ page }) => {
  97  |     await page.goto("/setup")
  98  |     await page.getByLabel(/Remember on this device/i).check()
  99  | 
  100 |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  101 |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  102 |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  103 |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  104 | 
  105 |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  106 |     await groqCard.locator('input[type="password"]').fill("sk-groq")
  107 |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  108 |     await expect(groqCard.getByText("Valid")).toBeVisible()
  109 | 
  110 |     await page.getByRole("button", { name: /New Investigation/i }).click()
  111 |     await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
  112 |     
  113 |     await page.getByText(/Analyse the timeline/i).click()
  114 |     await page.getByRole("button", { name: /Launch Team/i }).click()
  115 |     
  116 |     await expect(page).toHaveURL(/\/executions\/.+/)
  117 | 
  118 |     page.on("dialog", dialog => dialog.accept())
  119 |     await page.getByRole("button", { name: /Cancel/i }).click()
  120 |     await expect(page).toHaveURL(/\/$/)
  121 |   })
  122 | })
  123 | 
```