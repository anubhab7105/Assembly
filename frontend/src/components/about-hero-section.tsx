"use client";

import { useEffect, useRef } from "react";
import { AssemblyHeroExperience } from "./assembly-hero-experience";

export function AboutHeroSection() {
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

    const scrollContainer =
      section.closest(".overflow-y-auto") ||
      document.querySelector(".assembly-app-shell .overflow-y-auto") ||
      document.querySelector(".overflow-y-auto");

    const animateHero = () => {
      if (!section) return;
      const rect = section.getBoundingClientRect();
      const windowHeight = window.innerHeight;

      // Expansion begins as Section 3 approaches bottom (85% down) and completes as it transitions (45%)
      const start = windowHeight * 0.85;
      const end = windowHeight * 0.45;

      let rawProgress = (start - rect.bottom) / (start - end);
      rawProgress = Math.max(0, Math.min(rawProgress, 1));

      // Hermite smoothstep easing (3p^2 - 2p^3)
      const progress = rawProgress * rawProgress * (3 - 2 * rawProgress);

      const width = (95 + 5 * progress).toFixed(2);
      section.style.width = `${width}%`;
    };

    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          animateHero();
          ticking = false;
        });
        ticking = true;
      }
    };

    const container = scrollContainer || window;
    container.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });

    // Initial check
    animateHero();

    return () => {
      container.removeEventListener("scroll", onScroll);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <section
      ref={sectionRef}
      id="how-it-works"
      className="assembly-bezel-frame assembly-nova-section"
      aria-label="About Assembly Multi-Agent Experience"
      style={{ width: "95%", marginInline: "auto" }}
    >
      <AssemblyHeroExperience />

      <a href="#your-control" className="assembly-bezel-notch" aria-label="Scroll to next section">
        <svg
          className="assembly-notch-arch"
          viewBox="0 0 320 50"
          fill="none"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            d="M 0 48 C 20 48, 34 36, 34 24 C 34 12, 46 0, 64 0 L 256 0 C 274 0, 286 12, 286 24 C 286 36, 300 48, 320 48 L 320 50 L 0 50 Z"
            fill="#eaa221"
          />
          <path
            className="assembly-notch-stroke"
            d="M 0 48 C 20 48, 34 36, 34 24 C 34 12, 46 0, 64 0 L 256 0 C 274 0, 286 12, 286 24 C 286 36, 300 48, 320 48"
            stroke="none"
            strokeWidth="1"
            fill="none"
          />
        </svg>
      </a>
    </section>
  );
}
