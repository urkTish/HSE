import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium [&_svg]:size-3.5", {
  variants: {
    tone: {
      success: "border-success/25 bg-success-bg text-success",
      warning: "border-warning/25 bg-warning-bg text-warning",
      danger: "border-danger/25 bg-danger-bg text-danger",
      info: "border-info/25 bg-info-bg text-info",
      neutral: "border-neutral/25 bg-neutral-bg text-neutral",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
