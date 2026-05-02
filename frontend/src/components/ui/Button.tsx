import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "tertiary" | "trading-rise" | "trading-fall" | "subscribe" | "pill";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  icon?: ReactNode;
  children?: ReactNode;
}

const variantClass: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-primary text-brand-ink font-semibold rounded-md h-10 px-6 hover:bg-brand-primary-active disabled:bg-brand-primary-disabled disabled:text-text-muted",
  secondary:
    "bg-surface-card text-text-on-dark rounded-md h-10 px-6 border border-hairline hover:bg-surface-elevated",
  tertiary:
    "bg-transparent text-text-body font-semibold rounded-md h-10 px-4 hover:text-text-on-dark",
  "trading-rise":
    "bg-trading-rise text-text-on-dark rounded-sm h-8 px-5 font-semibold text-sm",
  "trading-fall":
    "bg-trading-fall text-text-on-dark rounded-sm h-8 px-5 font-semibold text-sm",
  subscribe:
    "bg-brand-primary text-brand-ink font-semibold rounded-sm h-7 px-4 text-sm hover:bg-brand-primary-active",
  pill:
    "bg-brand-primary text-brand-ink font-semibold rounded-pill px-8 py-3.5 hover:bg-brand-primary-active"
};

const sizeClass = { sm: "text-xs px-3 h-7", md: "" };

export function Button({ variant = "primary", size = "md", icon, children, className = "", ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 transition-colors ${variantClass[variant]} ${size !== "md" ? sizeClass[size] : ""} ${className}`}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}
