import Link from "next/link"

export default function NotFound() {
  return (
    <div className="asm-page flex min-h-screen flex-col items-center justify-center px-6 py-16 text-center">
      <p className="asm-index">[ 404 / Not found ]</p>
      <h1 className="mt-6 max-w-3xl text-5xl font-extrabold uppercase leading-[0.94] tracking-[-0.05em] sm:text-6xl">
        That page does not exist
      </h1>
      <p className="mt-5 max-w-md text-sm leading-relaxed text-muted-foreground">
        Wrong turn. Your next verified answer is one click away.
      </p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Link href="/chat" className="asm-btn asm-btn-primary asm-btn-lg">
          Run my first question
        </Link>
        <Link href="/" className="asm-btn asm-btn-outline asm-btn-lg">
          Back to home
        </Link>
        <Link href="/settings" className="asm-btn asm-btn-outline asm-btn-lg">
          Add my free keys
        </Link>
      </div>
    </div>
  )
}
