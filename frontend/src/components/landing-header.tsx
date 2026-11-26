"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandOrbMark } from "@/components/brand-orb-mark";
import { ArrowUpRight, Menu, X } from "lucide-react";

export function LandingHeader() {
  const pathname = usePathname();
  const isHome = pathname === "/";
  const [isScrolled, setIsScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const isHeaderSolid = !isHome || isScrolled;
  const isDarkHeader = isHeaderSolid || mobileMenuOpen;
  const headerRef = useRef<HTMLElement>(null);

  // Close mobile menu on Escape key
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileMenuOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Smooth scroll helper for section links
  const scrollToSection = useCallback((sectionId: string) => {
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  const handleNavClick = (sectionId: string, e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
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

    let timerId: ReturnType<typeof setTimeout> | null = null;
    const handleHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (hash) {
        if (timerId) clearTimeout(timerId);
        timerId = setTimeout(() => {
          scrollToSection(hash);
        }, 150);
      }
    };

    handleHash();
    window.addEventListener("hashchange", handleHash);
    return () => {
      if (timerId) clearTimeout(timerId);
      window.removeEventListener("hashchange", handleHash);
    };
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

      <div className="assembly-landing-actions hidden sm:flex">
        <Link
          href="/get-started"
          className="assembly-nav-cta"
          tabIndex={0}
        >
          Start an investigation
          <ArrowUpRight className="size-4" />
        </Link>
      </div>

      {/* Mobile Hamburger Button */}
      <button
        type="button"
        className={`sm:hidden inline-flex items-center justify-center p-2 rounded-lg transition ${
          isDarkHeader
            ? "text-white/85 hover:text-white hover:bg-white/10"
            : "text-black/85 hover:text-black hover:bg-black/10"
        }`}
        onClick={() => setMobileMenuOpen((prev) => !prev)}
        aria-label={mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
        aria-expanded={mobileMenuOpen}
        aria-controls="mobile-nav-menu"
      >
        {mobileMenuOpen ? <X className="size-6" /> : <Menu className="size-6" />}
      </button>

      {/* Mobile Dropdown Navigation Menu */}
      {mobileMenuOpen && (
        <div
          id="mobile-nav-menu"
          className="sm:hidden absolute top-full left-0 right-0 border-b border-white/10 bg-[#0b0c0e]/95 backdrop-blur-2xl px-6 py-6 shadow-2xl z-50 text-white"
        >
          <nav className="flex flex-col gap-4 text-base font-medium" aria-label="Mobile navigation">
            <Link
              href="/#how-it-works"
              className="py-2 text-white/85 transition hover:text-[#eaa221]"
              onClick={(e) => {
                setMobileMenuOpen(false);
                handleNavClick("how-it-works", e);
              }}
            >
              How it works
            </Link>
            <Link
              href="/science"
              className={`py-2 transition hover:text-[#eaa221] ${
                pathname === "/science" ? "text-[#eaa221]" : "text-white/85"
              }`}
              onClick={() => setMobileMenuOpen(false)}
            >
              Idea
            </Link>
            <Link
              href="/#your-control"
              className="py-2 text-white/85 transition hover:text-[#eaa221]"
              onClick={(e) => {
                setMobileMenuOpen(false);
                handleNavClick("your-control", e);
              }}
            >
              Your control
            </Link>
            <Link
              href="/#faq"
              className="py-2 text-white/85 transition hover:text-[#eaa221]"
              onClick={(e) => {
                setMobileMenuOpen(false);
                handleNavClick("faq", e);
              }}
            >
              FAQ
            </Link>
          </nav>
        </div>
      )}
    </header>
  );
}
