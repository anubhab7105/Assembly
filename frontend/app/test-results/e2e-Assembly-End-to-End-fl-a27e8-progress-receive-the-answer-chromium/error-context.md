# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e.spec.ts >> Assembly End-to-End flow >> 2. Ask a question, watch progress, receive the answer
- Location: tests\e2e.spec.ts:49:7

# Error details

```
Error: locator.click: Error: strict mode violation: getByText(/Will quantum computing achieve/i) resolved to 2 elements:
    1) <p class="truncate text-xs font-medium">Will quantum computing achieve commercial advanta…</p> aka getByRole('link', { name: 'Will quantum computing' })
    2) <p class="text-sm text-muted-foreground">Will quantum computing achieve commercial advanta…</p> aka getByText('Will quantum computing').nth(1)

Call log:
  - waiting for getByText(/Will quantum computing achieve/i)

```

# Page snapshot

```yaml
- generic [active] [ref=f1e1]:
  - generic [ref=f1e2]:
    - complementary [ref=f1e3]:
      - generic [ref=f1e4]:
        - generic [ref=f1e5]:
          - link "Assembly" [ref=f1e6] [cursor=pointer]:
            - /url: /
          - button "New Investigation" [ref=f1e11]
        - generic [ref=f1e12]:
          - generic [ref=f1e13]: History
          - textbox "Search..." [ref=f1e23]
          - link "Will quantum computing achieve commercial advantage before 2030? 10/8/2026 completed" [ref=f1e24] [cursor=pointer]:
            - /url: /executions/exec-1
            - generic [ref=f1e27]:
              - paragraph [ref=f1e28]: Will quantum computing achieve commercial advantage before 2030?
              - generic [ref=f1e29]:
                - generic [ref=f1e30]: 10/8/2026
                - generic [ref=f1e31]: completed
            - button "Delete execution" [ref=f1e32]
          - link "Timeline for AGI? 10/7/2026 failed" [ref=f1e36] [cursor=pointer]:
            - /url: /executions/exec-2
            - generic [ref=f1e39]:
              - paragraph [ref=f1e40]: Timeline for AGI?
              - generic [ref=f1e41]:
                - generic [ref=f1e42]: 10/7/2026
                - generic [ref=f1e43]: failed
            - button "Delete execution" [ref=f1e44]
        - link "Settings" [ref=f1e49] [cursor=pointer]:
          - /url: /settings
    - main [ref=f1e54]:
      - main [ref=f1e56]:
        - generic [ref=f1e57]:
          - heading "Assembly" [level=1] [ref=f1e61]
          - paragraph [ref=f1e62]: Turn one question into a temporary team of AI agents that reason, debate, and verify to find the best answer.
        - generic [ref=f1e63]:
          - generic [ref=f1e67]:
            - paragraph [ref=f1e68]: Insufficient Model Diversity
            - paragraph [ref=f1e69]: Assembly requires at least 2 distinct model families to function.
          - button "Configure Keys" [ref=f1e70]
        - generic [ref=f1e71]:
          - generic [ref=f1e72]:
            - textbox "What do you want the team to research?" [ref=f1e73]
            - generic [ref=f1e74]:
              - generic [ref=f1e75]:
                - generic [ref=f1e76]: "Mode: Auto"
                - generic [ref=f1e77]:
                  - button "3m" [ref=f1e81]
                  - button "5m" [ref=f1e82]
                  - button "10m" [ref=f1e83]
                  - button "15m" [ref=f1e84]
                - generic "0 families configured" [ref=f1e85] [cursor=pointer]: 0 ready
              - button "Launch Team" [disabled]
          - generic [ref=f1e87]:
            - generic [ref=f1e88]: Shift + Enter for new line
            - generic [ref=f1e89]: Enter to send
        - generic [ref=f1e90]:
          - paragraph [ref=f1e96] [cursor=pointer]: Will quantum computing achieve commercial advantage before 2030?
          - paragraph [ref=f1e102] [cursor=pointer]: What are the most viable methods for replicating room-temperature superconductors?
          - paragraph [ref=f1e108] [cursor=pointer]: Analyse the timeline and economic impacts of AGI given current scaling laws.
          - paragraph [ref=f1e114] [cursor=pointer]: Which battery chemistry is most likely to replace Lithium-Ion in EVs by 2035?
  - generic "Notifications"
  - button "Open Next.js Dev Tools" [ref=f1e120] [cursor=pointer]
  - alert [ref=f1e124]
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
  21  |     // Find the Gemini input and enter the canary key
  22  |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  23  |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  24  |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  25  |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  26  | 
  27  |     // Add Groq to reach 3 families
  28  |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  29  |     await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
  30  |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  31  |     await expect(groqCard.getByText("Valid")).toBeVisible()
  32  | 
  33  |     // Wait for Team Readiness to say at least 3
  34  |     await expect(page.getByText(/3 of 3 recommended model families ready/i, { exact: false })).toBeVisible()
  35  | 
  36  |     // Verify CANARY_KEY does not appear in console
  37  |     for (const log of consoleLogs) {
  38  |       expect(log).not.toContain(CANARY_KEY)
  39  |     }
  40  | 
  41  |     // Verify CANARY_KEY does not appear in LocalStorage
  42  |     const lsKeys = await page.evaluate(() => JSON.stringify(window.localStorage))
  43  |     expect(lsKeys).not.toContain(CANARY_KEY)
  44  | 
  45  |     // Verify CANARY_KEY is masked in the UI
  46  |     await expect(page.getByText(CANARY_KEY)).not.toBeVisible()
  47  |   })
  48  | 
  49  |   test("2. Ask a question, watch progress, receive the answer", async ({ page }) => {
  50  |     await page.goto("/setup")
  51  |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  52  |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  53  |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  54  |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  55  | 
  56  |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  57  |     await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
  58  |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  59  |     await expect(groqCard.getByText("Valid")).toBeVisible()
  60  | 
  61  |     await page.goto("/")
  62  |     
  63  |     // Wait for the capacity indicator to disappear
  64  |     await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
  65  | 
  66  |     // Click an example question
> 67  |     await page.getByText(/Will quantum computing achieve/i).click()
      |                                                             ^ Error: locator.click: Error: strict mode violation: getByText(/Will quantum computing achieve/i) resolved to 2 elements:
  68  | 
  69  |     // Click Launch
  70  |     await page.getByRole("button", { name: /Launch Team/i }).click()
  71  | 
  72  |     // Should navigate to execution view
  73  |     await expect(page).toHaveURL(/\/executions\/.+/)
  74  | 
  75  |     // Check progress view elements exist
  76  |     await expect(page.getByText(/Research Team/i)).toBeVisible()
  77  |     await expect(page.getByText(/Consensus Meter/i)).toBeVisible()
  78  |     await expect(page.getByText(/Event Log/i)).toBeVisible()
  79  |   })
  80  | 
  81  |   test("3. Refresh mid-execution and confirm re-attach", async ({ page }) => {
  82  |     // Setup keys and start
  83  |     await page.goto("/setup")
  84  |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  85  |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  86  |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  87  |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  88  | 
  89  |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  90  |     await groqCard.locator('input[type="password"]').fill("sk-groq")
  91  |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  92  |     await expect(groqCard.getByText("Valid")).toBeVisible()
  93  | 
  94  |     await page.goto("/")
  95  |     await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
  96  |     
  97  |     await page.getByText(/What are the most viable methods/i).click()
  98  |     await page.getByRole("button", { name: /Launch Team/i }).click()
  99  |     
  100 |     await expect(page).toHaveURL(/\/executions\/.+/)
  101 |     
  102 |     // Refresh page
  103 |     await page.reload()
  104 | 
  105 |     // Should still be on the execution page and re-attach
  106 |     await expect(page).toHaveURL(/\/executions\/.+/)
  107 |     await expect(page.getByText(/Research Team/i)).toBeVisible()
  108 |   })
  109 | 
  110 |   test("4. Cancel an execution", async ({ page }) => {
  111 |     // Setup keys and start
  112 |     await page.goto("/setup")
  113 |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  114 |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  115 |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  116 |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  117 | 
  118 |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  119 |     await groqCard.locator('input[type="password"]').fill("sk-groq")
  120 |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  121 |     await expect(groqCard.getByText("Valid")).toBeVisible()
  122 | 
  123 |     await page.goto("/")
  124 |     await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
  125 |     
  126 |     await page.getByText(/Analyse the timeline/i).click()
  127 |     await page.getByRole("button", { name: /Launch Team/i }).click()
  128 |     
  129 |     await expect(page).toHaveURL(/\/executions\/.+/)
  130 | 
  131 |     // Click Cancel
  132 |     page.on("dialog", dialog => dialog.accept()) // Accept the confirm alert
  133 |     await page.getByRole("button", { name: /Cancel/i }).click()
  134 | 
  135 |     // Should redirect to home
  136 |     await expect(page).toHaveURL(/\/$/)
  137 |   })
  138 | })
  139 | 
```