"use client";
import { CheckCircle2, Lock, OctagonAlert, Siren, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { StatusBadge } from "@/components/common/status-badge";
import { PossibleIdHint } from "@/components/common/api-warnings";
import { Code, StepDialog, SubNav } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { ChoiceMark } from "@/components/heat/common";
import type { Schemas } from "@/lib/api/client";
import { useEmergencyReference, useEmergencyRefresh } from "@/lib/api/emergency";
import { can, canWrite } from "@/lib/permissions";
import { utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { cn } from "@/lib/utils";

type S = Schemas;

/* ───────────── capabilities (6c §5.13, 178–190) ───────────── */

export function useEmCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  const roles = me.projects.find((p) => p.project_id === pid)?.roles ?? [];
  const hseStaff = me.is_hse_manager || roles.includes("hse_officer");
  return {
    view: can(me, "emergency.view", pid),
    prepare: canWrite(me, "erp.prepare", pid),
    approve: canWrite(me, "erp.approve", pid),
    roster: canWrite(me, "emergency_roster.manage", pid),
    assets: canWrite(me, "emergency_asset.manage", pid),
    check: canWrite(me, "emergency_check.record", pid),
    plan: canWrite(me, "drill.plan", pid),
    run: canWrite(me, "drill.run", pid),
    evaluate: canWrite(me, "drill.evaluate", pid),
    declare: canWrite(me, "emergency.declare", pid),
    allClear: canWrite(me, "emergency.all_clear", pid),
    /** EV-5: the review is 188 without the site engineers (S = All Clear only); the backend checks the role. */
    review: canWrite(me, "emergency.all_clear", pid) && hseStaff,
    kpi: can(me, "emergency_kpi.view", pid),
    void: canWrite(me, "emergency.void", pid),
    hseStaff,
  };
}

/* ───────────── sub navigation ───────────── */

export function EmPlanSubNav() {
  const t = useTranslations("emergency.nav");
  return (
    <SubNav
      items={[
        { href: "/emergency-plans", label: t("erps"), testId: "sub-em-erps" },
        { href: "/assembly-points", label: t("aps"), testId: "sub-em-aps" },
        { href: "/emergency-contacts", label: t("contacts"), testId: "sub-em-contacts" },
        { href: "/emergency-zone-profiles", label: t("profiles"), testId: "sub-em-profiles" },
        { href: "/muster-devices", label: t("devices"), testId: "sub-em-devices" },
        { href: "/emergency-info", label: t("info"), testId: "sub-em-info" },
        { href: "/emergency-settings", label: t("settings"), testId: "sub-em-settings" },
      ]}
    />
  );
}

export function EmOrgSubNav() {
  const t = useTranslations("emergency.nav");
  return (
    <SubNav
      items={[
        { href: "/emergency-roster", label: t("roster"), testId: "sub-em-roster" },
        { href: "/emergency-coverage", label: t("coverage"), testId: "sub-em-coverage" },
        { href: "/rescue-teams", label: t("teams"), testId: "sub-em-teams" },
      ]}
    />
  );
}

export function EmAssetSubNav() {
  const t = useTranslations("emergency.nav");
  return (
    <SubNav
      items={[
        { href: "/emergency-assets", label: t("assets"), testId: "sub-em-assets" },
        { href: "/emergency-asset-checks", label: t("checks"), testId: "sub-em-checks" },
      ]}
    />
  );
}

export function EmDrillSubNav() {
  const t = useTranslations("emergency.nav");
  return (
    <SubNav
      items={[
        { href: "/drills", label: t("drills"), testId: "sub-em-drills" },
        { href: "/drill-programme", label: t("programme"), testId: "sub-em-programme" },
      ]}
    />
  );
}

export function EmReportSubNav() {
  const t = useTranslations("emergency.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/emergency-board", label: t("board"), testId: "sub-em-board" },
        { href: "/emergency-actions", label: t("actions"), show: can(me, "emergency_kpi.view"), testId: "sub-em-actions" },
        { href: "/emergency-kpis", label: t("kpis"), show: can(me, "emergency_kpi.view"), testId: "sub-em-kpis" },
      ]}
    />
  );
}

/* ───────────── reference lists (ES, DT, AG, EOR, EAT, EC, DC, FC, MS, UR, response types) ───────────── */

type RefList = keyof S["EmergencyReference"];

/** Labels of the seeded 6c reference lists in the page language (server EN/AR); the code while loading. */
export function useEmRef() {
  const q = useEmergencyReference();
  const ar = useLocale() === "ar";
  const label = useCallback(
    (list: RefList, code: string | null | undefined): string => {
      if (!code) return "—";
      const item = q.data?.[list]?.find((x) => x.code === code);
      return item ? (ar ? item.label_ar : item.label_en) : code;
    },
    [q.data, ar],
  );
  const items = useCallback((list: RefList): S["EmRefItem"][] => q.data?.[list] ?? [], [q.data]);
  return { label, items, ready: Boolean(q.data) };
}

/* ───────────── badges (colour + icon + words) ───────────── */

const ERP_TONE: Record<S["ErpStatus"], string> = { draft: "draft", submitted: "submitted", approved: "approved", superseded: "superseded" };
export function ErpStatusBadge({ status }: { status: S["ErpStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="erp-status" data-status={status}>
      <StatusBadge status={ERP_TONE[status]} label={te(`emErpStatus.${status}`)} />
    </span>
  );
}

export function ActiveBadge({ active }: { active: boolean }) {
  const te = useTranslations("enums");
  return <StatusBadge status={active ? "active" : "inactive"} label={te(`emActiveStatus.${active ? "active" : "inactive"}`)} />;
}

const ASSET_TONE: Record<S["AssetStatus"], string> = { in_service: "in_service", out_of_service: "out_of_service", missing: "missing", retired: "retired" };
export function AssetStatusBadge({ status }: { status: S["AssetStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="asset-status" data-status={status}>
      <StatusBadge status={ASSET_TONE[status]} label={te(`emAssetStatus.${status}`)} />
    </span>
  );
}

/** Ready / not ready with the reason codes in words (EA-5): never colour alone. */
export function ReadyBadge({ ready, reasons }: { ready: boolean; reasons?: string[] }) {
  const t = useTranslations("emergency.common");
  const te = useTranslations("enums");
  return (
    <span className="inline-flex flex-col gap-1" data-testid="ready" data-ready={ready ? "yes" : "no"}>
      <Badge tone={ready ? "success" : "danger"}>
        {ready ? <CheckCircle2 aria-hidden /> : <XCircle aria-hidden />}
        {ready ? t("ready") : t("notReady")}
      </Badge>
      {!ready && reasons?.length ? (
        <span className="flex flex-wrap gap-1 text-xs text-muted-foreground">
          {reasons.map((r) => (
            <span key={r} data-testid="ready-reason" data-code={r}>
              {te.has(`emNotReady.${r}` as never) ? te(`emNotReady.${r}` as never) : r}
            </span>
          ))}
        </span>
      ) : null}
    </span>
  );
}

const DRILL_TONE: Record<S["DrillStatus"], string> = { planned: "planned", in_progress: "in_progress", conducted: "done", evaluated: "verified", cancelled: "cancelled", voided: "voided" };
export function DrillStatusBadge({ status }: { status: S["DrillStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="drill-status" data-status={status}>
      <StatusBadge status={DRILL_TONE[status]} label={te(`emDrillStatus.${status}`)} />
    </span>
  );
}

export function DrillResultBadge({ result }: { result: S["DrillResult"] | null | undefined }) {
  const te = useTranslations("enums");
  if (!result) return <span>—</span>;
  return (
    <span data-testid="drill-result" data-result={result}>
      <StatusBadge status={result === "satisfactory" ? "passed" : "failed"} label={te(`emDrillResult.${result}`)} />
    </span>
  );
}

export function EventStatusBadge({ status }: { status: S["EventStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="event-status" data-status={status}>
      {status === "active" ? (
        <Badge tone="danger">
          <Siren aria-hidden />
          {te("emEventStatus.active")}
        </Badge>
      ) : (
        <StatusBadge status={status === "all_clear" ? "cleared" : status} label={te(`emEventStatus.${status}`)} />
      )}
    </span>
  );
}

const MUSTER_TONE: Record<S["MusterStatus"], string> = { open: "open", reconciled: "validated", closed: "closed", voided: "voided" };
export function MusterStatusBadge({ status }: { status: S["MusterStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="muster-status" data-status={status}>
      <StatusBadge status={MUSTER_TONE[status]} label={te(`emMusterStatus.${status}`)} />
    </span>
  );
}

const LINE_TONE: Record<S["LineStatus"], string> = { due: "due", overdue: "overdue", satisfied: "done", retired: "inactive" };
export function LineStatusBadge({ status }: { status: S["LineStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="line-status" data-status={status}>
      <StatusBadge status={LINE_TONE[status]} label={te(`emLineStatus.${status}`)} />
    </span>
  );
}

const COVER_TONE: Record<S["CoverageState"], string> = { covered: "met", short: "not_met", not_required: "not_required" };
export function CoverageBadge({ state }: { state: S["CoverageState"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="coverage-state" data-state={state}>
      <StatusBadge status={COVER_TONE[state]} label={te(`emCoverageState.${state}`)} />
    </span>
  );
}

const ENTRY_TONE: Record<S["EntryState"], string> = { expected: "pending", accounted: "done", unaccounted: "missing", resolved: "cleared" };
export function EntryStateBadge({ state }: { state: S["EntryState"] }) {
  const { label } = useEmRef();
  return (
    <span data-testid="entry-state" data-state={state}>
      <StatusBadge status={ENTRY_TONE[state]} label={label("entry_states", state)} />
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const te = useTranslations("enums");
  const tone = severity === "critical" ? "danger" : severity === "major" ? "warning" : "info";
  return (
    <Badge tone={tone} data-testid="finding-severity" data-severity={severity}>
      {severity === "critical" ? <OctagonAlert aria-hidden /> : null}
      {te.has(`emSeverity.${severity}` as never) ? te(`emSeverity.${severity}` as never) : severity}
    </Badge>
  );
}

/* ───────────── small displays ───────────── */

/** Minutes as the server sends them (1 dp), against a target; "—" when missing (EV-7: never estimated). */
export function Minutes({ v, target, testId }: { v: string | null | undefined; target?: number | string | null; testId?: string }) {
  const t = useTranslations("emergency.common");
  if (v === null || v === undefined) return <span data-testid={testId}>—</span>;
  const over = target !== null && target !== undefined && Number(v) > Number(target);
  return (
    <span className={cn("inline-flex items-center gap-1 tabular-nums", over && "font-semibold text-danger")} data-testid={testId} data-over={over ? "yes" : "no"}>
      <bdi className="ltr">{t("min", { n: v })}</bdi>
      {target !== null && target !== undefined ? <span className="text-xs font-normal text-muted-foreground">{t("target", { n: String(target) })}</span> : null}
      {over ? <span className="sr-only">{t("overTarget")}</span> : null}
    </span>
  );
}

export function Codes({ items, empty = "—" }: { items: string[] | null | undefined; empty?: string }) {
  if (!items?.length) return <span>{empty}</span>;
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

/** Lock note: who may see named lists (P6c-2, P6c-4). */
export function PrivacyNote({ children, testId = "em-privacy-note" }: { children: ReactNode; testId?: string }) {
  return (
    <p className="mb-3 flex w-fit max-w-full items-start gap-2 rounded-md border border-input/70 bg-surface px-3 py-1.5 text-xs" data-testid={testId}>
      <Lock aria-hidden className="mt-px size-3.5 shrink-0 text-muted-foreground" />
      <span>{children}</span>
    </p>
  );
}

/** Radio-style answer buttons (pass / fail / n.a., resolution reasons), ≥ 44 px, the choice read from the mark. */
export function AnswerButtons<V extends string>({
  value,
  options,
  onChange,
  testId,
  danger,
}: {
  value: V | null | undefined;
  options: { value: V; label: string }[];
  onChange: (v: V) => void;
  testId?: string;
  danger?: V[];
}) {
  return (
    <div role="radiogroup" className="grid grid-cols-3 gap-2" data-testid={testId}>
      {options.map((o) => {
        const on = value === o.value;
        return (
          <Button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            variant={on ? (danger?.includes(o.value) ? "destructive" : "default") : "outline"}
            className="min-h-11 justify-start gap-2 px-2 text-sm"
            onClick={() => onChange(o.value)}
            data-testid={testId ? `${testId}-${o.value}` : undefined}
          >
            <ChoiceMark on={on} />
            {o.label}
          </Button>
        );
      })}
    </div>
  );
}

/** Reason ≥ min characters (return, cancel, void, tag out, retire). */
export function EmReasonDialog({
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
  onConfirm: (reason: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const t = useTranslations("emergency.common");
  const refresh = useEmergencyRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      destructive={destructive}
      dismissLabel={t("back")}
      disabled={reason.trim().length < min}
      testId="em-reason-confirm"
      onConfirm={async () => {
        await onConfirm(reason.trim());
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="em-reason" label={t("reason")} required hint={t("reasonMin", { min, n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="em-reason" />
      </FormField>
      <PossibleIdHint text={reason} />
    </StepDialog>
  );
}

/* ───────────── times (local Asia/Riyadh inputs) ───────────── */

/** Datetime-local value for now in the project zone (the e2e clock shifts Date). */
export function nowLocal(): string {
  return utcToZonedInput(new Date().toISOString());
}

export function toLocalInput(iso: string | null | undefined): string {
  return iso ? utcToZonedInput(iso) : "";
}

export function fromLocalInput(v: string): string | null {
  return v ? zonedInputToUtc(v) : null;
}

/** Hint under every 6c free text (P6c-3, P1-8). */
export function NoNamesHint() {
  const t = useTranslations("emergency.common");
  return <span data-testid="no-names-hint">{t("noNames")}</span>;
}
