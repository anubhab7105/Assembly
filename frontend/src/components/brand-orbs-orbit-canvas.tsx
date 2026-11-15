"use client";

import { useEffect, useRef } from "react";
import { initBrandOrbsOrbit } from "./brand-orbs-orbit-engine";

export function BrandOrbsOrbitCanvas({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const cleanup = initBrandOrbsOrbit(canvas);
    return () => {
      cleanup();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`intro-orbit-canvas ${className}`}
      style={{ display: "block", width: "100%", height: "100%", background: "transparent" }}
    />
  );
}
