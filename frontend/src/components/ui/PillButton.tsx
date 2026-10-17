import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Icon } from "./Icon";

type PillVariant = "primary" | "secondary" | "accent";

const VARIANTS: Record<PillVariant, string> = {
  primary: "bg-primary-container hover:bg-primary-container/90 text-on-primary shadow-sm",
  secondary: "bg-surface-container hover:bg-surface-container-high text-on-surface",
  accent: "bg-sunflower hover:bg-secondary-container text-primary-container shadow-sm",
};

interface PillButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  variant?: PillVariant;
  /** Material Symbols icon shown before the label. */
  icon?: string;
  /** Show the round sunflower "→" badge used on "Next: …" CTAs. */
  arrow?: boolean;
  /** Render as a Next.js link instead of a button. */
  href?: string;
  children: ReactNode;
}

/** Fully rounded action pill (primary charcoal, secondary surface, accent sunflower). */
export function PillButton({
  variant = "primary",
  icon,
  arrow = false,
  href,
  className = "",
  children,
  type = "button",
  ...rest
}: PillButtonProps) {
  const classes = `group inline-flex w-fit items-center gap-2 ${arrow ? "pl-6 pr-2.5" : "px-5"} py-2.5 rounded-full font-body-md text-body-md font-medium tracking-tight transition-all hover:scale-[1.02] active:scale-[0.98] focus-halo disabled:opacity-50 disabled:pointer-events-none ${VARIANTS[variant]} ${className}`;

  const content = (
    <>
      {icon && <Icon name={icon} className="text-[18px]" />}
      <span>{children}</span>
      {arrow && (
        <span className="ml-1 w-6 h-6 rounded-full bg-secondary-container text-on-secondary-fixed flex items-center justify-center font-bold text-xs group-hover:translate-x-0.5 transition-transform">
          →
        </span>
      )}
    </>
  );

  if (href) {
    return (
      <Link href={href} className={classes}>
        {content}
      </Link>
    );
  }
  return (
    <button type={type} className={classes} {...rest}>
      {content}
    </button>
  );
}
