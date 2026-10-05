import * as React from "react";
import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const tones = {
  danger: { cls: "border-danger/30 bg-danger-bg text-danger", Icon: AlertCircle },
  warning: { cls: "border-warning/30 bg-warning-bg text-warning", Icon: TriangleAlert },
  success: { cls: "border-success/30 bg-success-bg text-success", Icon: CheckCircle2 },
  info: { cls: "border-info/30 bg-info-bg text-info", Icon: Info },
} as const;

export function Alert({
  tone = "info",
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { tone?: keyof typeof tones }) {
  const { cls, Icon } = tones[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-2 rounded-md border p-3 text-sm", cls, className)} {...props}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
