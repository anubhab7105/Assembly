"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BrandOrbMark } from "@/components/brand-orb-mark";
import { ArrowUpRight } from "lucide-react";

export function LandingHeader() {
  const [isScrolled, setIsScrolled] = useState(false);
  const headerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    // 1. Find the scroll container in the application shell
    const scrollContainer =
      headerRef.current?.closest(".overflow-y-auto") ||
      document.querySelector(".assembly-app-shell .overflow-y-auto") ||
      document.querySelector(".overflow-y-auto");

    const checkScroll = (target?: EventTarget | null) => {
      let currentTop = 0;
      if (target && "scrollTop" in target) {
        currentTop = (target as HTMLElement).scrollTop;
      } else if (scrollContainer && "scrollTop" in scrollContainer) {
        currentTop = (scrollContainer as HTMLElement).scrollTop;
      } else {
        currentTop = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
      }
      setIsScrolled(currentTop > 80);
    };

    // Check initial state
    checkScroll();

    // 2. Listen to scroll container directly
    const onContainerScroll = (e: Event) => {
      checkScroll(e.target);
    };

    if (scrollContainer) {
      scrollContainer.addEventListener("scroll", onContainerScroll, { passive: true });
    }

    // 3. Listen to captured scroll events on window for any child containers
    const onWindowScroll = (e: Event) => {
      checkScroll(e.target);
    };

    window.addEventListener("scroll", onWindowScroll, { passive: true, capture: true });

    // 4. IntersectionObserver fallback on hero top boundary
    let observer: IntersectionObserver | null = null;
    let sentinel: HTMLDivElement | null = null;
    const heroSection =
      document.querySelector(".assembly-hero-fullbleed") ||
      document.querySelector(".assembly-hero-yellow-stage") ||
      document.querySelector(".assembly-landing-curtain");

    if (typeof IntersectionObserver !== "undefined" && heroSection) {
      sentinel = document.createElement("div");
      sentinel.style.position = "absolute";
      sentinel.style.top = "0";
      sentinel.style.left = "0";
      sentinel.style.width = "100%";
      sentinel.style.height = "80px";
      sentinel.style.pointerEvents = "none";
      sentinel.setAttribute("aria-hidden", "true");
      heroSection.appendChild(sentinel);

      observer = new IntersectionObserver(
        ([entry]) => {
          setIsScrolled(!entry.isIntersecting);
        },
        {
          root: (scrollContainer as Element) || null,
          threshold: 0,
        }
      );
      observer.observe(sentinel);
    }

    return () => {
      if (scrollContainer) {
        scrollContainer.removeEventListener("scroll", onContainerScroll);
      }
      window.removeEventListener("scroll", onWindowScroll, true);
      observer?.disconnect();
      if (sentinel && sentinel.parentNode) {
        sentinel.parentNode.removeChild(sentinel);
      }
    };
  }, []);

  return (
    <header
      ref={headerRef}
      className={`assembly-landing-header ${isScrolled ? "is-scrolled" : "is-top"}`}
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
        aria-hidden={!isScrolled}
      >
        <Link href="#how-it-works" tabIndex={isScrolled ? 0 : -1}>
          How it works
        </Link>
        <Link href="/science" tabIndex={isScrolled ? 0 : -1}>
          Idea
        </Link>
        <Link href="#your-control" tabIndex={isScrolled ? 0 : -1}>
          Your control
        </Link>
        <Link href="#faq" tabIndex={isScrolled ? 0 : -1}>
          FAQ
        </Link>
      </nav>

      <div
        className="assembly-landing-actions"
        aria-hidden={!isScrolled}
      >
        <Link
          href="/chat"
          className="assembly-nav-cta"
          tabIndex={isScrolled ? 0 : -1}
        >
          Start an investigation
          <ArrowUpRight className="size-4" />
        </Link>
      </div>
    </header>
  );
}
