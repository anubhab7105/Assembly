import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import { ModelPicker } from "./model-picker"
import { ApiClient } from "@/lib/api-client"

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>()
  return {
    ...actual,
    ApiClient: {
      ...actual.ApiClient,
      catalog: vi.fn(),
    },
  }
})

const catalog = {
  providers: [
    {
      id: "groq",
      enabled: true,
      models: [
        { id: "gpt-oss-20b", family: "gpt-oss", roles: ["solver"] },
        { id: "qwen-27b", family: "qwen", roles: ["solver"] },
      ],
    },
    {
      id: "openrouter",
      enabled: true,
      models: [{ id: "gemma-free", family: "gemma", roles: ["solver"] }],
    },
    {
      id: "cerebras",
      enabled: false,
      models: [{ id: "cereb-llama", family: "llama", roles: ["solver"] }],
    },
  ],
}

describe("ModelPicker family counting", () => {
  beforeEach(() => {
    vi.mocked(ApiClient.catalog).mockResolvedValue(catalog as never)
  })

  it("counts only keyed providers (keyless catalog entries do not inflate coverage)", async () => {
    render(
      <ModelPicker
        value={{ selected: [], pins: {} }}
        onChange={() => {}}
        keyedProviderIds={["groq"]}
      />,
    )
    expect((await screen.findByTestId("picker-gate-chip")).textContent).toContain(
      "2 families ready",
    )
  })

  it("shows BLOCKED with no keys instead of promising catalog families", async () => {
    render(
      <ModelPicker value={{ selected: [], pins: {} }} onChange={() => {}} keyedProviderIds={[]} />,
    )
    expect((await screen.findByTestId("picker-gate-chip")).textContent).toContain(
      "0 families ready",
    )
  })
})
