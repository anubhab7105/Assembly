import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Add my free keys",
  description:
    "Paste free keys from two providers. Keys stay in your browser. No account, no card.",
  alternates: { canonical: "/settings" },
}
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return children
}
