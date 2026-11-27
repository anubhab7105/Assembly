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
      limits_ready: true,
      models: [
        { id: "gpt-oss-20b", family: "gpt-oss", roles: ["solver", "critic"] },
        { id: "qwen-27b", family: "qwen", roles: ["solver", "critic"] },
      ],
    },
    {
      id: "openrouter",
      enabled: true,
      limits_ready: true,
      models: [{ id: "gemma-free", family: "gemma", roles: ["solver", "critic"] }],
    },
    {
      id: "cerebras",
      enabled: false,
      limits_ready: false,
      models: [{ id: "cereb-llama", family: "llama", roles: ["solver", "critic"] }],
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
    expect((screen.getByRole("checkbox", { name: /gemma-free/ }) as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByRole("checkbox", { name: /cereb-llama/ }) as HTMLInputElement).disabled).toBe(true)
    const pinSelect = screen.getByRole("combobox", { name: "Pin model" })
    expect(Array.from((pinSelect as HTMLSelectElement).options).map((option) => option.value)).toEqual([
      "", "gpt-oss-20b", "qwen-27b",
    ])
  })

  it("shows BLOCKED with no keys instead of promising catalog families", async () => {
    render(
      <ModelPicker value={{ selected: [], pins: {} }} onChange={() => {}} keyedProviderIds={[]} />,
    )
    expect((await screen.findByTestId("picker-gate-chip")).textContent).toContain(
      "0 families ready",
    )
    expect((screen.getByRole("checkbox", { name: /gpt-oss-20b/ }) as HTMLInputElement).disabled).toBe(true)
  })
})
