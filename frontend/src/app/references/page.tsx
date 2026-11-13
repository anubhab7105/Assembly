import Link from "next/link"
import { BrandMark } from "@/components/cinematic/brand-mark"
import { ThemeToggle } from "@/components/theme-toggle"

const REFERENCES: Array<{
  title: string
  authors: string
  venue: string
  href: string
  type: "Journal article" | "Conference paper" | "Preprint"
}> = [
  {
    title: "Orchestration logics for artificial intelligence platforms: From raw data to industry-specific applications",
    authors: "Weber, M., Hein, A., Weking, J., & Krcmar, H.",
    venue: "Information Systems Journal, 35(3), 1015–1043 (2025)",
    href: "https://doi.org/10.1111/isj.12567",
    type: "Journal article",
  },
  {
    title: "Hybrid orchestration of AI services and microservices in cloud-edge collaboration",
    authors: "Peng, K., Liu, X., Han, D., Hu, Y., Hu, M., Cai, C., & Xiong, Z.",
    venue: "IEEE Transactions on Mobile Computing, 25(7), 9382–9400 (2026)",
    href: "https://doi.org/10.1109/TMC.2026.3654236",
    type: "Journal article",
  },
  {
    title: "Multi-agent collaboration via evolving orchestration",
    authors: "Dang, Y., Qian, C., Luo, X., Fan, J., Xie, Z., Shi, R., Chen, W., Yang, C., Che, X., Tian, Y., Xiong, X., Han, L., Liu, Z., & Sun, M.",
    venue: "Advances in Neural Information Processing Systems 38 (NeurIPS 2025), pp. 182975–183009",
    href: "https://doi.org/10.52202/085713-5502",
    type: "Conference paper",
  },
  {
    title: "AgentVerse: Facilitating multi-agent collaboration and exploring emergent behaviors",
    authors: "Chen, W., Su, Y., Zuo, J., Yang, C., Yuan, C., Chan, C.-M., Yu, H., Lu, Y., Hung, Y.-H., Qian, C., Qin, Y., Cong, X., Xie, R., Liu, Z., Sun, M., & Zhou, J.",
    venue: "arXiv:2308.10848 (2023)",
    href: "https://doi.org/10.48550/arXiv.2308.10848",
    type: "Preprint",
  },
  {
    title: "AutoGen: Enabling next-gen LLM applications via multi-agent conversation",
    authors: "Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., Jiang, L., Zhang, X., Zhang, S., Liu, J., Awadallah, A. H., White, R. W., Burger, D., & Wang, C.",
    venue: "arXiv:2308.08155 (2023)",
    href: "https://doi.org/10.48550/arXiv.2308.08155",
    type: "Preprint",
  },
  {
    title: "MetaGPT: Meta programming for a multi-agent collaborative framework",
    authors: "Hong, S., Zhuge, M., Chen, J., Zheng, X., Cheng, Y., Zhang, C., Wang, J., Wang, Z., Yau, S. K. S., Lin, Z., Zhou, L., Ran, C., Xiao, L., Wu, C., & Schmidhuber, J.",
    venue: "arXiv:2308.00352 (2023)",
    href: "https://doi.org/10.48550/arXiv.2308.00352",
    type: "Preprint",
  },
]

const GROUPS: Array<{
  kicker: string
  title: string
  description: string
  types: Array<(typeof REFERENCES)[number]["type"]>
}> = [
  {
    kicker: "Journal articles",
    title: "Peer-reviewed work.",
    description: "Studies on platform orchestration logics and on orchestrating AI services alongside microservices.",
    types: ["Journal article"],
  },
  {
    kicker: "Conference proceedings",
    title: "Presented and published.",
    description: "Peer-reviewed conference research on coordinating many agents as a task grows.",
    types: ["Conference paper"],
  },
  {
    kicker: "Preprints",
    title: "Foundational frameworks.",
    description: "Widely cited preprints that shaped how multi-agent systems are structured and studied.",
    types: ["Preprint"],
  },
]

const NUMBERED = REFERENCES.map((reference, index) => ({ ...reference, number: index + 1 }))

export default function ReferencesPage() {
  return (
    <div className="cin-page cin-about-page">
      <header className="cin-topbar is-transparent">
        <Link href="/" className="cin-brand" aria-label="Assembly home">
          <BrandMark />
          <span className="cin-brand-word">Assembly</span>
        </Link>

        <div className="cin-topbar-actions">
          <ThemeToggle className="cin-icon-button" />
          <Link href="/chat" className="cin-btn cin-btn-sm cin-btn-primary">
            Open workspace
          </Link>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="cin-main">
        <div className="cin-shell cin-page-inner">
          <header className="cin-page-head">
            <div className="cin-page-head-copy">
              <span className="cin-kicker">References</span>
              <h1 className="cin-title">Sources we build on.</h1>
              <p className="cin-lede">
                The research papers and academic resources consulted while designing Assembly. Each entry
                links to the publisher or preprint record, so every claim is one click from its source.
              </p>
            </div>
            <div className="cin-page-head-aside">
              <span className="cin-page-number">References</span>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <span className="cin-chip cin-chip-brand">{REFERENCES.length} sources</span>
              </div>
            </div>
          </header>
        </div>

        {GROUPS.map((group) => (
          <section className="cin-section" key={group.kicker}>
            <div className="cin-shell">
              <div className="cin-section-head">
                <div>
                  <span className="cin-kicker">{group.kicker}</span>
                  <h2>{group.title}</h2>
                </div>
                <p>{group.description}</p>
              </div>

              <ol className="grid list-none gap-3 p-0" start={NUMBERED.find((item) => item.type === group.types[0])?.number ?? 1}>
                {NUMBERED.filter((item) => group.types.includes(item.type)).map((reference) => (
                  <li
                    key={reference.href}
                    className="rounded-2xl border border-border/70 bg-card/40 p-5 backdrop-blur-md"
                  >
                    <div className="flex items-start gap-4">
                      <span className="mt-0.5 shrink-0 text-sm font-semibold tabular-nums text-brand" aria-hidden>
                        [{reference.number}]
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold leading-relaxed text-foreground">
                          {reference.title}
                        </h3>
                        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{reference.authors}</p>
                        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{reference.venue}</p>
                        <a
                          href={reference.href}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-3 inline-flex break-all text-xs font-semibold text-brand underline decoration-brand/40 underline-offset-4 hover:decoration-brand"
                        >
                          {reference.href}
                          <span className="sr-only"> (opens in a new tab)</span>
                        </a>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </section>
        ))}
      </main>
    </div>
  )
}
