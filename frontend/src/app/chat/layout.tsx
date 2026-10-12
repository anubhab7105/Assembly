import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Run my question",
  description:
    "Ask one hard question, pick 3 to 15 minutes, and get back one answer that survived a debate, with sources.",
  alternates: { canonical: "/chat" },
}
export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return children
}
