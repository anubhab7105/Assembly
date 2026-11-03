import { Clock } from "lucide-react"
import { getExecutionTiming } from "@/lib/execution-timing"

interface ExecutionTimingProps {
  status: string
  remainingSeconds: number | null
  elapsedSeconds: number | null
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}:${remainder.toString().padStart(2, "0")}`
}

export function ExecutionTiming({
  status,
  remainingSeconds,
  elapsedSeconds,
}: ExecutionTimingProps) {
  const timing = getExecutionTiming(status, remainingSeconds, elapsedSeconds)

  return (
    <div className="flex flex-col items-end">
      <span
        data-testid="execution-timing-label"
        className="text-[10px] font-bold tracking-widest text-muted-foreground uppercase"
      >
        {timing.label}
      </span>
      <div className="flex items-center gap-1.5 font-mono text-2xl font-semibold tracking-tight text-foreground tabular-nums">
        <Clock className="size-5 text-brand" />
        {timing.seconds === null
          ? "Unavailable"
          : formatTime(Math.round(timing.seconds))}
      </div>
    </div>
  )
}
