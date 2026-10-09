"use client";
import { AlertTriangle, CheckCircle2, Circle, CircleDashed, CircleDot, Clock, Droplets, Lock, OctagonAlert, PauseCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { StatusBadge } from "@/components/common/status-badge";
import { PossibleIdHint } from "@/components/common/api-warnings";
import { Code, StepDialog, SubNav } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import type { Schemas } from "@/lib/api/client";
import { useHeatRefresh } from "@/lib/api/heat";
import { can, canWrite } from "@/lib/permissions";
import { REST_MIN } from "@/lib/heat-enums";
import { cn } from "@/lib/utils";
import { utcToZonedInput } from "@/lib/datetime";

type S = Schemas;

/* ───────────── capabilities (6b §5.13, 166–177) ───────────── */

export function useHeatCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  const roles = me.projects.find((p) => p.project_id === pid)?.roles ?? [];
  return {
    view: can(me, "heat.view", pid),
    record: canWrite(me, "heat_reading.record", pid),
    manage: canWrite(me, "heat_register.manage", pid),
    welfare: canWrite(me, "heat_welfare.record", pid),
    patrol: canWrite(me, "heat_patrol.record", pid),
    exempt: canWrite(me, "heat_exemption.grant", pid),
    plan: canWrite(me, "heat_plan.manage", pid),
    log: can(me, "heat_log.view", pid),
    kpi: can(me, "heat_kpi.view", pid),
    settings: canWrite(me, "heat_settings.edit", pid),
    void: canWrite(me, "heat.void", pid),
    /** HI-4: the review is the HSE Manager's or an HSE Officer's (the backend checks the role). */
    reviewer: me.is_hse_manager || roles.includes("hse_officer"),
  };
}

/* ───────────── sub navigation ───────────── */

export function HeatFieldSubNav() {
  const t = useTranslations("heat.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/heat-board", label: t("board"), testId: "sub-heat-board" },
        { href: "/wbgt-readings", label: t("readings"), testId: "sub-heat-readings" },
        { href: "/heat-welfare-checks", label: t("welfare"), testId: "sub-heat-welfare" },
        { href: "/heat-duty-list", label: t("duty"), testId: "sub-heat-duty" },
        { href: "/acclimatisation-plans", label: t("plans"), testId: "sub-heat-plans" },
        { href: "/heat-actions", label: t("actions"), show: can(me, "heat_kpi.view"), testId: "sub-heat-actions" },
      ]}
    />
  );
}

export function HeatBanSubNav() {
  const t = useTranslations("heat.nav");
  return (
    <SubNav
      items={[
        { href: "/ban-patrols", label: t("patrols"), testId: "sub-heat-patrols" },
        { href: "/ban-exemptions", label: t("exemptions"), testId: "sub-heat-exemptions" },
      ]}
    />
  );
}

export function HeatSetupSubNav() {
  const t = useTranslations("heat.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/heat-instruments", label: t("instruments"), testId: "sub-heat-instruments" },
        { href: "/monitoring-points", label: t("points"), testId: "sub-heat-points" },
        { href: "/rest-stations", label: t("stations"), testId: "sub-heat-stations" },
        { href: "/heat-settings", label: t("settings"), show: can(me, "heat.view"), testId: "sub-heat-settings" },
      ]}
    />
  );
}

export function HeatReportSubNav() {
  const t = useTranslations("heat.nav");
  return (
    <SubNav
      items={[
        { href: "/heat-stress", label: t("kpis"), testId: "sub-heat-kpis" },
        { href: "/heat-season-report", label: t("report"), testId: "sub-heat-report" },
      ]}
    />
  );
}

/* ───────────── regime and state ───────────── */

const REGIME_TONE: Record<S["Regime"], "success" | "info" | "warning" | "danger" | "neutral"> = {
  R0: "success",
  R1: "info",
  R2: "warning",
  R3: "warning",
  R4: "danger",
  unknown: "neutral",
};
const REGIME_ICON = { R0: CheckCircle2, R1: Clock, R2: PauseCircle, R3: AlertTriangle, R4: OctagonAlert, unknown: CircleDashed } as const;

/** Regime (R0…R4) with colour, icon and words; never colour alone. `short` shows the code and the work/rest split only. */
export function RegimeBadge({ regime, short, code, className }: { regime: S["Regime"] | null | undefined; short?: boolean; code?: boolean; className?: string }) {
  const te = useTranslations("enums");
  if (!regime) return <span>—</span>;
  const Icon = REGIME_ICON[regime];
  // `code`: the bare regime code (R0…R4) for dense grids; the full label is the tooltip and accessible name.
  const full = te(`regime.${regime}`);
  return (
    <Badge tone={REGIME_TONE[regime]} className={className} data-testid="regime" data-regime={regime} title={code ? full : undefined} aria-label={code ? full : undefined}>
      <Icon aria-hidden />
      {code ? (regime === "unknown" ? te("regimeShort.unknown") : regime) : short ? te(`regimeShort.${regime}`) : <RegimeWords label={full} />}
    </Badge>
  );
}

/**
 * "R2 · 30 work / 30 rest" with the code isolated: in Arabic the bidi algorithm otherwise glued "R2 · 30" into one
 * left-to-right run and moved the work minutes next to the code ("30 · R2 عمل / 30 راحة").
 */
function RegimeWords({ label }: { label: string }) {
  const i = label.indexOf(" · ");
  if (i < 0) return <>{label}</>;
  return (
    <span>
      <bdi>{label.slice(0, i)}</bdi>
      {label.slice(i)}
    </span>
  );
}

const REGIME_PANEL: Record<S["Regime"], string> = {
  R0: "border-success/40 bg-success-bg text-success",
  R1: "border-info/40 bg-info-bg text-info",
  R2: "border-warning/50 bg-warning-bg text-warning",
  R3: "border-warning/70 bg-warning-bg text-warning",
  R4: "border-danger/60 bg-danger-bg text-danger",
  unknown: "border-neutral/40 bg-neutral-bg text-neutral",
};

/** The regime a supervisor acts on, sized for a phone in the sun: icon, code and work/rest split large, the rest minutes under it. */
export function HeadlineRegime({ regime, minutes, caption }: { regime: S["Regime"]; minutes?: number | null; caption: string }) {
  const te = useTranslations("enums");
  const Icon = REGIME_ICON[regime];
  return (
    <div className={cn("flex items-center gap-3 rounded-md border-2 px-3 py-2", REGIME_PANEL[regime])} data-testid="headline-regime" data-regime={regime}>
      <Icon aria-hidden className="size-8 shrink-0" strokeWidth={2.25} />
      <div className="flex min-w-0 flex-col">
        <span className="text-xs font-medium opacity-90">{caption}</span>
        <span className="text-lg font-bold leading-snug">
          <RegimeWords label={te(`regime.${regime}`)} />
        </span>
        <RestMinutes regime={regime} minutes={minutes} className="text-sm font-medium text-current" />
      </div>
    </div>
  );
}

/** Radio mark for the large answer buttons: the choice reads from the shape (empty / dotted), not from the fill colour alone. */
export function ChoiceMark({ on }: { on: boolean }) {
  return on ? <CircleDot aria-hidden className="size-5" /> : <Circle aria-hidden className="size-5 opacity-50" />;
}

/** Rest minutes per hour for a regime (server value when given, §6.2 otherwise). */
export function RestMinutes({ regime, minutes, className }: { regime: S["Regime"]; minutes?: number | null; className?: string }) {
  const t = useTranslations("heat.common");
  const m = minutes ?? REST_MIN[regime];
  if (m === null || m === undefined) return null;
  return <span className={cn("text-xs text-muted-foreground", className)}>{regime === "R4" ? t("stopWork") : m === 0 ? t("normalBreaks") : t("restPerHour", { n: m })}</span>;
}

const STATE_TONE: Record<S["HeatStateKind"], string> = { current: "valid", stale: "expiring", unknown: "unplanned" };

export function HeatStateBadge({ state }: { state: S["HeatStateKind"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="heat-state" data-state={state}>
      <StatusBadge status={STATE_TONE[state]} label={te(`heatState.${state}`)} />
    </span>
  );
}

const PLAN_TONE: Record<S["PlanStatus"], string> = {
  planned: "planned",
  waiting_restriction: "on_hold",
  active: "in_progress",
  completed: "completed",
  interrupted: "missed",
  cancelled: "cancelled",
};

export function PlanStatusBadge({ status }: { status: S["PlanStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="plan-status" data-status={status}>
      <StatusBadge status={PLAN_TONE[status]} label={te(`planStatus.${status}`)} />
    </span>
  );
}

export function RecordStatusBadge({ status }: { status: S["RecordStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="record-status" data-status={status}>
      <StatusBadge status={status} label={te(`heatRecordStatus.${status}`)} />
    </span>
  );
}

/** WBGT value in °C, always left-to-right inside RTL pages (AC61). */
export function Wbgt({ v, className }: { v: string | null | undefined; className?: string }) {
  if (v === null || v === undefined) return <span>—</span>;
  return <bdi className={cn("ltr tabular-nums", className)}>{v} °C</bdi>;
}

export function Codes({ items }: { items: string[] | null | undefined }) {
  if (!items?.length) return <span>—</span>;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {items.map((c) => (
        <Code key={c} className="rounded bg-surface px-1 text-xs">
          {c}
        </Code>
      ))}
    </span>
  );
}

/** Water advice (list RGM: "Drink 1 cup … every 15–20 minutes") in the page language, from the server. */
export function WaterAdvice({ en, ar }: { en: string; ar: string }) {
  const locale = useLocale();
  return (
    <p className="flex items-start gap-2 rounded-md border border-info/30 bg-info-bg px-3 py-2 text-sm text-info" data-testid="water-advice">
      <Droplets aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span>{locale === "ar" ? ar : en}</span>
    </p>
  );
}

/** Heat-illness entries are sensitive health data (P6b-1/P6b-2): the note says each view is recorded. */
export function SensitiveNote({ children }: { children?: ReactNode }) {
  const t = useTranslations("heat.common");
  return (
    <p className="mb-3 flex w-fit max-w-full items-start gap-2 rounded-md border border-input/70 bg-surface px-3 py-1.5 text-xs" data-testid="heat-sensitive-note">
      <Lock aria-hidden className="mt-px size-3.5 shrink-0 text-muted-foreground" />
      <span>
        <span className="font-medium">{t("sensitive")}</span> {children}
      </span>
    </p>
  );
}

export function FreeText({ children, className, testId }: { children: string | null | undefined; className?: string; testId?: string }) {
  if (!children) return null;
  return (
    <span dir="auto" className={className} data-testid={testId}>
      {children}
    </span>
  );
}

/** Reason ≥ min characters (void, revoke, cancel, re-open). */
export function HeatReasonDialog({
  title,
  description,
  confirmLabel,
  min = 20,
  destructive = true,
  onConfirm,
  onClose,
}: {
  title: string;
  description?: string;
  confirmLabel: string;
  min?: number;
  destructive?: boolean;
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const t = useTranslations("heat.common");
  const refresh = useHeatRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      destructive={destructive}
      dismissLabel={t("back")}
      disabled={reason.trim().length < min}
      testId="heat-reason-confirm"
      onConfirm={async () => {
        await onConfirm(reason.trim());
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="heat-reason" label={t("reason")} required hint={t("reasonMin", { min, n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="heat-reason" />
      </FormField>
      <PossibleIdHint text={reason} />
    </StepDialog>
  );
}

/** Datetime-local input value for now in the project zone (the e2e clock shifts Date). */
export function nowLocalInput(): string {
  return utcToZonedInput(new Date().toISOString());
}
