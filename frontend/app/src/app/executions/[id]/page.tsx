"use client"

import { useParams } from "next/navigation"

export default function ExecutionPage() {
  const params = useParams()
  
  return (
    <div className="min-h-screen bg-background p-12">
      <h1 className="text-2xl font-bold">Execution Progress</h1>
      <p className="text-muted-foreground mt-4">
        Execution ID: <span className="font-mono bg-muted px-2 py-1 rounded">{params.id}</span>
      </p>
      <p className="mt-8 text-sm text-muted-foreground">
        This is a placeholder page. The useExecution hook is ready to be implemented here.
      </p>
    </div>
  )
}
