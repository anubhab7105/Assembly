import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Setup API Keys",
  description:
    "Add your free Gemini, Groq, OpenRouter and Hugging Face keys (BYOK). Keys stay in your browser; nothing is stored on the server.",
  alternates: { canonical: "/settings" },
}
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return children
}
