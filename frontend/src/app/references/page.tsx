import Link from "next/link"
import { BrandMark } from "@/components/cinematic/brand-mark"
import { ThemeToggle } from "@/components/theme-toggle"

const REFERENCES: Array<{ title: string; authors: string; venue: string; href: string }> = [
  {
    title: "Orchestration logics for artificial intelligence platforms: From raw data to industry-specific applications",
    authors: "Weber, M., Hein, A., Weking, J., & Krcmar, H.",
    venue: "Information Systems Journal, 35(3), 1015–1043 (2025)",
    href: "https://doi.org/10.1111/isj.12567",
  },
  {
    title: "Hybrid orchestration of AI services and microservices in cloud-edge collaboration",
    authors: "Peng, K., Liu, X., Han, D., Hu, Y., Hu, M., Cai, C., & Xiong, Z.",
    venue: "IEEE Transactions on Mobile Computing, 25(7), 9382–9400 (2026)",
    href: "https://doi.org/10.1109/TMC.2026.3654236",
  },
  {
    title: "Multi-agent collaboration via evolving orchestration",
    authors: "Dang, Y., Qian, C., Luo, X., Fan, J., Xie, Z., Shi, R., Chen, W., Yang, C., Che, X., Tian, Y., Xiong, X., Han, L., Liu, Z., & Sun, M.",
    venue: "Advances in Neural Information Processing Systems 38 (NeurIPS 2025), pp. 182975–183009",
    href: "https://doi.org/10.52202/085713-5502",
  },
  {
    title: "AgentVerse: Facilitating multi-agent collaboration and exploring emergent behaviors",
    authors: "Chen, W., Su, Y., Zuo, J., Yang, C., Yuan, C., Chan, C.-M., Yu, H., Lu, Y., Hung, Y.-H., Qian, C., Qin, Y., Cong, X., Xie, R., Liu, Z., Sun, M., & Zhou, J.",
    venue: "arXiv:2308.10848 (2023)",
    href: "https://doi.org/10.48550/arXiv.2308.10848",
  },
  {
    title: "AutoGen: Enabling next-gen LLM applications via multi-agent conversation",
    authors: "Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., Jiang, L., Zhang, X., Zhang, S., Liu, J., Awadallah, A. H., White, R. W., Burger, D., & Wang, C.",
    venue: "arXiv:2308.08155 (2023)",
    href: "https://doi.org/10.48550/arXiv.2308.08155",
  },
  {
    title: "MetaGPT: Meta programming for a multi-agent collaborative framework",
    authors: "Hong, S., Zhuge, M., Chen, J., Zheng, X., Cheng, Y., Zhang, C., Wang, J., Wang, Z., Yau, S. K. S., Lin, Z., Zhou, L., Ran, C., Xiao, L., Wu, C., & Schmidhuber, J.",
    venue: "arXiv:2308.00352 (2023)",
    href: "https://doi.org/10.48550/arXiv.2308.00352",
  },
]

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
          <h1 className="cin-title">References</h1>
          <p className="cin-lede">
            Papers consulted while designing Assembly. Each link opens the publisher or preprint record.
          </p>

          <ol className="mt-10 list-none space-y-0 border-t border-border/60 p-0">
            {REFERENCES.map((reference, index) => (
              <li key={reference.href} className="border-b border-border/60 py-5">
                <div className="flex gap-4">
                  <span className="shrink-0 text-sm tabular-nums text-muted-foreground">{index + 1}.</span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold leading-relaxed text-foreground">
                      {reference.title}
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      {reference.authors}
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      {reference.venue}
                    </p>
                    <a
                      href={reference.href}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-block break-all text-xs text-brand underline underline-offset-4"
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
      </main>
    </div>
  )
}
