import { chromium } from "playwright"

const BASE = "http://localhost:3100"

const widths = [390, 430, 720, 820, 1024, 1440]
const routes = ["/", "/chat", "/history", "/executions?id=local-visual-1", "/models", "/settings"]

const browser = await chromium.launch({ headless: true })
for (const width of widths) {
  const context = await browser.newContext({ viewport: { width, height: width < 500 ? 844 : 1000 } })
  const page = await context.newPage()
  for (const route of routes) {
    await page.goto(`${BASE}${route}`, { waitUntil: "load" })
    await page.waitForTimeout(400)
    const m = await page.evaluate(() => {
      const rect = (sel) => {
        const el = document.querySelector(sel)
        if (!el) return null
        const r = el.getBoundingClientRect()
        return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), right: Math.round(r.right), bottom: Math.round(r.bottom) }
      }
      return {
        scrollW: document.documentElement.scrollWidth,
        innerW: window.innerWidth,
        bodyScrollW: document.body.scrollWidth,
        topbar: rect(".cin-topbar"),
        actions: rect(".cin-topbar-actions"),
        nav: rect(".cin-bottom-nav"),
        hero: rect(".cin-hero"),
        stage: rect(".cin-hero-stage"),
        live: rect(".cin-float-window.is-live"),
        agreement: rect(".cin-float-window.is-agreement"),
        answer: rect(".cin-float-window.is-answer"),
        page: rect(".cin-page"),
        main: rect("#main-content"),
      }
    })
    console.log(width, route, JSON.stringify(m))
  }
  await context.close()
}
await browser.close()
