"use client";

import { useSyncExternalStore } from "react";
import { TypographyVortexCanvas, TextPathStudies } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

const emptySubscribe = () => () => {};

const ASSEMBLY_VORTEX_PHRASE = [
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

export function Scene() {
  const isClient = useSyncExternalStore(emptySubscribe, () => true, () => false);

  if (!isClient) {
    return <div className="shader-frame" style={{ position: "relative", width: "100%", height: "100%", background: "#0a0a0c" }} />;
  }

  return (
    <div className="shader-frame" style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}>
      <TypographyVortexCanvas
        mode="dark"
        phrase={ASSEMBLY_VORTEX_PHRASE}
        speed={1.00}
        ringGrowth={1.21}
        opacity={1.00}
        dissolveRadius={1.00}
        particleAmount={1.00}
        suctionDuration={920}
        guideLines={false}
      />
      <div
        className="assembly-orb-center"
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "clamp(60px, 7.5vw, 114px)",
          height: "clamp(60px, 7.5vw, 114px)",
          borderRadius: "50%",
          overflow: "hidden",
          zIndex: 10,
          pointerEvents: "auto",
        }}
      >
        <TextPathStudies
          variant="globe-study"
          mode="dark"
          scale={1.16}
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
    </div>
  );
}

