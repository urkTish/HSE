"use client";
import { CheckCircle2, CloudFog, Info, TriangleAlert, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { Checkbox } from "@/components/ui/checkbox";
import { StatusBadge } from "@/components/common/status-badge";
import { PossibleIdHint } from "@/components/common/api-warnings";
import { StepDialog, SubNav } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import type { Schemas } from "@/lib/api/client";
import { useEnvReference, useEnvRefresh } from "@/lib/api/env";
import { can, canWrite } from "@/lib/permissions";
import { cn } from "@/lib/utils";

type S = Schemas;

/* ───────────── capabilities (6e §5.17, 202–214) ───────────── */

export function useEnvCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  return {
    view: can(me, "env.view", pid),
    aspects: canWrite(me, "env_aspect.manage", pid),
    permits: canWrite(me, "env_permit.manage", pid),
    areas: canWrite(me, "waste_area.manage", pid),
    consign: canWrite(me, "consignment.record", pid),
    close: canWrite(me, "consignment.close", pid),
    monitoring: canWrite(me, "env_monitoring.manage", pid),
    reading: canWrite(me, "env_reading.record", pid),
    review: canWrite(me, "env.review", pid),
    spill: canWrite(me, "spill.record", pid),
    complaints: canWrite(me, "env_complaint.manage", pid),
    settings: canWrite(me, "env.settings", pid),
    void: canWrite(me, "env.void", pid),
  };
}

/* ───────────── sub navigation ───────────── */

export function EnvOverviewSubNav() {
  const t = useTranslations("env.nav");
  return (
    <SubNav
      items={[
        { href: "/env-overview", label: t("overview"), testId: "sub-env-overview" },
        { href: "/env-kpis", label: t("kpis"), testId: "sub-env-kpis" },
        { href: "/env-settings", label: t("settings"), testId: "sub-env-settings" },
      ]}
    />
  );
}

export function EnvPermitSubNav() {
  const t = useTranslations("env.nav");
  return (
    <SubNav
      items={[
        { href: "/env-permits", label: t("permits"), testId: "sub-env-permits" },
        { href: "/env-providers", label: t("providers"), testId: "sub-env-providers" },
      ]}
    />
  );
}

export function EnvWasteSubNav() {
  const t = useTranslations("env.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/waste-consignments", label: t("consignments"), testId: "sub-env-consignments" },
        { href: "/waste-consignments/new", label: t("dispatch"), show: can(me, "consignment.record"), testId: "sub-env-dispatch" },
        { href: "/waste-areas", label: t("areas"), testId: "sub-env-areas" },
        { href: "/waste-streams", label: t("streams"), testId: "sub-env-streams" },
      ]}
    />
  );
}

export function EnvMonitorSubNav() {
  const t = useTranslations("env.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/env-readings", label: t("readings"), testId: "sub-env-readings" },
        { href: "/env-readings/new", label: t("newReading"), show: can(me, "env_reading.record"), testId: "sub-env-new-reading" },
        { href: "/env-exceedances", label: t("exceedances"), testId: "sub-env-exceedances" },
        { href: "/env-points", label: t("points"), testId: "sub-env-points" },
        { href: "/env-water", label: t("water"), testId: "sub-env-water" },
      ]}
    />
  );
}

export function EnvEventSubNav() {
  const t = useTranslations("env.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/spills", label: t("spills"), testId: "sub-env-spills" },
        { href: "/spills/new", label: t("newSpill"), show: can(me, "spill.record"), testId: "sub-env-new-spill" },
        { href: "/env-complaints", label: t("complaints"), testId: "sub-env-complaints" },
      ]}
    />
  );
}

/* ───────────── reference lists (server EN/AR labels, §3.17) ───────────── */

export type EnvList =
  | "aspects"
  | "impacts"
  | "permit_types"
  | "issuers"
  | "provider_kinds"
  | "licence_activities"
  | "waste_classes"
  | "routes"
  | "streams"
  | "storage_area_types"
  | "instrument_kinds"
  | "point_kinds"
  | "parameters"
  | "noise_areas"
  | "spill_substances"
  | "exceedance_causes"
  | "condition"
  | "schedule"
  | "period"
  | "averaging"
  | "limit_source"
  | "point_source"
  | "spill_source"
  | "surface"
  | "water_source"
  | "complaint_channel"
  | "complaint_category"
  | "background_source";

/** Labels of the seeded 6e reference lists in the page language; the code while loading or when unknown. */
export function useEnvRef() {
  const q = useEnvReference();
  const ar = useLocale() === "ar";
  const lists = q.data?.lists as Record<string, S["EnvRefItem"][]> | undefined;
  const items = useCallback((l: EnvList): S["EnvRefItem"][] => lists?.[l] ?? [], [lists]);
  const label = useCallback(
    (l: EnvList, code: string | null | undefined): string => {
      if (!code) return "—";
      const it = lists?.[l]?.find((x) => x.code === code);
      return it ? (ar ? it.label_ar : it.label_en) : code;
    },
    [lists, ar],
  );
  /** Unit of a parameter from the PA detail ("µg/m³ · 0–20000"). */
  const unit = useCallback(
    (parameter: string | null | undefined): string => {
      const d = lists?.parameters?.find((x) => x.code === parameter)?.detail ?? "";
      const u = d.split(" · ")[0] ?? "";
      return u === "—" || u === "score" ? "" : u;
    },
    [lists],
  );
  const options = useCallback((l: EnvList) => items(l).map((x) => ({ value: x.code, label: ar ? x.label_ar : x.label_en })), [items, ar]);
  return { label, items, unit, options, library: q.data?.limit_library ?? [], ready: Boolean(q.data) };
}

/** Bilingual text of a record in the page language (EN fallback). */
export function useBi() {
  const ar = useLocale() === "ar";
  return useCallback((en: string | null | undefined, arText: string | null | undefined) => (ar && arText?.trim() ? arText : (en ?? arText ?? "")), [ar]);
}

/* ───────────── status badges (colour + icon + words) ───────────── */

type EnvStatusGroup =
  | "envAspectStatus"
  | "envPermitStatus"
  | "envProviderStatus"
  | "envAreaStatus"
  | "envConsignmentStatus"
  | "envInstrumentStatus"
  | "envExceedanceStatus"
  | "envSpillStatus"
  | "envComplaintStatus"
  | "envRecordState";

/** Shared tone map for the 6e states (StatusBadge already knows most of them). */
const TONE: Record<string, string> = {
  dispatched: "in_progress",
  received: "submitted",
  reported: "reported",
  cleaned_up: "in_progress",
  responded: "submitted",
  valid: "valid",
  pending: "pending_approval",
};

export function EnvStatusBadge({ group, status, testId = "env-status" }: { group: EnvStatusGroup; status: string; testId?: string }) {
  const te = useTranslations("enums");
  return (
    <span data-testid={testId} data-status={status}>
      <StatusBadge status={TONE[status] ?? status} label={te(`${group}.${status}` as "envSpillStatus.reported")} />
    </span>
  );
}

/** Reading / requirement result (§6.2): never colour alone. */
export function ResultBadge({ result, background }: { result: S["ReadingResult"]; background?: boolean }) {
  const te = useTranslations("enums");
  const tone = result === "exceedance" ? "danger" : result === "alert" ? "warning" : result === "ok" ? "success" : "neutral";
  const Icon = result === "exceedance" ? XCircle : result === "alert" ? TriangleAlert : result === "ok" ? CheckCircle2 : Info;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={tone} data-testid="reading-result" data-result={result}>
        <Icon aria-hidden />
        {te(`envReadingResult.${result}`)}
      </Badge>
      {background ? <BackgroundBadge /> : null}
    </span>
  );
}

/** "Background dust" label (EXD-3, EXD-4): an exception, never a deletion. */
export function BackgroundBadge({ refText }: { refText?: string | null }) {
  const t = useTranslations("env.common");
  return (
    <Badge tone="info" data-testid="background-badge">
      <CloudFog aria-hidden />
      {t("background")}
      {refText ? <bdi className="ltr font-mono text-[11px]">{refText}</bdi> : null}
    </Badge>
  );
}

/** A measured value with its unit, kept left-to-right in Arabic. */
export function Measure({ v, unit, className }: { v: string | null | undefined; unit?: string; className?: string }) {
  if (v === null || v === undefined || v === "") return <span>—</span>;
  return (
    <bdi className={cn("ltr tabular-nums whitespace-nowrap", className)}>
      {v}
      {unit ? ` ${unit}` : ""}
    </bdi>
  );
}

/** Hint under every 6e free text (P6e-4, P1-8). */
export function NoNamesHint() {
  const t = useTranslations("env.common");
  return <span data-testid="no-names-hint">{t("noNames")}</span>;
}

/** Reason ≥ min characters (void, suspend, cancel, archive, reject). */
export function EnvReasonDialog({
  title,
  description,
  confirmLabel,
  min = 20,
  destructive = true,
  onConfirm,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  confirmLabel: string;
  min?: number;
  destructive?: boolean;
  onConfirm: (reason: string) => Promise<unknown>;
  onClose: () => void;
  children?: ReactNode;
}) {
  const t = useTranslations("env.common");
  const refresh = useEnvRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      destructive={destructive}
      dismissLabel={t("back")}
      disabled={reason.trim().length < min}
      testId="env-reason-confirm"
      onConfirm={async () => {
        await onConfirm(reason.trim());
        await refresh();
      }}
      onClose={onClose}
    >
      {children}
      <FormField id="env-reason" label={t("reason")} required hint={t("reasonMin", { min, n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="env-reason" />
      </FormField>
      <PossibleIdHint text={reason} />
    </StepDialog>
  );
}

/** Labelled checkbox with a ≥ 44 px target. */
export function Check({ id, label, checked, onChange, disabled, testId }: { id: string; label: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; testId?: string }) {
  return (
    <CheckboxField id={id} label={label}>
      <Checkbox checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} data-testid={testId} />
    </CheckboxField>
  );
}
