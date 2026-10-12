import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "My past runs",
  description:
    "Your run history on this device, with sources and confidence levels.",
  alternates: { canonical: "/executions" },
}
export default function ExecutionsLayout({ children }: { children: React.ReactNode }) {
  return children
}
