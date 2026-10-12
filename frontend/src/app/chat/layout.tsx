import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Ask a Question",
  description:
    "Ask one hard question, pick a 3–15 minute budget, and run a temporary team of AI agents that cross-examine and verify before answering.",
  alternates: { canonical: "/chat" },
}
export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return children
}
