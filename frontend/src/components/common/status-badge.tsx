import { AlertTriangle, Archive, Ban, CheckCircle2, CircleDashed, Clock, Hourglass, Loader, Lock, PauseCircle, Search, ShieldCheck, XCircle } from "lucide-react";
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
  // Phase 1
  submitted: { tone: "info", Icon: Clock },
  verified: { tone: "success", Icon: ShieldCheck },
  reported: { tone: "info", Icon: Clock },
  under_investigation: { tone: "info", Icon: Search },
  pending_review: { tone: "warning", Icon: Hourglass },
  actions_pending: { tone: "warning", Icon: Hourglass },
  voided: { tone: "neutral", Icon: XCircle },
  open: { tone: "warning", Icon: CircleDashed },
  action_raised: { tone: "info", Icon: Clock },
  planned: { tone: "info", Icon: Clock },
  completed: { tone: "success", Icon: CheckCircle2 },
  missed: { tone: "danger", Icon: AlertTriangle },
  cancelled: { tone: "neutral", Icon: XCircle },
  in_progress: { tone: "info", Icon: Loader },
  pending_verification: { tone: "warning", Icon: Hourglass },
  generating: { tone: "info", Icon: Loader },
  reviewed: { tone: "info", Icon: ShieldCheck },
  published: { tone: "success", Icon: CheckCircle2 },
  validated: { tone: "info", Icon: ShieldCheck },
  committed: { tone: "success", Icon: CheckCircle2 },
  discarded: { tone: "neutral", Icon: XCircle },
  expired: { tone: "danger", Icon: AlertTriangle },
  provisional: { tone: "warning", Icon: Hourglass },
  confirmed: { tone: "success", Icon: CheckCircle2 },
  due: { tone: "warning", Icon: Clock },
  done: { tone: "success", Icon: CheckCircle2 },
  overdue: { tone: "danger", Icon: AlertTriangle },
  requested: { tone: "info", Icon: Clock },
  rejected: { tone: "danger", Icon: XCircle },
  ok: { tone: "success", Icon: CheckCircle2 },
  warning: { tone: "warning", Icon: AlertTriangle },
  error: { tone: "danger", Icon: XCircle },
  on_time: { tone: "success", Icon: CheckCircle2 },
  late: { tone: "warning", Icon: Clock },
  pending: { tone: "info", Icon: Hourglass },
  unplanned: { tone: "neutral", Icon: CircleDashed },
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
