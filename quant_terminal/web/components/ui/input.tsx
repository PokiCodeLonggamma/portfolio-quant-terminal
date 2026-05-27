import * as React from "react";
import { cn } from "@/lib/cn";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full px-3 bg-[var(--color-card)] border border-[var(--color-border)] rounded-none",
        "font-mono text-sm text-[var(--color-bone)] placeholder:text-[var(--color-bone-dim)]",
        "focus:outline-none focus:border-[var(--color-rule)]",
        "disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => (
    <label
      ref={ref}
      className={cn(
        "font-mono text-xs uppercase tracking-widest text-[var(--color-bone-muted)] mb-1.5 block",
        className,
      )}
      {...props}
    />
  ),
);
Label.displayName = "Label";
