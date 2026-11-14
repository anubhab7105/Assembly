"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandOrbMark } from "@/components/brand-orb-mark";
import { ArrowUpRight } from "lucide-react";

export function LandingHeader() {
  const pathname = usePathname();
  const isHome = pathname === "/";
  const [isScrolled, setIsScrolled] = useState(false);
  const isHeaderSolid = !isHome || isScrolled;
  const headerRef = useRef<HTMLElement>(null);

  // Smooth scroll helper for section links
  const scrollToSection = useCallback((sectionId: string) => {
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  const handleNavClick = (sectionId: string, e: React.MouseEvent) => {
    if (isHome) {
      e.preventDefault();
      scrollToSection(sectionId);
      if (typeof window !== "undefined") {
        window.history.pushState(null, "", `/#${sectionId}`);
      }
    }
  };

  // When on home page and arrived with or switched to a hash, scroll to that section
  useEffect(() => {
    if (typeof window === "undefined" || !isHome) return;

    const handleHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (hash) {
        setTimeout(() => {
          scrollToSection(hash);
        }, 150);
      }
    };

    handleHash();
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, [isHome, scrollToSection]);

  // Scroll detection for homepage header appearance
  useEffect(() => {
    if (!isHome) return;

    const scrollContainer =
      headerRef.current?.closest(".overflow-y-auto") ||
      document.querySelector(".assembly-app-shell .overflow-y-auto") ||
      document.querySelector(".overflow-y-auto");

    const getScrollTop = () => {
      if (scrollContainer && "scrollTop" in scrollContainer) {
        return (scrollContainer as HTMLElement).scrollTop;
      }
      return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
    };

    const updateScroll = () => {
      const top = getScrollTop();
      setIsScrolled(top > 80);
    };

    // Initial check
    updateScroll();

    if (scrollContainer) {
      scrollContainer.addEventListener("scroll", updateScroll, { passive: true });
    }
    window.addEventListener("scroll", updateScroll, { passive: true });

    return () => {
      if (scrollContainer) {
        scrollContainer.removeEventListener("scroll", updateScroll);
      }
      window.removeEventListener("scroll", updateScroll);
    };
  }, [isHome]);

  return (
    <header
      ref={headerRef}
      className={`assembly-landing-header ${isHeaderSolid ? "is-scrolled" : "is-top"}`}
      aria-label="Site header"
    >
      <Link
        href="/"
        className="assembly-wordmark"
        aria-label="Assembly home"
        onClick={() => {
          const scrollContainers = document.querySelectorAll(".overflow-y-auto");
          scrollContainers.forEach((el) => {
            el.scrollTo({ top: 0, behavior: "smooth" });
          });
          if (typeof window !== "undefined") {
            window.scrollTo({ top: 0, behavior: "smooth" });
          }
        }}
      >
        <BrandOrbMark /><span>ssembly</span>
      </Link>

      <nav
        className="assembly-landing-links"
        aria-label="Main navigation"
        aria-hidden={!isHeaderSolid}
      >
        <Link
          href="/#how-it-works"
          onClick={(e) => handleNavClick("how-it-works", e)}
          tabIndex={isHeaderSolid ? 0 : -1}
        >
          How it works
        </Link>
        <Link
          href="/science"
          className={pathname === "/science" ? "is-active" : undefined}
          tabIndex={isHeaderSolid ? 0 : -1}
        >
          Idea
        </Link>
        <Link
          href="/#your-control"
          onClick={(e) => handleNavClick("your-control", e)}
          tabIndex={isHeaderSolid ? 0 : -1}
        >
          Your control
        </Link>
        <Link
          href="/#faq"
          onClick={(e) => handleNavClick("faq", e)}
          tabIndex={isHeaderSolid ? 0 : -1}
        >
          FAQ
        </Link>
      </nav>

      <div
        className="assembly-landing-actions"
        aria-hidden={!isHeaderSolid}
      >
        <Link
          href="/chat"
          className="assembly-nav-cta"
          tabIndex={isHeaderSolid ? 0 : -1}
        >
          Start an investigation
          <ArrowUpRight className="size-4" />
        </Link>
      </div>
    </header>
  );
}
