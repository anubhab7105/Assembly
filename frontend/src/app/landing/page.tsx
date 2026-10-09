"use client"

import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Zap } from "lucide-react"

export default function LandingPage() {
  const router = useRouter()

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6">
      <main className="flex flex-col items-center gap-8 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand/10 text-brand">
          <Zap className="size-8" />
        </div>
        <h1 className="text-5xl font-bold tracking-tight text-foreground">
          Assembly
        </h1>
        <Button size="lg" onClick={() => router.push("/")}>
          Go to Chat
        </Button>
      </main>
    </div>
  )
}
