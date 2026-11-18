import Link from "next/link"
import { ArrowRight, CheckCircle2, Github, Terminal } from "lucide-react"
import { BrandOrbMark } from "@/components/brand-orb-mark"

const requirements = [
  "Python 3.11 or newer",
  "Node.js 20 or newer with npm",
  "Git",
]

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-xl border border-white/10 bg-black/50 p-4 text-sm leading-7 text-[#f5d79b]">
      <code>{children}</code>
    </pre>
  )
}

export default function GetStartedPage() {
  return (
    <main id="main-content" tabIndex={-1} className="min-h-full bg-[#080808] text-[#f4f0e8]">
      <div className="mx-auto max-w-5xl px-5 pb-20 pt-8 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between gap-4 border-b border-white/10 pb-6">
          <Link href="/" aria-label="Assembly home" className="flex items-center gap-2 text-lg font-semibold tracking-tight text-white">
            <BrandOrbMark style={{ width: 32, height: 32 }} />
            <span>Assembly</span>
          </Link>
          <Link href="/" className="text-sm text-white/60 transition hover:text-white">Back to overview</Link>
        </header>

        <section className="py-16 sm:py-20">
          <p className="mb-5 text-xs font-semibold uppercase tracking-[0.24em] text-[#eaa221]">Run it on your machine</p>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">Run Assembly locally.</h1>
          <p className="mt-6 max-w-2xl text-base leading-8 text-white/65 sm:text-lg">
            The hosted website introduces the project. The FastAPI backend and investigation workspace run on your machine; model inference uses the provider APIs for the keys you configure.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <a href="https://github.com/anubhab7105/Assembly" target="_blank" rel="noreferrer noopener" className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#eaa221] px-6 py-3 text-sm font-semibold text-black transition hover:bg-[#f2b94e]">
              <Github className="size-4" /> Open the Assembly repository <ArrowRight className="size-4" />
            </a>
            <a href="#installation" className="inline-flex min-h-12 items-center gap-2 rounded-full border border-white/15 px-6 py-3 text-sm font-semibold text-white transition hover:border-white/35">
              <Terminal className="size-4" /> View installation steps
            </a>
          </div>
        </section>

        <section className="grid gap-8 border-y border-white/10 py-10 sm:grid-cols-[1fr_1.4fr]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#eaa221]">Before you begin</p>
            <h2 className="mt-3 text-2xl font-semibold">Requirements</h2>
            <p className="mt-3 text-sm leading-7 text-white/55">Install these tools before cloning and starting the project.</p>
          </div>
          <ul className="grid gap-3">
            {requirements.map((item) => (
              <li key={item} className="flex items-center gap-3 text-sm text-white/80">
                <CheckCircle2 className="size-4 shrink-0 text-[#eaa221]" /> {item}
              </li>
            ))}
          </ul>
        </section>

        <section id="installation" className="space-y-12 py-12">
          <div className="grid gap-4 sm:grid-cols-[72px_1fr]">
            <span className="text-sm font-semibold tracking-[0.2em] text-[#eaa221]">01</span>
            <div>
              <h2 className="text-2xl font-semibold">Clone the repository</h2>
              <p className="mb-4 mt-2 text-sm leading-7 text-white/60">Open a terminal and clone the public repository.</p>
              <CodeBlock>{`git clone https://github.com/anubhab7105/Assembly.git
cd Assembly`}</CodeBlock>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-[72px_1fr]">
            <span className="text-sm font-semibold tracking-[0.2em] text-[#eaa221]">02</span>
            <div>
              <h2 className="text-2xl font-semibold">Create the Python environment</h2>
              <p className="mb-4 mt-2 text-sm leading-7 text-white/60">Create and activate a virtual environment from the repository root.</p>
              <CodeBlock>{`python -m venv .venv

# Windows PowerShell
.venv\\Scripts\\Activate.ps1

# macOS / Linux
source .venv/bin/activate`}</CodeBlock>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-[72px_1fr]">
            <span className="text-sm font-semibold tracking-[0.2em] text-[#eaa221]">03</span>
            <div>
              <h2 className="text-2xl font-semibold">Install backend dependencies</h2>
              <p className="mb-4 mt-2 text-sm leading-7 text-white/60">Install the application and development requirements.</p>
              <CodeBlock>{`python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt`}</CodeBlock>
              <p className="mb-3 mt-5 text-sm leading-7 text-white/60">Create the local environment file:</p>
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-white/45">Windows PowerShell</p>
              <CodeBlock>{"Copy-Item .env.example .env"}</CodeBlock>
              <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-white/45">macOS / Linux</p>
              <CodeBlock>{"cp .env.example .env"}</CodeBlock>
              <p className="mt-4 text-sm leading-7 text-white/55">Generate a fresh quota salt with <code className="rounded bg-white/10 px-1.5 py-0.5 text-[#f5d79b]">python -c &quot;import secrets; print(secrets.token_hex(32))&quot;</code> and place it in <code className="rounded bg-white/10 px-1.5 py-0.5 text-[#f5d79b]">QUOTA_SALT</code> inside <code className="rounded bg-white/10 px-1.5 py-0.5 text-[#f5d79b]">.env</code>. Never commit this file.</p>
              <p className="mb-3 mt-5 text-sm leading-7 text-white/60">Apply the local database migrations:</p>
              <CodeBlock>{"alembic upgrade head"}</CodeBlock>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-[72px_1fr]">
            <span className="text-sm font-semibold tracking-[0.2em] text-[#eaa221]">04</span>
            <div>
              <h2 className="text-2xl font-semibold">Install frontend dependencies</h2>
              <p className="mb-4 mt-2 text-sm leading-7 text-white/60">From the repository root, install the frontend packages.</p>
              <CodeBlock>{`cd frontend
npm ci --legacy-peer-deps
cd ..`}</CodeBlock>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-[72px_1fr]">
            <span className="text-sm font-semibold tracking-[0.2em] text-[#eaa221]">05</span>
            <div>
              <h2 className="text-2xl font-semibold">Start Assembly</h2>
              <p className="mb-4 mt-2 text-sm leading-7 text-white/60">Run the local launcher from the repository root. It starts FastAPI and the Next.js frontend together, checks that both are ready, and opens the chat workspace in your browser.</p>
              <CodeBlock>{"python scripts/dev_web.py"}</CodeBlock>
              <div className="mt-5 rounded-xl border border-[#eaa221]/25 bg-[#eaa221]/[0.07] p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#eaa221]">Workspace URL</p>
                <p className="mt-2 text-lg font-semibold text-white">http://127.0.0.1:3000/chat</p>
                <p className="mt-2 text-sm leading-6 text-white/55">Keep the terminal open while using Assembly. Press Ctrl+C there to stop both local services.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="border-t border-white/10 pt-8">
          <h2 className="text-2xl font-semibold">Connect your model providers</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-white/60">Once the local workspace opens, use Settings to add your own provider API keys. Assembly uses bring-your-own-key access; keep keys private and never paste them into source files, issues, or screenshots.</p>
          <p className="mt-5 text-sm text-white/45">Need more detail? The repository README and contributor guide contain the full development and testing instructions.</p>
          <Link href="/chat" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-[#eaa221] hover:text-[#f2b94e]">Open the local chat page <ArrowRight className="size-4" /></Link>
        </section>
      </div>
    </main>
  )
}
