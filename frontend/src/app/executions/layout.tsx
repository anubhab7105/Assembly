import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Run History",
  description:
    "Review past Assembly runs on this device, with consensus scores, sources and uncertainty notes.",
  alternates: { canonical: "/executions" },
}
export default function ExecutionsLayout({ children }: { children: React.ReactNode }) {
  return children
}
