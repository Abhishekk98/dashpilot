import type { HTMLAttributes, ReactNode } from "react";

type CardVariant = "glass" | "dark" | "solid";

const VARIANTS: Record<CardVariant, string> = {
  // Level 1 frosted glass card (most cards in the designs)
  glass: "bg-surface-container-lowest/80 backdrop-blur-md shadow-card",
  // Level 3 charcoal utility card (e.g. "Pipeline Orchestration", "Profiler Schema Signal")
  dark: "bg-primary-container text-on-primary shadow-dark",
  // Opaque white, for cards nested on glass
  solid: "bg-surface-container-lowest shadow-card",
};

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  /** Lift the shadow on hover, as on the Home dashboard cards. */
  interactive?: boolean;
  /** Override the default 28px (p-7) interior padding. */
  padding?: string;
  children: ReactNode;
}

/** 28px-radius analytical card from DESIGN.md. */
export function Card({ variant = "glass", interactive = false, padding = "p-7", className = "", children, ...rest }: CardProps) {
  const hover = interactive ? "hover:shadow-card-hover transition-all duration-300" : "";
  return (
    <div className={`rounded-card ${padding} ${VARIANTS[variant]} ${hover} ${className}`} {...rest}>
      {children}
    </div>
  );
}
