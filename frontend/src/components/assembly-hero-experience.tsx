"use client";

import { useEffect, useRef, useState } from "react";
import { BrandOrbsOrbitCanvas } from "./brand-orbs-orbit-canvas";
import "../app/assembly-hero-experience.css";

const PRODUCT_TABS = [
  "Multi-Agent Collaboration",
  "Independent Problem Analysis",
  "AI-Powered Research",
  "Automated Fact-Checking",
  "Agent-to-Agent Debate",
  "Consensus Building",
  "Answer Verification",
  "Code Review and Analysis",
];

export function AssemblyHeroExperience() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState(0);

  // Tab Auto-Rotation Interval
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveTab((prev) => (prev + 1) % PRODUCT_TABS.length);
    }, 2400);

    return () => clearInterval(timer);
  }, []);

  // IntersectionObserver for reveal animation (.rv -> .revealed)
  useEffect(() => {
    const root = rootRef.current;
    if (!root || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
          }
        });
      },
      { threshold: 0.05, rootMargin: "0px 0px -20px 0px" }
    );

    const revealElements = root.querySelectorAll(".rv");
    revealElements.forEach((el) => observer.observe(el));

    return () => {
      observer.disconnect();
    };
  }, []);

  return (
    <div ref={rootRef} className="assembly-nova-experience-root">
      {/* Main Multi-Section Content */}
      <div className="content-container">
        {/* Section 1: Intro */}
        <section id="intro" className="assembly-hero-section">
          <div className="section-stage">
            <div className="intro-bottom-left rv rv-del-3">
              <div className="intro-unleash">Multi-Agent AI Orchestration Platform</div>
              <div className="headline-boxes">
                <h1 className="hero-slogan-title">
                  <span className="headline-box machines">Let intelligence</span>
                  <span className="headline-plain-text">
                    challenge<br />
                    itself.
                  </span>
                </h1>
              </div>
              <div className="intro-desc">
                <p>
                  Assembly brings multiple AI agents together to solve your questions independently, challenge conflicting perspectives, and verify evidence. Through collaborative reasoning and intelligent research, it turns diverse insights into one carefully synthesized answer, within a time budget you control.
                </p>
              </div>
            </div>

            {/* Orbiting Models on Right (Scrolls up naturally with Section 1) */}
            <div className="intro-orbit-box" aria-hidden="true">
              <BrandOrbsOrbitCanvas />
            </div>
          </div>
        </section>

        {/* Section 2: Product — Centered Multi-Agent Consensus */}
        <section id="how-it-works" className="assembly-hero-section">
          <div className="section-stage">
            <div className="product-carousel-wrap rv rv-del-1">
              <div
                className="product-carousel-strip"
                style={{ transform: `translateX(-${activeTab * 336}px)` }}
              >
                {PRODUCT_TABS.map((tab, idx) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(idx)}
                    className={`carousel-tab ${idx === activeTab ? "active" : ""}`}
                    aria-pressed={idx === activeTab}
                  >
                    <span>{tab}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="product-headline rv rv-del-2">
              <div className="gateway-box">How Assembly Works</div>
              <h2 className="product-title">Multi-Agent Consensus</h2>
              <div className="product-desc">
                <p>
                  Set a 3, 5, 10, or 15-minute time budget. Assembly immediately mobilizes an ad-hoc ensemble of specialized agents. Each model formulates its hypothesis in complete epistemic isolation before reviewing peer contributions, ensuring independent lines of reasoning that remain completely free from groupthink, prompt priming, or shared single-model bias.
                </p>
                <p>
                  Rather than trusting a single LLM or relying on passive majority voting, Assembly coordinates diverse model architectures (Gemini, Llama, Qwen, DeepSeek) across specialized roles: independent solvers, adversarial critics, and empirical researchers. Opposing model families rigorously cross-examine contradictory claims, expose hidden assumptions, and stress-test every weak assertion.
                </p>
                <p>
                  Live web search results ground factual statements in verifiable primary sources, while an automated consensus engine continuously scores agreement rates, evidentiary weight, and confidence drift. If consensus emerges too quickly, an adversarial challenger round triggers to pressure fragile assumptions.
                </p>
                <p>
                  The final synthesizer distills the entire debate into one definitive, audit-ready answer complete with cited sources, dissenting viewpoints, and explicit uncertainty notes — delivering verifiable epistemic rigor within your exact time budget.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Section 3: Our Approach */}
        <section id="reviews" className="assembly-hero-section">
          <div className="section-stage">
            <div className="reviews-header-strip rv rv-del-1">
              <span className="tstmnl-badge">OUR APPROACH</span>
              <div className="tstmnl-avatar">
                {/* Multi-agent connected nodes icon */}
                <svg width="44" height="44" viewBox="0 0 44 44" fill="none">
                  <circle cx="14" cy="16" r="3.5" fill="#ff8a3d" />
                  <circle cx="30" cy="16" r="3.5" fill="#ff3d8b" />
                  <circle cx="22" cy="29" r="4" fill="#f0ede6" />
                  <line x1="14" y1="16" x2="22" y2="29" stroke="rgba(255,255,255,0.3)" strokeWidth="1.2" />
                  <line x1="30" y1="16" x2="22" y2="29" stroke="rgba(255,255,255,0.3)" strokeWidth="1.2" />
                  <line
                    x1="14"
                    y1="16"
                    x2="30"
                    y2="16"
                    stroke="rgba(255,255,255,0.2)"
                    strokeWidth="1.2"
                    strokeDasharray="2 2"
                  />
                </svg>
              </div>
              <div className="tstmnl-name-group">
                <span className="tstmnl-name">Cognitive Diversity</span>
                <span className="tstmnl-role">Cross-Model Verification</span>
              </div>
            </div>

            <div className="review-quote-wrap rv rv-del-2">
              <div className="review-quote">
                “Multi-agent orchestration that replaces single-model blind spots with rigorous cross-examination.”
              </div>
              <p className="approach-body">
                Instead of trusting a single LLM or relying on passive majority voting, Assembly coordinates a temporary
                team of models across distinct families. Agents formulate solutions in isolation, then actively
                cross-examine contradictions.
              </p>
              <p className="approach-body">
                Dedicated critics challenge assumptions while researchers verify factual claims against live web sources. If
                consensus forms too easily, an adversarial check triggers — synthesizing one verified, sourced answer with
                transparent uncertainty notes within your strict time budget.
              </p>
            </div>

            <div className="reviews-right rv rv-del-3">
              <div className="reviews-right-tag">Zero Shared Blindspots</div>
              <p className="reviews-right-desc">
                <strong>Multi-Family Redundancy:</strong> Single models share systematic blindspots. Assembly coordinates
                models across distinct architectures (Gemini, Llama, Qwen, DeepSeek), guaranteeing independent critical
                perspectives.
              </p>
              <p className="reviews-right-desc">
                <strong>Adversarial Pressure:</strong> When early agreement risks complacency, an automated challenger round
                pressures the consensus, forcing models to defend or revise their conclusions.
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
