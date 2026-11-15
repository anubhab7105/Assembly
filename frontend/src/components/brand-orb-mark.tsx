"use client";

import React, { useEffect, useRef } from "react";

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
const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const rscale = (S: number) => Math.pow(S / 300, 0.6);

const proj = (yaw: number, tilt: number, cx: number, cy: number, s: number) => {
  const st = Math.sin(tilt), ct = Math.cos(tilt);
  const sy = Math.sin(yaw), cyw = Math.cos(yaw);
  return (x: number, y: number, z: number): [number, number, number] => {
    const px = x * cyw + z * sy, pz = -x * sy + z * cyw;
    const py = y * ct - pz * st, z2 = y * st + pz * ct;
    return [cx + px * s, cy - py * s, z2];
  };
};

function paintAura(
  ctx: CanvasRenderingContext2D,
  dots: Array<{ x: number; y: number; z: number; r: number; v: number; glow: number; a?: number }>,
  accentColor: [number, number, number] | null,
  rMin: number
) {
  dots.sort((a, b) => a.z - b.z);
  for (const d of dots) {
    const v = clamp01(d.v);
    const glow = d.glow;

    if (accentColor) {
      // Dark dots on light surfaces: rich, dark, high-contrast pitch black
      const alpha = 0.78 + 0.22 * glow;
      ctx.fillStyle = `rgba(${accentColor[0]},${accentColor[1]},${accentColor[2]},${alpha})`;
    } else {
      // Bright glowing dots on dark surfaces
      const baseG = 180 + 75 * v;
      let r = baseG, gg = baseG, b = baseG;
      if (v > 0.7) {
        const w = Math.min(1, ((v - 0.7) / 0.3) * 0.9);
        r += (255 - r) * w;
        gg += (255 - gg) * w;
        b += (255 - b) * w;
      }
      const alpha = 0.68 + 0.32 * glow;
      ctx.fillStyle = `rgba(${r | 0},${gg | 0},${b | 0},${alpha})`;
    }

    ctx.beginPath();
    ctx.arc(d.x, d.y, Math.max(rMin, d.r * 1.25), 0, TAU);
    ctx.fill();
  }
}

function drawAura(
  ctx: CanvasRenderingContext2D,
  S: number,
  t: number,
  accentColor: [number, number, number] | null = null,
  mini = false
) {
  const cx = S / 2, cy = S / 2, R = (S / 2) * 0.76;
  const rs = rscale(S) * (mini ? 1.8 : 1);
  const p = proj(0.14 * Math.sin(t * 0.36), 0.12 * Math.sin(t * 0.28), cx, cy, R);

  /* Authentic ThreeUI aura ripple travels outward through the field */
  const ring = (((t * 0.32) % 1 + 1) % 1) * 2.2 - 0.2;
  const dots: Array<{ x: number; y: number; z: number; r: number; v: number; glow: number; a?: number }> = [];

  for (let i = 0; i < AURA_DOTS.length; i++) {
    const [gx, gy, gr] = AURA_DOTS[i];
    const d0 = Math.hypot(gx, gy);
    const glow = Math.exp(-Math.pow(d0 - ring, 2) / 0.045);
    const [x, y, z] = p(gx, -gy, 0);
    const dep = (z + 1) / 2;
    dots.push({
      x,
      y,
      z,
      r: Math.max(0.65, gr * R * 1.1) + (0.22 * dep + 0.65 * glow) * rs,
      v: 0.5 + 0.12 * dep + 0.38 * glow,
      glow,
    });
  }

  paintAura(ctx, dots, accentColor, mini ? 1.0 : 0.8);
}

export function BrandDottedAMark({
  className = "",
  style,
  size = 32,
  darkColor,
}: {
  className?: string;
  style?: React.CSSProperties;
  size?: number | string;
  darkColor?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const S = typeof size === "number" ? size : 32;

    canvas.width = Math.round(S * dpr);
    canvas.height = Math.round(S * dpr);

    const getAccent = (): [number, number, number] | null => {
      if (typeof window !== "undefined" && window.location.pathname.startsWith("/science")) {
        return null; // Always bright luminous white on /science pitch-black hero
      }
      const isSciencePage = Boolean(canvas.closest(".assembly-science-page"));
      if (isSciencePage) return null;

      const isLightMode = typeof document !== "undefined" && !document.documentElement.classList.contains("dark");
      if (isLightMode) {
        return [0, 0, 0]; // Full pitch black in Day mode
      }

      const isTopHeader = Boolean(canvas.closest(".assembly-landing-header.is-top"));
      const isHeaderScrolled = Boolean(canvas.closest(".assembly-landing-header.is-scrolled"));
      const useDark = darkColor || (isTopHeader && !isHeaderScrolled);
      return useDark ? [0, 0, 0] : null;
    };

    // Paint initial frame synchronously so mark is visible immediately without waiting for rAF
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, S, S);
    drawAura(ctx, S, 0, getAccent(), S < 28);

    const render = (timeMs: number) => {
      const t = timeMs / 1000;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, S, S);

      drawAura(ctx, S, t, getAccent(), S < 28);
      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animId);
  }, [size, darkColor]);

  const dimension = typeof size === "number" ? `${size}px` : size;

  return (
    <span
      className={`assembly-wordmark-dotted-a inline-flex items-center justify-center shrink-0 ${className}`}
      style={{
        width: dimension,
        height: dimension,
        lineHeight: 1,
        pointerEvents: "none",
        ...style,
      }}
      aria-hidden="true"
    >
      <canvas
        ref={canvasRef}
        style={{
          width: dimension,
          height: dimension,
          display: "block",
          background: "transparent",
          pointerEvents: "none",
        }}
      />
    </span>
  );
}

// Backwards-compatible alias for existing imports
export const BrandOrbMark = BrandDottedAMark;
