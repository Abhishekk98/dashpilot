import type { ButtonHTMLAttributes } from "react";

import { Icon } from "./Icon";

type IconButtonVariant = "glass" | "surface" | "dark" | "accent";
type IconButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<IconButtonVariant, string> = {
  glass: "bg-surface-container-lowest/80 backdrop-blur-xl text-on-surface hover:bg-surface-container",
  surface: "bg-surface-container-low text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
  dark: "bg-primary-container text-on-primary hover:bg-primary-container/90",
  accent: "bg-sunflower text-primary-container hover:bg-secondary-container",
};

// 32 / 40 / 44px: the three circle sizes used across the designs.
const SIZES: Record<IconButtonSize, { box: string; icon: string }> = {
  sm: { box: "w-8 h-8", icon: "text-[18px]" },
  md: { box: "w-10 h-10", icon: "text-[20px]" },
  lg: { box: "w-11 h-11", icon: "text-[22px]" },
};

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Material Symbols name; defaults to the ↗ "north_east" navigation arrow. */
  icon?: string;
  /** Required for accessibility since the button has no text. */
  label: string;
  variant?: IconButtonVariant;
  size?: IconButtonSize;
}

/** Circular icon button (↗ navigation circles, back arrows, notifications). */
export function IconButton({
  icon = "north_east",
  label,
  variant = "surface",
  size = "md",
  className = "",
  type = "button",
  children,
  ...rest
}: IconButtonProps) {
  const s = SIZES[size];
  return (
    <button
      type={type}
      aria-label={label}
      className={`relative ${s.box} rounded-full flex items-center justify-center transition-all duration-200 focus-halo ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      <Icon name={icon} className={s.icon} />
      {children}
    </button>
  );
}
