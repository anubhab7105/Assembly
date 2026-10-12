import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import rehypeHighlight from "rehype-highlight"

// Regression test for the katex override (frontend/package.json `overrides`).
// The override pins every nested katex copy to the top-level 0.19.0, which is
// OUTSIDE the consumers' declared ^0.16.0 range — so this test proves the
// actual remark-math/rehype-katex pipeline from final-answer.tsx still renders.
const MATH_MD = `Inline $E = mc^2$ and block:

$$
\\int_0^1 x \\, dx = \\frac{1}{2}
$$
`

function MathDoc() {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex, rehypeHighlight]}
    >
      {MATH_MD}
    </ReactMarkdown>
  )
}

describe("math rendering pipeline (remark-math/rehype-katex)", () => {
  it("renders both inline and block math through KaTeX", () => {
    const { container } = render(<MathDoc />)
    const rendered = container.querySelectorAll(".katex")
    // One .katex per formula: inline + block display.
    expect(rendered.length).toBeGreaterThanOrEqual(2)
    // Block math renders inside a display wrapper.
    expect(container.querySelector(".katex-display")).not.toBeNull()
    // No KaTeX parse errors surfaced.
    expect(container.querySelector(".katex-error")).toBeNull()
  })
})
