"use client";

import { useEffect, useRef } from "react";
import { ArrowRight } from "lucide-react";

export interface FaqItem {
  question: string;
  answer: string;
}

export function LandingFaqAccordion({ items }: { items: FaqItem[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const detailsList = container.querySelectorAll<HTMLDetailsElement>("details.assembly-faq-item");
    const handleToggle = (e: Event) => {
      const target = e.currentTarget as HTMLDetailsElement;
      if (target.open) {
        detailsList.forEach((details) => {
          if (details !== target && details.open) {
            details.open = false;
          }
        });
      }
    };

    detailsList.forEach((details) => {
      details.addEventListener("toggle", handleToggle);
    });

    return () => {
      detailsList.forEach((details) => {
        details.removeEventListener("toggle", handleToggle);
      });
    };
  }, [items]);

  return (
    <div ref={containerRef} className="assembly-faq-list">
      {items.map((faq) => (
        <details className="assembly-faq-item" key={faq.question} name="assembly-faq">
          <summary>
            {faq.question}
            <span>
              <ArrowRight className="size-4" aria-hidden="true" />
            </span>
          </summary>
          <p>{faq.answer}</p>
        </details>
      ))}
    </div>
  );
}
