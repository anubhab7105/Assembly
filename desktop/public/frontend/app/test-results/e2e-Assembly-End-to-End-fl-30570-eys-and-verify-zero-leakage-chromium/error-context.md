# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e.spec.ts >> Assembly End-to-End flow >> 1. Setup flow with test keys and verify zero leakage
- Location: tests\e2e.spec.ts:42:7

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText(/3 of 3 recommended model families ready/i)
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByText(/3 of 3 recommended model families ready/i) with timeout 5000ms
  - waiting for getByText(/3 of 3 recommended model families ready/i)

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
  - heading "Initial Setup" [level=1]
  - paragraph: Configure your Bring-Your-Own-Key (BYOK) providers. Assembly requires at least 3 model families for effective debate.
  - main:
    - text: Team Readiness 0 of 3 recommended model families ready. Action Required No keys configured yet.
    - checkbox "Remember on this device Encrypts keys using WebCrypto and stores in browser DB. Turn off for pure in-memory (safest)." [checked]
    - text: Remember on this device Encrypts keys using WebCrypto and stores in browser DB. Turn off for pure in-memory (safest).
    - button "Clear all keys"
    - text: Google Gemini Invalid Complex reasoning, massive context windows (up to 2M tokens), and fast generation. API Key
    - link "Get free key":
      - /url: https://aistudio.google.com/app/apikey
    - textbox "sk-C••••••••-KEY"
    - paragraph: Free tiers may use inputs to improve models. Keys never leave this device except to authenticate.
    - button "Test Saved Key"
    - text: Groq Invalid Lightning-fast inference (LPU), great for real-time debate and rapid drafting. API Key
    - link "Get free key":
      - /url: https://console.groq.com/keys
    - textbox "sk-g••••••••ummy"
    - paragraph: Free tiers may use inputs to improve models. Keys never leave this device except to authenticate.
    - button "Test Saved Key"
    - text: Cerebras Extreme speed on LLaMA models, ideal for rapid-fire cross-examination. API Key
    - link "Get free key":
      - /url: https://cloud.cerebras.ai/
    - textbox "sk-..."
    - paragraph: Free tiers may use inputs to improve models. Keys never leave this device except to authenticate.
    - button "Test Saved Key" [disabled]
    - text: OpenRouter Access to dozens of free-tier models; provides excellent model diversity. API Key
    - link "Get free key":
      - /url: https://openrouter.ai/keys
    - textbox "sk-..."
    - paragraph: Free tiers may use inputs to improve models. Keys never leave this device except to authenticate.
    - button "Test Saved Key" [disabled]
    - text: Mistral Strong reasoning capabilities, good for critical analysis and verification. API Key
    - link "Get free key":
      - /url: https://console.mistral.ai/api-keys/
    - textbox "sk-..."
    - paragraph: Free tiers may use inputs to improve models. Keys never leave this device except to authenticate.
    - button "Test Saved Key" [disabled]
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
  8   |   test.beforeEach(async ({ page }) => {
  9   |     consoleLogs = []
  10  |     page.on("console", msg => {
  11  |       consoleLogs.push(msg.text())
  12  |     })
  13  | 
  14  |     // Mock Backend API
  15  |     await page.route("**/api/providers/*/test", async route => {
  16  |       await route.fulfill({ json: { status: "valid" } })
  17  |     })
  18  |     await page.route("**/api/executions/preflight", async route => {
  19  |       await route.fulfill({ json: { feasible: true } })
  20  |     })
  21  |     await page.route("**/api/executions", async (route, request) => {
  22  |       if (request.method() === "POST") {
  23  |         await route.fulfill({ json: { id: "exec-test", status: "running" } })
  24  |       } else {
  25  |         await route.fulfill({ json: [] })
  26  |       }
  27  |     })
  28  |     await page.route("**/api/executions/*/cancel", async route => {
  29  |       await route.fulfill({ json: { status: "cancelled" } })
  30  |     })
  31  |     await page.route("**/api/executions/*/events*", async route => {
  32  |       await route.fulfill({ json: [
  33  |         { 
  34  |           event_type: "team.ready", 
  35  |           seq: 1,
  36  |           data: { agents: [{ id: "1", role: "Researcher", model_family: "gemini" }] } 
  37  |         }
  38  |       ]})
  39  |     })
  40  |   })
  41  | 
  42  |   test("1. Setup flow with test keys and verify zero leakage", async ({ page }) => {
  43  |     await page.goto("/setup")
  44  |     
  45  |     // Check "Remember on this device"
  46  |     await page.getByLabel(/Remember on this device/i).check()
  47  | 
  48  |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  49  |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  50  |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  51  |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  52  | 
  53  |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  54  |     await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
  55  |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  56  |     await expect(groqCard.getByText("Valid")).toBeVisible()
  57  | 
> 58  |     await expect(page.getByText(/3 of 3 recommended model families ready/i, { exact: false })).toBeVisible()
      |                                                                                                ^ Error: expect(locator).toBeVisible() failed
  59  | 
  60  |     for (const log of consoleLogs) {
  61  |       expect(log).not.toContain(CANARY_KEY)
  62  |     }
  63  | 
  64  |     const lsKeys = await page.evaluate(() => JSON.stringify(window.localStorage))
  65  |     expect(lsKeys).not.toContain(CANARY_KEY)
  66  | 
  67  |     await expect(page.getByText(CANARY_KEY)).not.toBeVisible()
  68  |   })
  69  | 
  70  |   test("2. Ask a question, watch progress, receive the answer", async ({ page }) => {
  71  |     await page.goto("/setup")
  72  |     await page.getByLabel(/Remember on this device/i).check()
  73  | 
  74  |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  75  |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  76  |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  77  |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  78  | 
  79  |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  80  |     await groqCard.locator('input[type="password"]').fill("sk-groq-dummy")
  81  |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  82  |     await expect(groqCard.getByText("Valid")).toBeVisible()
  83  | 
  84  |     await page.getByRole("button", { name: /New Investigation/i }).click()
  85  |     
  86  |     await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
  87  |     await page.getByText(/Will quantum computing achieve/i).click()
  88  |     await page.getByRole("button", { name: /Launch Team/i }).click()
  89  |     await expect(page).toHaveURL(/\/executions\/.+/)
  90  | 
  91  |     await expect(page.getByText(/Research Team/i)).toBeVisible()
  92  |     await expect(page.getByText(/Consensus Meter/i)).toBeVisible()
  93  |     await expect(page.getByText(/Event Log/i)).toBeVisible()
  94  |   })
  95  | 
  96  |   test("3. Refresh mid-execution and confirm re-attach", async ({ page }) => {
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
  113 |     await page.getByText(/What are the most viable methods/i).click()
  114 |     await page.getByRole("button", { name: /Launch Team/i }).click()
  115 |     
  116 |     await expect(page).toHaveURL(/\/executions\/.+/)
  117 |     await page.reload()
  118 | 
  119 |     await expect(page).toHaveURL(/\/executions\/.+/)
  120 |     await expect(page.getByText(/Research Team/i)).toBeVisible()
  121 |   })
  122 | 
  123 |   test("4. Cancel an execution", async ({ page }) => {
  124 |     await page.goto("/setup")
  125 |     await page.getByLabel(/Remember on this device/i).check()
  126 | 
  127 |     const geminiCard = page.locator(".bg-card").filter({ hasText: "Google Gemini" })
  128 |     await geminiCard.locator('input[type="password"]').fill(CANARY_KEY)
  129 |     await geminiCard.getByRole("button", { name: /Save & Test/i }).click()
  130 |     await expect(geminiCard.getByText("Valid")).toBeVisible()
  131 | 
  132 |     const groqCard = page.locator(".bg-card").filter({ hasText: "Groq" })
  133 |     await groqCard.locator('input[type="password"]').fill("sk-groq")
  134 |     await groqCard.getByRole("button", { name: /Save & Test/i }).click()
  135 |     await expect(groqCard.getByText("Valid")).toBeVisible()
  136 | 
  137 |     await page.getByRole("button", { name: /New Investigation/i }).click()
  138 |     await expect(page.getByText(/Insufficient Model Diversity/i)).not.toBeVisible()
  139 |     
  140 |     await page.getByText(/Analyse the timeline/i).click()
  141 |     await page.getByRole("button", { name: /Launch Team/i }).click()
  142 |     
  143 |     await expect(page).toHaveURL(/\/executions\/.+/)
  144 | 
  145 |     page.on("dialog", dialog => dialog.accept())
  146 |     await page.getByRole("button", { name: /Cancel/i }).click()
  147 |     await expect(page).toHaveURL(/\/$/)
  148 |   })
  149 | })
  150 | 
```