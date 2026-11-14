"use client";

import { useRef, useEffect, useState } from "react";
import {
  CheckCircle2,
  LockKeyhole,
  MessageSquare,
  Search,
  Timer,
} from "lucide-react";

export const CONTROL_ITEMS = [
  {
    icon: LockKeyhole,
    title: "Your credentials",
    description: "Bring your own provider keys. Saved web keys stay in your browser.",
  },
  {
    icon: Timer,
    title: "Your time",
    description: "Choose 3, 5, 10, or 15 minutes for the investigation.",
  },
  {
    icon: Search,
    title: "Your evidence",
    description: "Review cited sources, confidence, and areas that remain uncertain.",
  },
  {
    icon: MessageSquare,
    title: "Your history",
    description: "Return to investigations saved locally on this device.",
  },
];

export function AssemblyControlDraggableList() {
  const containerRef = useRef<HTMLDivElement>(null);
  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const startScrollTopRef = useRef(0);
  const [isDragging, setIsDragging] = useState(false);

  // Continuous smooth auto-scrolling animation (seamlessly continues anytime user is not dragging)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let animationFrameId: number;
    let lastTime = performance.now();

    const loop = (now: number) => {
      const dt = Math.min(now - lastTime, 64);
      lastTime = now;

      if (!isDraggingRef.current) {
        // Continuous upward auto-scroll speed (~32px per sec)
        const scrollSpeed = 0.032;
        el.scrollTop += scrollSpeed * dt;

        const halfHeight = el.scrollHeight / 2;
        if (el.scrollTop >= halfHeight) {
          el.scrollTop -= halfHeight;
        }
      }

      animationFrameId = requestAnimationFrame(loop);
    };

    animationFrameId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    const el = containerRef.current;
    if (!el) return;

    isDraggingRef.current = true;
    setIsDragging(true);
    startYRef.current = e.clientY;
    startScrollTopRef.current = el.scrollTop;

    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {}
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;
    const el = containerRef.current;
    if (!el) return;

    const dy = e.clientY - startYRef.current;
    el.scrollTop = startScrollTopRef.current - dy;

    const halfHeight = el.scrollHeight / 2;
    if (el.scrollTop >= halfHeight) {
      el.scrollTop -= halfHeight;
      startScrollTopRef.current -= halfHeight;
    } else if (el.scrollTop < 0) {
      el.scrollTop += halfHeight;
      startScrollTopRef.current += halfHeight;
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;
    isDraggingRef.current = false;
    setIsDragging(false);

    try {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    } catch {}
  };

  return (
    <div
      ref={containerRef}
      className={`assembly-control-draggable-viewport ${isDragging ? "is-dragging" : ""}`}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      role="region"
      aria-label="Interactive control items, drag to scroll"
    >
      <div className="assembly-control-draggable-track">
        {[...CONTROL_ITEMS, ...CONTROL_ITEMS, ...CONTROL_ITEMS].map((item, idx) => {
          const Icon = item.icon;
          return (
            <div
              key={idx}
              className="assembly-control-item"
              aria-hidden={idx >= CONTROL_ITEMS.length ? "true" : undefined}
            >
              <span className="assembly-control-icon">
                <Icon className="size-4" />
              </span>
              <div>
                <b>{item.title}</b>
                <p>{item.description}</p>
              </div>
              <CheckCircle2 className="size-4 assembly-control-check" />
            </div>
          );
        })}
      </div>
    </div>
  );
}
