import { useEffect, useRef } from "react";
import { createTypographyVortexRenderer } from "./typographyVortexRenderer";

export type TypographyVortexCanvasProps = {
  mode?: "dark" | "light";
  phrase?: string;
  speed?: number;
  ringGrowth?: number;
  opacity?: number;
  dissolveRadius?: number;
  particleAmount?: number;
  suctionDuration?: number;
  centerRadius?: number;
  guideLines?: boolean;
  className?: string;
};

export const TYPOGRAPHY_VORTEX_DEFAULTS = {
  mode: "dark" as const,
  phrase: [
    "MULTI-AGENT COLLABORATION",
    "INDEPENDENT PROBLEM ANALYSIS",
    "AI-POWERED RESEARCH",
    "AUTOMATED FACT-CHECKING",
    "AGENT-TO-AGENT DEBATE",
    "CONSENSUS BUILDING",
    "ANSWER VERIFICATION",
    "CODE REVIEW AND ANALYSIS",
    "DATA ANALYSIS",
    "CYBERSECURITY RESEARCH",
    "BUSINESS INTELLIGENCE",
    "ACADEMIC RESEARCH",
    "REPORT GENERATION",
    "FINAL ANSWER SYNTHESIS",
  ].join(" / ") + " / ",
  speed: 1,
  ringGrowth: 1.21,
  opacity: 1,
  dissolveRadius: 1,
  particleAmount: 1,
  suctionDuration: 920,
  guideLines: false,
} as const;

export function TypographyVortexCanvas({ className = "", ...props }: TypographyVortexCanvasProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const optionsRef = useRef({ ...TYPOGRAPHY_VORTEX_DEFAULTS, ...props });
  optionsRef.current = { ...TYPOGRAPHY_VORTEX_DEFAULTS, ...props };

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return undefined;
    return createTypographyVortexRenderer(host, canvas, () => optionsRef.current);
  }, []);

  return (
    <div
      ref={hostRef}
      className={`typography-vortex-component typography-vortex-component--${optionsRef.current.mode}${className ? ` ${className}` : ""}`}
      data-mode={optionsRef.current.mode}
      data-dissolve-state="ambient"
      data-suction-state="idle"
      data-particles="0"
      data-dissolve-strength="0.00"
    >
      <canvas ref={canvasRef} aria-label="Interactive typography vortex" />
      <span className="typography-vortex-component__hint">MOVE / DISSOLVE · CLICK / SUCTION</span>
    </div>
  );
}
