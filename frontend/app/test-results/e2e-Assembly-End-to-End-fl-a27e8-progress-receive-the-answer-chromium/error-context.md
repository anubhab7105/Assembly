# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e.spec.ts >> Assembly End-to-End flow >> 2. Ask a question, watch progress, receive the answer
- Location: tests\e2e.spec.ts:43:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: /Launch Team/i })

```

# Page snapshot

```yaml
- generic [ref=e1]:
  - generic [ref=e2]:
    - complementary [ref=e3]:
      - generic [ref=e4]:
        - generic [ref=e5]:
          - link "Assembly" [ref=e6] [cursor=pointer]:
            - /url: /
          - button "New Investigation" [ref=e11]
        - generic [ref=e12]:
          - generic [ref=e13]: History
          - textbox "Search..." [ref=e23]
          - link "Will quantum computing achieve commercial advantage before 2030? 10/8/2026 completed" [active] [ref=e24] [cursor=pointer]:
            - /url: /executions/exec-1
            - generic [ref=e27]:
              - paragraph [ref=e28]: Will quantum computing achieve commercial advantage before 2030?
              - generic [ref=e29]:
                - generic [ref=e30]: 10/8/2026
                - generic [ref=e31]: completed
            - button "Delete execution" [ref=e32]
          - link "Timeline for AGI? 10/7/2026 failed" [ref=e36] [cursor=pointer]:
            - /url: /executions/exec-2
            - generic [ref=e39]:
              - paragraph [ref=e40]: Timeline for AGI?
              - generic [ref=e41]:
                - generic [ref=e42]: 10/7/2026
                - generic [ref=e43]: failed
            - button "Delete execution" [ref=e44]
        - link "Settings" [ref=e49] [cursor=pointer]:
          - /url: /settings
    - main [ref=e54]:
      - generic [ref=e55]:
        - generic [ref=e56]: WebSocket failed. Polling for updates...
        - generic [ref=e65]:
          - generic [ref=e70]:
            - heading "Research Team" [level=1] [ref=e71]
            - paragraph [ref=e72]: "ID: exec-1"
          - generic [ref=e73]:
            - generic [ref=e74]:
              - generic [ref=e75]: Time Remaining
              - generic [ref=e76]: "--:--"
            - button "Cancel" [ref=e80]
        - main [ref=e81]:
          - generic [ref=e82]:
            - generic [ref=e83]:
              - generic [ref=e84]: Consensus Meter
              - generic [ref=e91]: Awaiting first debate round...
            - generic [ref=e97]:
              - generic [ref=e98]: Active Team (0)
              - generic [ref=e106]: Forming temporary team...
          - generic [ref=e108]:
            - generic [ref=e109]:
              - generic [ref=e110]: Cross-Examinations
              - generic [ref=e114]: No conflicts detected yet.
            - generic [ref=e117]:
              - generic [ref=e118]: Verified Sources
              - generic [ref=e123]: No external sources cited yet.
          - generic [ref=e126]:
            - generic [ref=e127]: Event Log
            - generic [ref=e131]: Awaiting events...
  - generic "Notifications"
  - generic [ref=e138] [cursor=pointer]:
    - button "Open Next.js Dev Tools" [ref=e139]
    - generic [ref=e143]:
      - button "Open issues overlay" [ref=e144]:
        - generic [ref=e145]:
          - generic [aria-hidden] [ref=e146]: "1"
          - generic [ref=e147]: "2"
        - generic [ref=e148]:
          - text: Issue
          - generic [aria-hidden] [ref=e149]: s
      - button "Collapse issues badge" [ref=e150]
  - alert [ref=e153]: Research Team
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
> 61  |     await page.getByRole("button", { name: /Launch Team/i }).click()
      |                                                              ^ Error: locator.click: Test timeout of 30000ms exceeded.
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
  89  |     await expect(page).toHaveURL(/\/executions\/.+/)
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