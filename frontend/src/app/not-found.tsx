import Link from "next/link"

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 py-16 text-center">
      <p className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        404
      </p>
      <h1 className="mt-4 text-4xl font-bold tracking-tight">
        That page does not exist
      </h1>
      <p className="mt-4 max-w-md text-muted-foreground">
        Wrong turn. Your next verified answer is one click away.
      </p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Link
          href="/chat"
          className="inline-flex h-11 items-center rounded-xl bg-brand px-6 font-semibold text-brand-foreground"
        >
          Run my first question
        </Link>
        <Link
          href="/"
          className="inline-flex h-11 items-center rounded-xl border border-border bg-card px-6 font-semibold"
        >
          Back to home
        </Link>
        <Link
          href="/settings"
          className="inline-flex h-11 items-center rounded-xl border border-border bg-card px-6 font-semibold"
        >
          Add my free keys
        </Link>
      </div>
    </div>
  )
}
