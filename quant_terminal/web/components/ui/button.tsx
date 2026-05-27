import * as React from "react";
import { cn } from "@/lib/cn";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "ghost" | "outline" | "destructive";
  size?: "sm" | "md" | "lg";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", ...props }, ref) => {
    const base =
      "inline-flex items-center justify-center font-mono uppercase tracking-wider " +
      "border transition-colors focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed " +
      "rounded-none";
    const sizes = {
      sm: "h-7 px-2.5 text-xs",
      md: "h-9 px-4 text-sm",
      lg: "h-11 px-6 text-sm",
    } as const;
    const variants = {
      default:
        "bg-[var(--color-card)] border-[var(--color-border)] text-[var(--color-bone)] " +
        "hover:border-[var(--color-rule)] hover:bg-[var(--color-card-hover)]",
      ghost:
        "bg-transparent border-transparent text-[var(--color-bone-muted)] " +
        "hover:bg-[var(--color-card)] hover:text-[var(--color-bone)]",
      outline:
        "bg-transparent border-[var(--color-border)] text-[var(--color-bone)] " +
        "hover:border-[var(--color-rule)]",
      destructive:
        "bg-[var(--color-card)] border-[var(--color-mercury)] text-[var(--color-mercury)] " +
        "hover:bg-[var(--color-mercury)] hover:text-[var(--color-ink)]",
    } as const;
    return (
      <button
        ref={ref}
        className={cn(base, sizes[size], variants[variant], className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
