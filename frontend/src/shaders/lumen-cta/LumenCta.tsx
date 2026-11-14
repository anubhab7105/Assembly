import type { CSSProperties, ReactNode } from "react";

export type LumenCtaProps = {
  variant?: "primary" | "ghost";
  className?: string;
  style?: CSSProperties;
  mode?: "light" | "dark";
  children?: ReactNode;
  onClick?: () => void;
};

export function LumenCta({
  variant = "primary",
  className = "",
  style,
  mode = "dark",
  children = "Get started",
  onClick,
}: LumenCtaProps) {
  return (
    <button
      type="button"
      className={`lumen-cta lumen-cta--${variant} ${className}`.trim()}
      data-mode={mode}
      style={style}
      onClick={onClick}
    >
      <span>{children}</span>
    </button>
  );
}

