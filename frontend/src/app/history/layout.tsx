import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Run history",
  description: "Past Assembly investigations saved on this device, with agreement, budget, and status.",
  alternates: { canonical: "/history" },
}
export default function HistoryLayout({ children }: { children: React.ReactNode }) {
  return children
}
