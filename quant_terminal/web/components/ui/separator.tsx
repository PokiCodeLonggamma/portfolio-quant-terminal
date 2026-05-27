import * as React from "react";
import { cn } from "@/lib/cn";

type Props = React.HTMLAttributes<HTMLDivElement> & { orientation?: "horizontal" | "vertical" };

export const Separator = ({ className, orientation = "horizontal", ...props }: Props) => (
  <div
    role="separator"
    aria-orientation={orientation}
    className={cn(
      orientation === "horizontal" ? "h-px w-full" : "w-px h-full",
      "bg-[var(--color-border)]",
      className,
    )}
    {...props}
  />
);
