"use client";

import Link from "next/link";
import { BrandOrbMark } from "@/components/brand-orb-mark";
import { ArrowUpRight } from "lucide-react";

export function LandingFooter() {
  const scrollToTop = () => {
    if (typeof document === "undefined") return;
    const scrollContainers = document.querySelectorAll(".overflow-y-auto");
    scrollContainers.forEach((el) => {
      el.scrollTo({ top: 0, behavior: "smooth" });
    });
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  return (
    <footer className="assembly-rich-footer" aria-label="Assembly footer">
      <div className="assembly-rich-footer-inner">
        {/* Top 4-Column Grid */}
        <div className="assembly-rich-footer-grid">
          {/* Column 1: Brand & Philosophy */}
          <div className="assembly-rich-footer-brand-col">
            <Link href="/" className="assembly-wordmark" aria-label="Assembly Home" onClick={scrollToTop}>
              <BrandOrbMark className="assembly-wordmark-mark--header" /><span>ssembly</span>
            </Link>
            <p className="assembly-rich-footer-desc">
              Turn one hard question into a temporary team of independent AI agents. Cross-examined, cited, and transparent.
            </p>
          </div>

          {/* Column 2: Product */}
          <div className="assembly-rich-footer-nav-col">
            <h4 className="assembly-rich-footer-heading">Product</h4>
            <ul className="assembly-rich-footer-list">
              <li>
                <Link href="/chat" className="assembly-rich-footer-link assembly-rich-footer-link--cta">
                  <span>Start an investigation</span>
                  <ArrowUpRight className="size-3.5" aria-hidden="true" />
                </Link>
              </li>
              <li>
                <Link href="#how-it-works" className="assembly-rich-footer-link">
                  How it works
                </Link>
              </li>
              <li>
                <Link href="#your-control" className="assembly-rich-footer-link">
                  Your control
                </Link>
              </li>
              <li>
                <Link href="#get-started" className="assembly-rich-footer-link">
                  Brand orbs orbit
                </Link>
              </li>
              <li>
                <Link href="#faq" className="assembly-rich-footer-link">
                  FAQ &amp; Guide
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3: Architecture */}
          <div className="assembly-rich-footer-nav-col">
            <h4 className="assembly-rich-footer-heading">Architecture</h4>
            <ul className="assembly-rich-footer-list">
              <li>
                <Link href="#how-it-works" className="assembly-rich-footer-link">
                  Consensus Engine
                </Link>
              </li>
              <li>
                <Link href="#how-it-works" className="assembly-rich-footer-link">
                  Cross-Examination
                </Link>
              </li>
              <li>
                <Link href="#your-control" className="assembly-rich-footer-link">
                  Diversity Gate (7 Families)
                </Link>
              </li>
              <li>
                <Link href="/settings" className="assembly-rich-footer-link">
                  Model Router &amp; Limits
                </Link>
              </li>
              <li>
                <Link href="/settings" className="assembly-rich-footer-link">
                  Local Key Vault
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 4: Trust & Legal */}
          <div className="assembly-rich-footer-nav-col">
            <h4 className="assembly-rich-footer-heading">Trust &amp; Legal</h4>
            <ul className="assembly-rich-footer-list">
              <li>
                <Link href="/privacy" className="assembly-rich-footer-link">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="assembly-rich-footer-link">
                  Terms of Service
                </Link>
              </li>
              <li>
                <Link href="/cookies" className="assembly-rich-footer-link">
                  Cookie Policy
                </Link>
              </li>
              <li>
                <Link href="/refunds" className="assembly-rich-footer-link">
                  Refunds Policy
                </Link>
              </li>
              <li>
                <Link href="/settings" className="assembly-rich-footer-link">
                  Key Management
                </Link>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="assembly-rich-footer-bottom">
          <div className="assembly-rich-footer-bottom-copy">
            <span>© 2026 Assembly. All rights reserved.</span>
          </div>

          <button
            type="button"
            onClick={scrollToTop}
            className="assembly-rich-footer-back-to-top"
            aria-label="Back to top"
          >
            <span>Back to top</span>
            <span aria-hidden="true">↑</span>
          </button>
        </div>
      </div>
    </footer>
  );
}

