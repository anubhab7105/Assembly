"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { TypographyVortexCanvas, TextPathStudies, RectangleButtons } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

const emptySubscribe = () => () => {};

// Halftone dotted "A" mark circles [gx, gy, radius] from ThreeUI BrandOrbs "aura" specification
const AURA_DOTS: readonly [number, number, number][] = [
  [-0.173, -0.959, 0.065], [-0.015, -0.963, 0.061], [0.138, -0.971, 0.052], [-0.264, -0.803, 0.059],
  [-0.103, -0.804, 0.058], [0.056, -0.807, 0.055], [0.207, -0.817, 0.044], [-0.336, -0.636, 0.064],
  [-0.172, -0.634, 0.067], [-0.012, -0.636, 0.064], [0.131, -0.655, 0.045], [0.284, -0.664, 0.036],
  [-0.417, -0.47, 0.068], [-0.291, -0.507, 0.032], [-0.143, -0.52, 0.018], [0.049, -0.49, 0.048],
  [0.201, -0.5, 0.038], [0.357, -0.506, 0.033], [-0.499, -0.313, 0.064], [-0.375, -0.351, 0.025],
  [-0.217, -0.355, 0.021], [0.131, -0.331, 0.045], [0.285, -0.339, 0.037], [0.439, -0.346, 0.03],
  [-0.589, -0.157, 0.058], [-0.456, -0.185, 0.03], [-0.298, -0.19, 0.025], [0.207, -0.17, 0.045],
  [0.361, -0.178, 0.036], [0.513, -0.187, 0.027], [-0.669, 0.002, 0.055], [-0.534, -0.024, 0.029],
  [0.291, -0.009, 0.043], [0.45, -0.012, 0.041], [0.598, -0.026, 0.026], [-0.755, 0.163, 0.054],
  [-0.611, 0.146, 0.036], [-0.457, 0.137, 0.028], [0.36, 0.145, 0.035], [0.523, 0.146, 0.036],
  [0.675, 0.136, 0.026], [-0.836, 0.322, 0.05], [-0.681, 0.315, 0.043], [-0.524, 0.31, 0.039],
  [-0.355, 0.316, 0.045], [-0.196, 0.314, 0.043], [-0.038, 0.31, 0.038], [0.117, 0.303, 0.032],
  [0.265, 0.289, 0.018], [0.442, 0.304, 0.032], [0.601, 0.301, 0.03], [0.759, 0.297, 0.025],
  [-0.924, 0.48, 0.047], [-0.765, 0.477, 0.044], [-0.588, 0.492, 0.058], [-0.43, 0.488, 0.055],
  [-0.3, 0.456, 0.023], [-0.118, 0.476, 0.043], [0.035, 0.468, 0.035], [0.197, 0.467, 0.034],
  [0.353, 0.462, 0.028], [0.516, 0.463, 0.029], [0.677, 0.462, 0.029], [0.832, 0.455, 0.022],
  [-1.0, 0.643, 0.048], [-0.839, 0.642, 0.047], [-0.675, 0.645, 0.05], [-0.527, 0.631, 0.035],
  [0.123, 0.632, 0.037], [0.277, 0.625, 0.029], [0.437, 0.623, 0.028], [0.599, 0.623, 0.028],
  [0.757, 0.619, 0.024], [0.918, 0.618, 0.023], [-0.92, 0.808, 0.051], [-0.762, 0.804, 0.047],
  [0.357, 0.79, 0.033], [0.517, 0.787, 0.03], [0.676, 0.785, 0.028], [0.835, 0.782, 0.024],
  [1.0, 0.785, 0.028], [-0.995, 0.971, 0.053], [-0.835, 0.97, 0.051], [0.604, 0.951, 0.033],
  [0.761, 0.947, 0.028], [0.926, 0.95, 0.031],
];

const TAU = Math.PI * 2;
const VORTEX_PHRASE = [
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
].join(" / ") + " / ";
const WORD_STR = "ssembly";

const JIT_OFFSETS: [number, number, number][] = [
  [-0.64, 0.42, 0.12],
  [0.55, -0.71, 0.38],
  [-0.32, 0.65, 0.22],
  [0.78, 0.31, 0.51],
  [-0.45, -0.52, 0.18],
  [0.62, 0.82, 0.44],
  [-0.73, -0.25, 0.31]
];

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v));
}
function clamp01(v: number) {
  return clamp(v, 0, 1);
}
function seg(v: number, a: number, b: number) {
  return (v - a) / (b - a);
}
function eOut(t: number) {
  return 1 - Math.pow(1 - t, 3);
}
function smooth(v: number) {
  v = clamp(v, 0, 1);
  return v * v * (3 - 2 * v);
}
function lerp(a: number, b: number, m: number) {
  return a + (b - a) * m;
}

const proj = (yaw: number, tilt: number, cx: number, cy: number, s: number) => {
  const st = Math.sin(tilt), ct = Math.cos(tilt);
  const sy = Math.sin(yaw), cyw = Math.cos(yaw);
  return (x: number, y: number, z: number): [number, number, number] => {
    const px = x * cyw + z * sy, pz = -x * sy + z * cyw;
    const py = y * ct - pz * st, z2 = y * st + pz * ct;
    return [cx + px * s, cy - py * s, z2];
  };
};

function KineticAssemblyWordmark({
  isTriggered,
  onSettled,
}: {
  isTriggered: boolean;
  onSettled: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const hasCompletedRef = useRef(false);
  const isAnimatingRef = useRef(false);
  const onSettledRef = useRef(onSettled);

  useEffect(() => {
    onSettledRef.current = onSettled;
  }, [onSettled]);

  useEffect(() => {
    if (!isTriggered) return;
    // Strictly run once: if already played or completed, never restart
    if (hasCompletedRef.current) return;
    if (isAnimatingRef.current) return;
    isAnimatingRef.current = true;

    const canvas = canvasRef.current;
    const host = hostRef.current;
    if (!canvas || !host) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let startTime: number | null = null;
    const DURATION = 2100; // ms

    const drawFrame = (p: number, t: number) => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = host.clientWidth;
      const height = host.clientHeight;

      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }

      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const fontSize = Math.round(clamp(width * 0.115, 46, 88));
      ctx.font = `700 ${fontSize}px -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif`;
      ctx.textBaseline = "middle";

      // Measure character offsets
      const charOffsets: number[] = [];
      let measuredTextW = 0;
      for (let i = 0; i < WORD_STR.length; i++) {
        charOffsets.push(measuredTextW);
        measuredTextW += ctx.measureText(WORD_STR[i]).width;
      }

      const markSize = fontSize * 0.95;
      const gap = fontSize * 0.04;
      const totalW = markSize + gap + measuredTextW;

      const cx = width / 2;
      const cy = height / 2;
      const startX = cx - totalW / 2;

      // 1. Authentic ThreeUI Aura Halftone Dotted "A" mark
      const mkO = smooth(seg(p, 0.12, 0.70));
      const mkS = lerp(0.45, 1, eOut(clamp(seg(p, 0.12, 0.75), 0, 1)));
      if (mkO > 0.01) {
        ctx.save();
        const mkCenterX = startX + markSize / 2;
        const mkCenterY = cy;
        const R = (markSize / 2) * 0.78 * mkS;
        const rs = Math.pow(markSize / 300, 0.6) * 1.5;
        const pProj = proj(0.14 * Math.sin(t * 0.36), 0.12 * Math.sin(t * 0.28), mkCenterX, mkCenterY, R);

        /* Authentic ThreeUI aura ripple travels outward through the field */
        const ring = (((t * 0.32) % 1 + 1) % 1) * 2.2 - 0.2;
        const dots: Array<{ x: number; y: number; z: number; r: number; v: number; glow: number }> = [];

        for (let i = 0; i < AURA_DOTS.length; i++) {
          const [gx, gy, gr] = AURA_DOTS[i];
          const d0 = Math.hypot(gx, gy);
          const glow = Math.exp(-Math.pow(d0 - ring, 2) / 0.045);
          const [x, y, z] = pProj(gx, -gy, 0);
          const dep = (z + 1) / 2;
          dots.push({
            x,
            y,
            z,
            r: (Math.max(0.5, gr * R * 0.95) + (0.22 * dep + 0.65 * glow) * rs) * mkS,
            v: clamp01(0.5 + 0.12 * dep + 0.38 * glow),
            glow,
          });
        }

        dots.sort((a, b) => a.z - b.z);
        for (const d of dots) {
          const v = d.v;
          const baseG = 140 + 115 * v;
          let rCol = baseG, gCol = baseG, bCol = baseG;
          if (v > 0.82) {
            const w = Math.min(1, ((v - 0.82) / 0.18) * 0.7);
            rCol += (255 - rCol) * w;
            gCol += (255 - gCol) * w;
            bCol += (255 - bCol) * w;
          }
          const alpha = (0.45 + 0.55 * d.glow) * mkO;
          ctx.fillStyle = `rgba(${rCol | 0},${gCol | 0},${bCol | 0},${alpha})`;
          ctx.beginPath();
          ctx.arc(d.x, d.y, Math.max(0.4, d.r), 0, TAU);
          ctx.fill();
        }
        ctx.restore();
      }

      // 2. Kinetic assembling characters with Chromatic Aberration RGB splits
      const textBaseX = startX + markSize + gap;
      for (let i = 0; i < WORD_STR.length; i++) {
        const j = JIT_OFFSETS[i];
        const a = eOut(clamp(seg(p, 0.04, 0.82) * 1.35 - j[2] * 0.35, 0, 1));
        const op = Math.min(1, a * 1.5);
        if (op < 0.02) continue;

        const chX = textBaseX + charOffsets[i] + j[0] * 56 * (1 - a);
        const chY = cy + j[1] * 30 * (1 - a);
        const sep = (1 - a) * 14;

        if (sep > 0.4) {
          // Red RGB aberration split
          ctx.save();
          ctx.globalAlpha = op * 0.85;
          ctx.fillStyle = "rgba(255, 64, 72, 0.85)";
          ctx.fillText(WORD_STR[i], chX - sep, chY);

          // Green/Cyan RGB aberration split
          ctx.fillStyle = "rgba(64, 255, 190, 0.8)";
          ctx.fillText(WORD_STR[i], chX + sep, chY);

          // Blue RGB aberration split
          ctx.fillStyle = "rgba(96, 124, 255, 0.8)";
          ctx.fillText(WORD_STR[i], chX, chY + sep * 0.55);
          ctx.restore();
        }

        // Main solid white character
        ctx.save();
        ctx.globalAlpha = op;
        ctx.fillStyle = "#ffffff";
        ctx.fillText(WORD_STR[i], chX, chY);
        ctx.restore();
      }

      ctx.restore();
    };

    const render = (now: number) => {
      if (!startTime) startTime = now;
      const elapsed = now - startTime;
      const p = Math.min(1, elapsed / DURATION);
      const t = elapsed / 1000;

      drawFrame(p, t);

      if (p >= 1 && !hasCompletedRef.current) {
        hasCompletedRef.current = true;
        onSettledRef.current();
      }

      // Continuous 60 FPS loop so the aura wave ripples forever through the dotted "A" mark
      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(animId);
      isAnimatingRef.current = false;
    };
  }, [isTriggered]);

  return (
    <div ref={hostRef} className="assembly-intro-kinetic-canvas-wrap">
      <canvas ref={canvasRef} className="assembly-intro-kinetic-canvas" />
    </div>
  );
}

export function TextIntroScene() {
  const isClient = useSyncExternalStore(emptySubscribe, () => true, () => false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isTriggered, setIsTriggered] = useState(false);
  const [isSettled, setIsSettled] = useState(false);
  const hasFiredTriggerRef = useRef(false);

  useEffect(() => {
    if (!isClient) return;
    if (hasFiredTriggerRef.current) return;
    const el = containerRef.current;
    if (!el) return;

    const scrollContainer =
      el.closest(".overflow-y-auto") ||
      document.querySelector(".assembly-app-shell .overflow-y-auto") ||
      document.querySelector(".overflow-y-auto");

    const fireOnce = () => {
      if (hasFiredTriggerRef.current) return;
      hasFiredTriggerRef.current = true;
      setIsTriggered(true);
      cleanup();
    };

    const checkVisibility = () => {
      if (hasFiredTriggerRef.current) return;
      const rect = el.getBoundingClientRect();
      const vh = window.innerHeight || document.documentElement.clientHeight;
      if (rect.top < vh * 0.85 && rect.bottom > vh * 0.10) {
        fireOnce();
      }
    };

    let observer: IntersectionObserver | null = null;
    if (typeof IntersectionObserver !== "undefined") {
      observer = new IntersectionObserver(
        (entries) => {
          const [entry] = entries;
          if (entry && entry.isIntersecting) {
            fireOnce();
          }
        },
        { threshold: 0.15 }
      );
      observer.observe(el);
    }

    const container = scrollContainer || window;
    container.addEventListener("scroll", checkVisibility, { passive: true });
    window.addEventListener("scroll", checkVisibility, { passive: true });

    checkVisibility();

    if (typeof window !== "undefined") {
      try {
        sessionStorage.removeItem("assembly_intro_seen");
      } catch {}
    }

    function cleanup() {
      if (observer) observer.disconnect();
      container.removeEventListener("scroll", checkVisibility);
      window.removeEventListener("scroll", checkVisibility);
    }

    return cleanup;
  }, [isClient]);

  if (!isClient) {
    return (
      <div
        className="shader-frame assembly-intro-frame"
        style={{ width: "100%", height: "100%", background: "#000000" }}
      />
    );
  }

  return (
    <div
      ref={containerRef}
      className={`shader-frame assembly-intro-frame ${isSettled ? "is-settled" : ""}`}
      style={{ width: "100%", height: "100%", position: "relative", background: "#000000", overflow: "hidden" }}
    >
      {/* 1. Background Layer: Rotating Concentric Typographic Vortex from Image 2 */}
      <div className="assembly-intro-vortex-layer" aria-label="Concentric typographic vortex">
        <TypographyVortexCanvas
          mode="dark"
          phrase={VORTEX_PHRASE}
          speed={1.0}
          ringGrowth={1.21}
          opacity={0.88}
          dissolveRadius={1.0}
          particleAmount={1.0}
          suctionDuration={920}
          guideLines={false}
        />
      </div>

      {/* 2. Center 3D Typographic Globe from Image 2 */}
      <div className="assembly-intro-globe-center" aria-hidden="true">
        <TextPathStudies
          variant="globe-study"
          mode="dark"
          scale={1.25}
          opacity={1.00}
          hue={0}
          saturation={1.00}
          brightness={1.00}
          style={{
            width: "100%",
            height: "100%",
            background: "transparent",
          }}
        />
      </div>

      {/* 3. Foreground Layer: Kinetic Chromatic Assembling Wordmark + Button */}
      <div className="assembly-intro-foreground-stage">
        <KineticAssemblyWordmark
          isTriggered={isTriggered}
          onSettled={() => setIsSettled(true)}
        />

        <div className={`assembly-intro-button-container ${isSettled ? "is-visible" : "is-hidden"}`}>
          <Link href="/chat" className="assembly-intro-button-link" aria-label="Start an investigation">
            <div className="assembly-intro-button-wrap">
              <RectangleButtons
                variant="dark-pill"
                mode="dark"
              >
                Start an investigation
              </RectangleButtons>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}
