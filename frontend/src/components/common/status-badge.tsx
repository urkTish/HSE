import { Archive, Ban, CheckCircle2, CircleDashed, Clock, Lock, PauseCircle, XCircle } from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { Badge, type BadgeProps } from "@/components/ui/badge";

type Tone = NonNullable<BadgeProps["tone"]>;
const MAP: Record<string, { tone: Tone; Icon: ComponentType<SVGProps<SVGSVGElement>> }> = {
  active: { tone: "success", Icon: CheckCircle2 },
  approved: { tone: "success", Icon: CheckCircle2 },
  success: { tone: "success", Icon: CheckCircle2 },
  planning: { tone: "info", Icon: CircleDashed },
  draft: { tone: "info", Icon: CircleDashed },
  invited: { tone: "info", Icon: Clock },
  pending_approval: { tone: "info", Icon: Clock },
  on_hold: { tone: "warning", Icon: PauseCircle },
  temporarily_closed: { tone: "warning", Icon: PauseCircle },
  suspended: { tone: "warning", Icon: PauseCircle },
  locked: { tone: "warning", Icon: Lock },
  denied: { tone: "warning", Icon: Ban },
  closed: { tone: "neutral", Icon: Archive },
  archived: { tone: "neutral", Icon: Archive },
  inactive: { tone: "neutral", Icon: Archive },
  demobilised: { tone: "neutral", Icon: Archive },
  deactivated: { tone: "neutral", Icon: XCircle },
  blacklisted: { tone: "danger", Icon: Ban },
  failed: { tone: "danger", Icon: XCircle },
};

/** Status shown with colour + icon + text (never colour alone). */
export function StatusBadge({ status, label }: { status: string; label: string }) {
  const { tone, Icon } = MAP[status] ?? { tone: "neutral" as Tone, Icon: CircleDashed };
  return (
    <Badge tone={tone} data-status={status}>
      <Icon aria-hidden />
      {label}
    </Badge>
  );
}
