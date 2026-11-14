"use client";

import { useEffect, useState } from "react";
import { LandingHeader } from "@/components/landing-header";
import { LandingFooter } from "@/components/landing-footer";
import { Calendar, BookmarkCheck } from "lucide-react";
import "./science.css";

const ROTATING_WORDS = ["research", "papers", "articles"];

const PUBLISHED_RESEARCH = [
  {
    image: "/papers/paper-1-weber.png",
    date: "Nov 07, 2024",
    category: "Platform Orchestration",
    title: "Orchestration Logics for Artificial Intelligence Platforms: From Raw Data to Industry-Specific Applications",
    desc: "A systematic investigation analyzing multi-agent platform orchestration. Demonstrates how coordinating autonomous actors and foundation models systematically surpasses monolithic execution constraints.",
    source: "By Weber, Hein, Weking et al.",
    venue: "Information Systems Journal",
    url: "https://doi.org/10.1111/isj.12567",
  },
  {
    image: "/papers/paper-2-peng.png",
    date: "July 2026",
    category: "Decentralized Swarms",
    title: "Hybrid Orchestration of AI Services and Microservices in Cloud-Edge Collaboration",
    desc: "Presents decentralized multi-agent collaboration algorithms, proving that coupled AI consensus topologies optimize inference accuracy and reduce communication latency under distributed compute constraints.",
    source: "By Peng, Liu, Han et al.",
    venue: "IEEE Trans. Mobile Computing",
    url: "https://doi.org/10.1109/TMC.2026.3654236",
  },
  {
    image: "/papers/paper-3-agentverse.png",
    date: "Aug 21, 2023",
    category: "Collaborative Evaluation",
    title: "AgentVerse: Facilitating Multi-Agent Collaboration and Exploring Emergent Behaviors",
    desc: "Empirically demonstrates that autonomous agent groups deployed with collaborative debate and peer evaluation achieve significantly higher problem-solving fidelity than individual models.",
    source: "By Chen, Su, Zuo et al.",
    venue: "arXiv / ICLR",
    url: "https://doi.org/10.48550/arXiv.2308.10848",
  },
  {
    image: "/papers/paper-4-autogen.png",
    date: "Aug 16, 2023",
    category: "Multi-Agent Debate",
    title: "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation",
    desc: "Formalizes conversational agent architectures, showing that modular, multi-turn cross-examination between specialized agents dramatically mitigates hallucinations and reasoning failures.",
    source: "By Wu, Bansal, Zhang et al.",
    venue: "Microsoft Research / arXiv",
    url: "https://doi.org/10.48550/arXiv.2308.08155",
  },
  {
    image: "/papers/paper-5-neurips.png",
    date: "Dec 2024",
    category: "Dynamic Topologies",
    title: "Multi-Agent Collaboration via Evolving Orchestration",
    desc: "Proves that adaptive orchestration graphs break epistemic conformity traps, enabling heterogeneous model collectives to statistically outperform static single-model inference on complex logic tasks.",
    source: "By Dang, Qian, Luo et al.",
    venue: "NeurIPS 2024",
    url: "https://doi.org/10.52202/085713-5502",
  },
  {
    image: "/papers/paper-6-metagpt.png",
    date: "Aug 01, 2023",
    category: "Role Differentiation",
    title: "MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework",
    desc: "Encodes standardized operating procedures into agent workflows, verifying that structured peer critique and role differentiation systematically prune hallucinated outputs.",
    source: "By Hong, Zhuge, Chen et al.",
    venue: "DeepWisdom / arXiv",
    url: "https://doi.org/10.48550/arXiv.2308.00352",
  },
];

export default function SciencePage() {
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<"idle" | "exiting" | "entering">("idle");

  useEffect(() => {
    let enterTimeout: ReturnType<typeof setTimeout>;
    let switchTimeout: ReturnType<typeof setTimeout>;

    const interval = setInterval(() => {
      // 1. Current word slides up & fades out
      setPhase("exiting");

      switchTimeout = setTimeout(() => {
        // 2. Switch word and position below
        setIndex((prev) => (prev + 1) % ROTATING_WORDS.length);
        setPhase("entering");

        // 3. Glide up into center position
        enterTimeout = setTimeout(() => {
          setPhase("idle");
        }, 40);
      }, 350);
    }, 2800);

    return () => {
      clearInterval(interval);
      clearTimeout(switchTimeout);
      clearTimeout(enterTimeout);
    };
  }, []);

  const currentWord = ROTATING_WORDS[index];

  return (
    <div className="assembly-science-page">
      <LandingHeader />

      {/* Top Hero Stage in Pure Pitch Black */}
      <div className="assembly-science-hero-stage">
        <div className="assembly-science-container">
          <header className="assembly-science-hero">
            <h1>
              The Idea Behind <em>Assembly</em>
            </h1>
            <p className="assembly-science-lead">
              Discover how intelligent agents collaborate, challenge ideas, and combine their
              reasoning to transform complex questions into meaningful insights.
            </p>
          </header>
        </div>
      </div>

      {/* Research Papers Stage on Marigold Yellow Background */}
      <div className="assembly-science-yellow-stage">
        <div className="assembly-science-container">
          <header className="assembly-science-yellow-header">
            <h2>
              What published{" "}
              <span className="assembly-science-rotator-wrap">
                <em
                  className={`assembly-science-rotating-word ${
                    phase === "exiting"
                      ? "is-exiting"
                      : phase === "entering"
                      ? "is-entering"
                      : "is-idle"
                  }`}
                >
                  {currentWord}
                </em>
              </span>{" "}
              show.
            </h2>
            <p className="assembly-science-yellow-subhead">
              Single large language models produce convincing answers, but suffer from systematic
              hallucinations and architectural blindspots. Assembly replaces singular inference with
              a temporary, self-challenging collective of independent AI agents.
            </p>
          </header>

          <section className="assembly-research-grid" aria-label="Published Academic Research">
            {PUBLISHED_RESEARCH.map((paper) => (
              <article key={paper.url} className="assembly-press-card">
                <div className="assembly-press-thumb-wrap">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={paper.image}
                    alt={paper.title}
                    className="assembly-press-thumb"
                    loading="lazy"
                  />
                </div>

                <div className="assembly-press-body">
                  <div className="assembly-press-meta">
                    <span className="assembly-press-date">
                      <Calendar className="size-3.5" />
                      {paper.date}
                    </span>
                    <span className="assembly-press-bullet">&bull;</span>
                    <span className="assembly-press-category">
                      <BookmarkCheck className="size-3.5 text-[#eaa221]" />
                      {paper.category}
                    </span>
                  </div>

                  <h2 className="assembly-press-title">{paper.title}</h2>
                  <p className="assembly-press-desc">{paper.desc}</p>

                  <div className="assembly-press-footer">
                    <span className="assembly-press-source">{paper.source}</span>
                    <a
                      href={paper.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="assembly-press-link"
                    >
                      Read the study &rarr;
                    </a>
                  </div>
                </div>
              </article>
            ))}
          </section>
        </div>
      </div>

      {/* Downward Curve Transition Divider (at exact spot shown in Image 3) */}
      <div className="assembly-science-curve-divider" aria-hidden="true">
        <svg viewBox="0 0 1440 90" preserveAspectRatio="none">
          <path d="M 0,0 Q 720,90 1440,0 L 1440,0 L 0,0 Z" fill="#eaa221" />
        </svg>
      </div>

      {/* Bottom Stage in Pure Pitch Black (2-Column Editorial Side-by-Side, No Boxed Cards) */}
      <div className="assembly-science-black-stage">
        <div className="assembly-science-container assembly-science-editorial-wrap">
          <div className="assembly-science-editorial-grid">
            <article className="assembly-science-editorial-col">
              <span className="assembly-science-eyebrow">The Epistemic Problem</span>
              <h2>Why Single Models Fail at Hard Reasoning</h2>
              <p className="assembly-science-subhead">
                Architectural homogeneity creates convincing illusions of correctness.
              </p>
              <p className="assembly-science-body">
                Single large language models excel at fluent generation, but they suffer from ungrounded confidence.
                When a lone LLM makes a subtle deductive mistake, its internal attention mechanism self-reinforces
                that error across subsequent tokens. Simply asking the same model to &ldquo;double check&rdquo; or running
                majority voting over identical checkpoints merely averages out identical systemic biases rather than uncovering ground truth.
              </p>
            </article>

            <article className="assembly-science-editorial-col">
              <span className="assembly-science-eyebrow">Cross-Architecture Dialectic</span>
              <h2>The Power of Cross-Family Critique</h2>
              <p className="assembly-science-subhead">
                Truth emerges when competing model families are forced to interrogate each other.
              </p>
              <p className="assembly-science-body">
                Assembly enforces strict model diversity across distinct foundational families&mdash;including Gemini, Llama,
                Qwen, and DeepSeek. When an agent forms an initial hypothesis in isolation, a critic agent from an entirely
                different model family is assigned to stress-test the reasoning, while empirical web verification and mathematical
                entropy scoring actively prevent premature consensus.
              </p>
            </article>
          </div>
        </div>

        <LandingFooter />
      </div>
    </div>
  );
}
