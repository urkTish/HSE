"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Ban, CircleCheck, CircleX, OctagonX, ShieldCheck, TriangleAlert, type LucideIcon } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, DaysLeft, StepDialog, SubNav } from "@/components/access/common";
import { DateTimeInput, userLabel } from "@/components/ptw/common";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, postForm, unwrap, type Schemas } from "@/lib/api/client";
export { HookConditions, HookSeverity } from "./hook-ui";
import { useCertCatalogue, useCertRefresh, useTpis } from "@/lib/api/cert";
import { CERT_VERIFICATION_METHODS, VERIFICATION_DIFFERENCES, VERIFICATION_OUTCOMES } from "@/lib/cert-enums";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";

type S = Schemas;

/* ───────────── sub navigation ───────────── */

export function EquipmentSubNav() {
  const t = useTranslations("cert.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/equipment-deployments", label: t("deployments"), testId: "sub-eq-deployments" },
        { href: "/equipment", label: t("register"), testId: "sub-eq-register" },
        { href: "/equipment-certificates", label: t("certificates"), testId: "sub-eq-certs" },
        { href: "/verification-log", label: t("verificationLog"), show: can(me, "cert.verify") || can(me, "cert.review"), testId: "sub-eq-verif" },
        { href: "/defects", label: t("defects"), testId: "sub-eq-defects" },
      ]}
    />
  );
}

export function ScaffoldSubNav() {
  const t = useTranslations("cert.nav");
  return (
    <SubNav
      items={[
        { href: "/scaffolds", label: t("scaffolds"), testId: "sub-sc-register" },
        { href: "/scaffold-board", label: t("tagBoard"), testId: "sub-sc-board" },
      ]}
    />
  );
}

export function PersonnelSubNav() {
  const t = useTranslations("cert.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/personnel-certificates", label: t("personnel"), testId: "sub-pc-list" },
        { href: "/verification-log", label: t("verificationLog"), show: can(me, "cert.verify") || can(me, "cert.review"), testId: "sub-pc-verif" },
        { href: "/certification-bans", label: t("bans"), show: can(me, "cert.blacklist") || can(me, "cert.review"), testId: "sub-pc-bans" },
        { href: "/blacklist-register", label: t("blacklist"), testId: "sub-pc-blacklist" },
      ]}
    />
  );
}

export function CertSetupSubNav() {
  const t = useTranslations("cert.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/hook-policy", label: t("hookPolicy"), testId: "sub-cs-hooks" },
        { href: "/cert-settings", label: t("settings"), show: can(me, "cert_settings.edit") || can(me, "cert.review"), testId: "sub-cs-settings" },
        { href: "/cert-catalogue", label: t("catalogue"), testId: "sub-cs-catalogue" },
        { href: "/tpi-approvals", label: t("approvals"), show: can(me, "cert_register.view"), testId: "sub-cs-approvals" },
      ]}
    />
  );
}

/* ───────────── badges ───────────── */

export function ServiceStatusBadge({ status, reason }: { status: S["ServiceStatus"]; reason?: S["ServiceStatusReason"] | null }) {
  const te = useTranslations("enums");
  return (
    <span className="inline-flex flex-wrap items-center gap-1" data-testid="service-status" data-status={status} data-reason={reason ?? ""}>
      <StatusBadge status={status} label={te(`serviceStatus.${status}`)} />
      {reason && reason !== status && status !== "in_service" ? <span className="text-xs text-muted-foreground">{te(`serviceStatusReason.${reason}`)}</span> : null}
    </span>
  );
}

export function CertStatusBadge({ status }: { status: S["CertificateStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="cert-status" data-status={status}>
      <StatusBadge status={status} label={te(`certStatus.${status}`)} />
    </span>
  );
}

export function VerificationBadge({ status }: { status: S["VerificationStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="verification-status" data-status={status}>
      <StatusBadge status={`verif_${status}`} label={te(`verificationStatus.${status}`)} />
    </span>
  );
}

/** Physical tag colour per tag status (theme-independent tag tokens): expired / inspection required hang a red tag. */
export const TAG_TONE: Record<S["ScaffoldTagStatus"], "green" | "yellow" | "red" | "none"> = {
  green: "green",
  yellow: "yellow",
  red: "red",
  expired: "red",
  inspection_required: "red",
  none: "none",
};
export const TAG_FILL = {
  green: "bg-tag-green text-tag-green-fg",
  yellow: "bg-tag-yellow text-tag-yellow-fg",
  red: "bg-tag-red text-tag-red-fg",
  none: "bg-tag-none text-tag-none-fg",
} as const;
export const TAG_BORDER = { green: "border-tag-green", yellow: "border-tag-yellow", red: "border-tag-red", none: "border-tag-none" } as const;
const TAG_ICON: Record<S["ScaffoldTagStatus"], LucideIcon> = {
  green: CircleCheck,
  yellow: TriangleAlert,
  red: OctagonX,
  expired: OctagonX,
  inspection_required: OctagonX,
  none: Ban,
};

/**
 * Scaffold tag chip: the solid tag colour (identical in light and dark, readable in sun) with its own icon and the
 * tag word plus what it means ("Green — safe to use", "Tag expired — do not use"). Never colour alone.
 */
export function TagStatusBadge({ status, size = "sm" }: { status: S["ScaffoldTagStatus"]; size?: "sm" | "lg" }) {
  const te = useTranslations("enums");
  const td = useTranslations("certDesign");
  const Icon = TAG_ICON[status];
  const label = status === "expired" || status === "inspection_required" ? td(`tag.${status}`) : te(`tagStatus.${status}`);
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-md font-bold",
        size === "lg" ? "px-2.5 py-1 text-sm" : "px-1.5 py-0.5 text-xs",
        TAG_FILL[TAG_TONE[status]],
      )}
      data-testid="tag-status"
      data-status={status}
    >
      <Icon aria-hidden className={cn("shrink-0", size === "lg" ? "size-4" : "size-3.5")} strokeWidth={2.5} />
      <span className="min-w-0">{label}</span>
    </span>
  );
}

/* ───────────── state panel ───────────── */

export type StateTone = "success" | "warning" | "danger" | "info" | "neutral";
const STATE_TONE_CLS: Record<StateTone, string> = {
  success: "border-success/40 bg-success-bg [--tone:var(--status-success)]",
  warning: "border-warning/50 bg-warning-bg [--tone:var(--status-warning)]",
  danger: "border-danger/40 bg-danger-bg [--tone:var(--status-danger)]",
  info: "border-info/40 bg-info-bg [--tone:var(--status-info)]",
  neutral: "border-neutral/40 bg-neutral-bg [--tone:var(--status-neutral)]",
};

/**
 * One-glance "may this be used today, and if not why" panel (Phase 3 permit state panel pattern): tinted 2 px border
 * with an 8 px start bar, a 36 px icon, the state in 24 px bold and one plain sentence; details below.
 * The state always comes from the server (service status, in_force, usable, usable_today); the UI only words it.
 */
export function CertStatePanel({
  tone,
  Icon,
  word,
  sub,
  line,
  children,
  testId,
  data,
}: {
  tone: StateTone;
  Icon: LucideIcon;
  word: ReactNode;
  sub?: ReactNode;
  line?: ReactNode;
  children?: ReactNode;
  testId?: string;
  data?: Record<`data-${string}`, string>;
}) {
  const t = useTranslations("certDesign");
  return (
    <section
      className={cn("flex flex-col gap-2 rounded-xl border-2 border-s-8 p-4 [border-inline-start-color:var(--tone)]", STATE_TONE_CLS[tone])}
      aria-label={t("stateLabel")}
      data-testid={testId}
      data-tone={tone}
      {...data}
    >
      <div className="flex items-start gap-3">
        <Icon aria-hidden className="mt-0.5 size-9 shrink-0 text-[var(--tone)]" strokeWidth={2.25} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-2xl leading-tight font-bold text-[var(--tone)]" data-testid="cert-state-word">
              {word}
            </span>
            {sub ? <span className="text-base font-semibold">{sub}</span> : null}
          </p>
          {line ? <p className="mt-0.5 text-sm font-medium">{line}</p> : null}
          {children ? <div className="mt-2 flex flex-col gap-1.5 text-sm">{children}</div> : null}
        </div>
      </div>
    </section>
  );
}

/** A server reason code in words: hook reason, service-status reason or gate reason, else the code itself. */
export function useReasonLabel() {
  const te = useTranslations("enums");
  return (code: string | null | undefined): string => {
    if (!code) return "";
    if (te.has(`hookReason.${code as S["HookReasonCode"]}`)) return te(`hookReason.${code as S["HookReasonCode"]}`);
    if (te.has(`serviceStatusReason.${code as S["ServiceStatusReason"]}`)) return te(`serviceStatusReason.${code as S["ServiceStatusReason"]}`);
    if (te.has(`gateReason.${code as S["GateReasonCode"]}`)) return te(`gateReason.${code as S["GateReasonCode"]}`);
    return code;
  };
}

export function ScaffoldStatusBadge({ status }: { status: S["ScaffoldStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="scaffold-status" data-status={status}>
      <StatusBadge status={`scaffold_${status}`} label={te(`scaffoldStatus.${status}`)} />
    </span>
  );
}

export function DefectCategoryBadge({ category }: { category: S["DefectCategory"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="defect-category" data-category={category}>
      <StatusBadge status={`defect_${category}`} label={te(`defectCategory.${category}`)} />
    </span>
  );
}

export function HookStageBadge({ stage }: { stage: S["HookStage"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="hook-stage" data-stage={stage}>
      <StatusBadge status={`hook_${stage}`} label={te(`hookStage.${stage}`)} />
    </span>
  );
}

export function LineResultBadge({ result }: { result: S["LineResult"] }) {
  const te = useTranslations("enums");
  return <StatusBadge status={`line_${result}`} label={te(`lineResult.${result}`)} />;
}

/**
 * The two kinds of "not met" a Phase 4 hook can return, visually distinct:
 * hard stop (red, lock icon, blocks in every stage) and transition-stage warning (amber, does not block yet).
 */
/* ───────────── validity ───────────── */

/** Strictest-wins validity as computed by the server (the UI never computes it). */
export function CertValidityView({ v, projectId, compact, hideBadge }: { v: S["CertValidity"]; projectId?: string | null; compact?: boolean; hideBadge?: boolean }) {
  const t = useTranslations("cert");
  const te = useTranslations("enums");
  const { date, dateTime } = useFormatters(projectId);
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="cert-validity" data-in-force={v.in_force ? "yes" : "no"} data-valid-until={v.valid_until ?? ""} data-factor={v.limiting_factor ?? ""}>
      <span className="flex flex-wrap items-center gap-2">
        {hideBadge ? null : v.in_force ? (
          <Badge tone="success">
            <CircleCheck aria-hidden />
            {t("inForce")}
          </Badge>
        ) : (
          <Badge tone="danger">
            <CircleX aria-hidden />
            {t("notInForce")}
          </Badge>
        )}
        {v.valid_until ? (
          <span>
            {t("validUntil")}: <span className="ltr font-medium">{date(v.valid_until)}</span>
          </span>
        ) : null}
        {v.in_force ? <DaysLeft days={v.days_left} /> : null}
      </span>
      {v.limiting_factor ? (
        <span className="text-xs text-muted-foreground" data-testid="cert-limiting-factor" data-factor={v.limiting_factor}>
          {t("limitedBy", { factor: te(`certLimitingFactor.${v.limiting_factor}`) })}
        </span>
      ) : null}
      {!compact && v.printed_date && v.platform_end && v.printed_date !== v.platform_end ? (
        <span className="text-xs text-muted-foreground">
          {t("printedVsPlatform", { printed: date(v.printed_date), platform: date(v.platform_end) })}
        </span>
      ) : null}
      {!v.in_force && v.not_in_force_reason ? (
        <span className="text-xs font-medium text-destructive" data-testid="not-in-force-reason" data-reason={v.not_in_force_reason}>
          {te(`hookReason.${v.not_in_force_reason}`)}
        </span>
      ) : null}
      {v.unverified_window_until ? <span className="text-xs text-warning">{t("unverifiedWindow", { until: dateTime(v.unverified_window_until) })}</span> : null}
      {!compact && v.in_force_from ? <span className="text-xs text-muted-foreground">{t("inForceFrom", { at: dateTime(v.in_force_from) })}</span> : null}
    </div>
  );
}

export function EquipmentLimitations({ items }: { items: S["EquipmentLimitationRead"][] }) {
  const locale = useLocale();
  if (!items.length) return null;
  return (
    <ul className="flex flex-wrap gap-1" data-testid="limitations">
      {items.map((l, i) => (
        <li key={`${l.code}-${i}`}>
          <Badge tone="warning" data-code={l.code}>
            {locale === "ar" ? l.label_ar : l.label_en}
            {l.value ? <bdi className="ltr ms-1">{l.value}</bdi> : null}
            {l.text ? <span className="ms-1">· {l.text}</span> : null}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

export function PersonnelLimitations({ items }: { items: S["PersonnelLimitationRead"][] }) {
  const locale = useLocale();
  if (!items.length) return null;
  return (
    <ul className="flex flex-wrap gap-1" data-testid="limitations">
      {items.map((l, i) => (
        <li key={`${l.code}-${i}`}>
          <Badge tone="warning" data-code={l.code}>
            {locale === "ar" ? l.label_ar : l.label_en}
            {l.text ? <span className="ms-1">· {l.text}</span> : null}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

/* ───────────── labels and pickers ───────────── */

export function TpiLabel({ tpi, link = true }: { tpi: Pick<S["TpiRef"], "id" | "tpi_code" | "legal_name_en" | "legal_name_ar"> | null | undefined; link?: boolean }) {
  const locale = useLocale();
  if (!tpi) return <>—</>;
  const body = (
    <>
      <Code>{tpi.tpi_code}</Code>
      <span className="ms-1.5 text-muted-foreground">{locale === "ar" ? tpi.legal_name_ar : tpi.legal_name_en}</span>
    </>
  );
  return link ? (
    <Link href={`/tpis/${tpi.id}`} className="hover:underline">
      {body}
    </Link>
  ) : (
    <span>{body}</span>
  );
}

export function EquipmentLabel({ e, link = true }: { e: Pick<S["EquipmentRef"], "id" | "equipment_no" | "category" | "manufacturer" | "model">; link?: boolean }) {
  const te = useTranslations("enums");
  const body = (
    <>
      <Code className="font-medium">{e.equipment_no}</Code>
      <span className="ms-1.5 text-xs text-muted-foreground">
        {te(`eqc.${e.category}`)} · {e.manufacturer} {e.model}
      </span>
    </>
  );
  return link ? (
    <Link href={`/equipment/${e.id}`} className="hover:underline" data-testid="equipment-link">
      {body}
    </Link>
  ) : (
    <span>{body}</span>
  );
}

/** TPI picker (org-wide register), optionally narrowed by kind. Shows only TPIs accepted for use first. */
export function TpiSelect({
  id,
  value,
  onChange,
  kind,
  projectId,
  required,
  label,
}: {
  id: string;
  value: string;
  onChange: (id: string, tpi: S["TpiListItem"] | null) => void;
  kind?: S["TpiKind"];
  projectId?: string;
  required?: boolean;
  label: string;
}) {
  const tc = useTranslations("common");
  const t = useTranslations("cert");
  const locale = useLocale();
  const q = useTpis({ kind: kind ? [kind] : null, project_id: projectId ?? null, page_size: 200 });
  const items = q.data?.items ?? [];
  return (
    <FormField id={id} label={label} required={required}>
      <Select value={value} onChange={(e) => onChange(e.target.value, items.find((x) => x.id === e.target.value) ?? null)} data-testid={id}>
        <option value="">{tc("select")}</option>
        {items.map((x) => (
          <option key={x.id} value={x.id}>
            {x.tpi_code} — {locale === "ar" ? x.legal_name_ar : x.legal_name_en}
            {x.accepted_for_use ? "" : ` (${t("notAccepted")})`}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

/** Personnel certificate type labels from the catalogue (codes are strings, D-83). */
export function useCertTypes(projectId: string) {
  const locale = useLocale();
  const q = useCertCatalogue(projectId);
  const types = q.data?.cert_types ?? [];
  const label = (code: string) => {
    const x = types.find((c) => c.code === code);
    return x ? (locale === "ar" ? x.label_ar : x.label_en) : code;
  };
  return { types, label, catalogue: q.data, isLoading: q.isLoading };
}

export function UserName({ u }: { u: S["UserRef"] | null | undefined }) {
  const locale = useLocale();
  return <>{u ? userLabel(u, locale) : "—"}</>;
}

/* ───────────── workflow: certificate transitions ───────────── */

const REASON_REQUIRED: S["CertificateStatus"][] = ["rejected", "suspended", "revoked", "draft"];

/**
 * Certificate review actions from `allowed_actions` (server-decided). Reject / suspend / revoke need a reason;
 * accept can carry the identity / configuration confirmation ticks.
 */
export function CertTransitionButtons({
  kind,
  id,
  actions,
  needsIdentityTick,
  needsConfigTick,
  onDone,
}: {
  kind: "equipment" | "personnel";
  id: string;
  actions: S["AllowedCertAction"][];
  needsIdentityTick?: boolean;
  needsConfigTick?: boolean;
  onDone?: (r: unknown) => void;
}) {
  const t = useTranslations("cert");
  const te = useTranslations("enums");
  const locale = useLocale();
  const refresh = useCertRefresh();
  const [to, setTo] = useState<S["AllowedCertAction"] | null>(null);
  const [reason, setReason] = useState("");
  const [code, setCode] = useState<S["CertStatusReason"] | "">("");
  const [identity, setIdentity] = useState(false);
  const [config, setConfig] = useState(false);
  if (!actions.length) return null;
  async function go(a: S["AllowedCertAction"]) {
    const body: S["CertTransitionRequest"] = {
      to_status: a.to_status,
      reason: reason.trim() || null,
      reason_code: code || null,
      identity_confirmed_by_tpi: identity,
      configuration_mismatch_confirmed: config,
    };
    const r =
      kind === "equipment"
        ? await unwrap(api.POST("/api/v1/equipment-certificates/{certificate_id}/transitions", { params: { path: { certificate_id: id } }, body }))
        : await unwrap(api.POST("/api/v1/personnel-certificates/{certificate_id}/transitions", { params: { path: { certificate_id: id } }, body }));
    await refresh();
    toast.success(te(`certStatus.${a.to_status}`));
    onDone?.(r);
  }
  const needsReason = to ? REASON_REQUIRED.includes(to.to_status) : false;
  const destructive = to ? ["rejected", "revoked", "suspended"].includes(to.to_status) : false;
  return (
    <>
      {actions.map((a) => (
        <Button
          key={a.to_status}
          variant={a.to_status === "accepted" ? "default" : ["revoked", "rejected"].includes(a.to_status) ? "destructive-outline" : "outline"}
          onClick={() => {
            setTo(a);
            setReason("");
            setCode("");
          }}
          data-testid={`cert-action-${a.to_status}`}
        >
          {locale === "ar" ? a.label_ar : a.label_en}
        </Button>
      ))}
      {to ? (
        <StepDialog
          title={locale === "ar" ? to.label_ar : to.label_en}
          description={to.to_status === "accepted" ? t("acceptHint") : destructive ? t("hardStopHint") : undefined}
          confirmLabel={locale === "ar" ? to.label_ar : to.label_en}
          destructive={destructive}
          disabled={needsReason && reason.trim().length < 5}
          onClose={() => setTo(null)}
          onConfirm={() => go(to)}
          testId="cert-transition-confirm"
        >
          {to.to_status === "accepted" && needsIdentityTick ? (
            <Tick id="ct-identity" label={t("identityConfirmed")} checked={identity} onChange={setIdentity} />
          ) : null}
          {to.to_status === "accepted" && needsConfigTick ? (
            <Tick id="ct-config" label={t("configMismatchConfirmed")} checked={config} onChange={setConfig} />
          ) : null}
          {["suspended", "revoked", "rejected"].includes(to.to_status) ? (
            <FormField id="ct-code" label={t("reasonCode")}>
              <Select value={code} onChange={(e) => setCode(e.target.value as S["CertStatusReason"])} data-testid="ct-code">
                <option value="">—</option>
                {(["document_review", "verification_failed", "tpi_revocation_notice", "tpi_suspension_notice", "hse_suspension", "other"] as const).map((x) => (
                  <option key={x} value={x}>
                    {te(`certStatusReason.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          {needsReason || to.to_status !== "accepted" ? (
            <FormField id="ct-reason" label={t("reason")} required={needsReason}>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="ct-reason" />
            </FormField>
          ) : null}
        </StepDialog>
      ) : null}
    </>
  );
}

/* ───────────── verification ───────────── */

export function VerificationTable({ items, projectId, loading, error, onRetry }: { items: S["VerificationRead"][]; projectId: string; loading?: boolean; error?: unknown; onRetry?: () => void }) {
  const t = useTranslations("cert");
  const te = useTranslations("enums");
  const { dateTime } = useFormatters(projectId);
  if (loading) return <LoadingState rows={2} />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!items.length) return <EmptyState message={t("noVerifications")} />;
  return (
    <Table data-testid="verifications-table">
      <THead>
        <TR>
          <TH>{t("performedAt")}</TH>
          <TH>{t("method")}</TH>
          <TH>{t("channel")}</TH>
          <TH>{t("outcome")}</TH>
          <TH>{t("reference")}</TH>
          <TH>{t("by")}</TH>
          <TH>{t("verificationStatus")}</TH>
        </TR>
      </THead>
      <TBody>
        {items.map((v) => (
          <TR key={v.id} data-testid="verification-row" data-outcome={v.outcome ?? ""}>
            <TD label={t("performedAt")}>{dateTime(v.performed_at)}</TD>
            <TD label={t("method")}>
              {te(`certVerificationMethod.${v.method}`)}
              {!v.counts_as_verification ? <span className="block text-xs text-muted-foreground">{t("doesNotCount")}</span> : null}
            </TD>
            <TD label={t("channel")}>
              <bdi className="ltr text-xs break-all">{v.channel_used}</bdi>
            </TD>
            <TD label={t("outcome")}>
              {v.outcome ? te(`verificationOutcome.${v.outcome}`) : "—"}
              {v.differences.length ? <span className="block text-xs text-muted-foreground">{v.differences.map((d) => te(`verificationDifference.${d}`)).join(" · ")}</span> : null}
            </TD>
            <TD label={t("reference")}>
              <Code className="text-xs break-all">{v.reference}</Code>
            </TD>
            <TD label={t("by")}>
              <UserName u={v.performed_by} />
            </TD>
            <TD label={t("verificationStatus")}>
              <VerificationBadge status={v.verification_status_after} />
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

/** Record a verification with the TPI (VF-2: not by the submitter; channel must be registered with the TPI). */
export function VerifyDialog({ kind, id, tpi, onClose }: { kind: "equipment" | "personnel"; id: string; tpi?: Pick<S["TpiRef"], "tpi_code"> | null; onClose: () => void }) {
  const t = useTranslations("cert");
  const te = useTranslations("enums");
  const refresh = useCertRefresh();
  const qc = useQueryClient();
  const [method, setMethod] = useState<S["CertVerificationMethod"]>("tpi_portal");
  const [channel, setChannel] = useState("");
  const [outcome, setOutcome] = useState<S["VerificationOutcome"]>("confirmed");
  const [diffs, setDiffs] = useState<S["VerificationDifference"][]>([]);
  const [diffText, setDiffText] = useState("");
  const [reference, setReference] = useState("");
  const [at, setAt] = useState("");
  const [evidence, setEvidence] = useState<string | null>(null);
  const phone = method === "tpi_phone";
  // VF-2/VF-3: evidence is required except for a phone call, where the reference names the TPI person (≥ 20 chars).
  const valid =
    channel.trim().length > 2 &&
    (phone ? reference.trim().length >= 20 : reference.trim().length > 1 && Boolean(evidence)) &&
    (outcome !== "details_differ" || diffs.length > 0);
  async function save() {
    const body: S["VerificationCreate"] = {
      method,
      channel_used: channel.trim(),
      outcome,
      differences: outcome === "details_differ" ? diffs : [],
      differences_text: diffText.trim() || null,
      reference: reference.trim(),
      evidence_attachment_id: phone ? null : evidence,
      performed_at: at || null,
    };
    const v =
      kind === "equipment"
        ? await unwrap(api.POST("/api/v1/equipment-certificates/{certificate_id}/verifications", { params: { path: { certificate_id: id } }, body }))
        : await unwrap(api.POST("/api/v1/personnel-certificates/{certificate_id}/verifications", { params: { path: { certificate_id: id } }, body }));
    await refresh();
    await qc.invalidateQueries({ queryKey: [kind === "equipment" ? "equipment-certificate-verifications" : "personnel-certificate-verifications"] });
    toast.success(te(`verificationStatus.${v.verification_status_after}`));
  }
  return (
    <StepDialog title={t("recordVerification")} description={t("verifyHint", { tpi: tpi?.tpi_code ?? "" })} confirmLabel={t("recordVerification")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="verify-confirm">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="vf-method" label={t("method")} required hint={method === "original_sighted" ? t("sightedHint") : undefined}>
          <Select value={method} onChange={(e) => setMethod(e.target.value as S["CertVerificationMethod"])} data-testid="vf-method">
            {CERT_VERIFICATION_METHODS.filter((m) => m !== "tpi_register_file").map((m) => (
              <option key={m} value={m}>
                {te(`certVerificationMethod.${m}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="vf-channel" label={t("channel")} required hint={t("channelHint")}>
          <Input value={channel} onChange={(e) => setChannel(e.target.value)} className="ltr" data-testid="vf-channel" />
        </FormField>
        <FormField id="vf-outcome" label={t("outcome")} required>
          <Select value={outcome} onChange={(e) => setOutcome(e.target.value as S["VerificationOutcome"])} data-testid="vf-outcome">
            {VERIFICATION_OUTCOMES.map((m) => (
              <option key={m} value={m}>
                {te(`verificationOutcome.${m}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="vf-ref" label={t("reference")} required hint={phone ? t("referencePhoneHint") : t("referenceHint")}>
          <Input value={reference} onChange={(e) => setReference(e.target.value)} className="ltr" data-testid="vf-reference" />
        </FormField>
      </div>
      {outcome === "details_differ" ? (
        <CheckboxGroup
          id="vf-diffs"
          legend={t("differences")}
          options={VERIFICATION_DIFFERENCES.map((d) => ({ value: d, label: te(`verificationDifference.${d}`) }))}
          value={diffs}
          onChange={setDiffs}
        />
      ) : null}
      {outcome !== "confirmed" ? (
        <FormField id="vf-difftext" label={t("differencesText")}>
          <Textarea value={diffText} onChange={(e) => setDiffText(e.target.value)} maxLength={500} />
        </FormField>
      ) : null}
      {!phone ? (
        <UploadField id="vf-evidence" label={t("evidence")} ownerType="verification_evidence" ownerId={id} accept="application/pdf,image/png,image/jpeg,message/rfc822,.eml" value={evidence} onChange={(v) => setEvidence(v)} required hint={t("evidenceHint")} />
      ) : null}
      <FormField id="vf-at" label={t("performedAt")} hint={t("performedAtHint")}>
        <DateTimeInput id="vf-at" value={at} onChange={setAt} />
      </FormField>
    </StepDialog>
  );
}

/** Verification history + record button for one certificate. */
export function VerificationsCard({
  kind,
  id,
  projectId,
  tpi,
  canRecord,
  query,
}: {
  kind: "equipment" | "personnel";
  id: string;
  projectId: string;
  tpi?: Pick<S["TpiRef"], "tpi_code"> | null;
  canRecord: boolean;
  query: { data?: S["VerificationList"]; isLoading: boolean; error: unknown; refetch: () => unknown };
}) {
  const t = useTranslations("cert");
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("verifications")}</CardTitle>
        {canRecord ? (
          <Button variant="outline" onClick={() => setOpen(true)} data-testid="record-verification">
            <ShieldCheck aria-hidden />
            {t("recordVerification")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        <VerificationTable items={query.data?.items ?? []} projectId={projectId} loading={query.isLoading} error={query.error} onRetry={() => void query.refetch()} />
      </CardContent>
      {open ? <VerifyDialog kind={kind} id={id} tpi={tpi} onClose={() => setOpen(false)} /> : null}
    </Card>
  );
}

/** Small "label: value" stat used on boards and bands. */
export function Stat({ label, value, tone, testId, href }: { label: string; value: ReactNode; tone?: "danger" | "warning" | "success"; testId?: string; href?: string }) {
  const body = (
    <div
      className={cn(
        "flex min-h-touch flex-col justify-center rounded-lg border p-3",
        tone === "danger" && "border-destructive/40 bg-danger-bg/40",
        tone === "warning" && "border-warning/40 bg-warning-bg/40",
        tone === "success" && "border-success/30",
      )}
      data-testid={testId}
    >
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xl font-semibold tabular-nums">{value}</span>
    </div>
  );
  return href ? (
    <Link href={href} className="hover:opacity-90">
      {body}
    </Link>
  ) : (
    body
  );
}

export function useCertCaps(projectId: string) {
  const me = useMeData();
  return {
    view: can(me, "cert_register.view", projectId),
    edit: canWrite(me, "equipment.edit", projectId),
    review: canWrite(me, "cert.review", projectId),
    verify: canWrite(me, "cert.verify", projectId),
    mobilise: canWrite(me, "equipment.mobilise", projectId),
    raise: canWrite(me, "defect.raise", projectId),
    rectify: canWrite(me, "defect.rectify", projectId),
    close: canWrite(me, "defect.close", projectId),
    inspect: canWrite(me, "scaffold.inspect", projectId),
    tpiEdit: canWrite(me, "tpi.edit", projectId),
    blacklist: canWrite(me, "cert.blacklist", projectId),
    suspend: canWrite(me, "cert.suspend", projectId),
    pView: can(me, "personnel_cert.view", projectId),
    pSubmit: canWrite(me, "personnel_cert.submit", projectId),
    scan: can(me, "personnel_cert.scan_view", projectId),
    import: canWrite(me, "cert.import", projectId),
    check: can(me, "cert.check", projectId),
    kpi: can(me, "cert_kpi.view", projectId),
    export: can(me, "export.cert", projectId),
    settings: canWrite(me, "cert_settings.edit", projectId),
    manager: me.is_hse_manager,
  };
}

/** Checkbox with its label (large touch target); testId = id. */
export function Tick({ id, label, checked, onChange, disabled }: { id: string; label: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <CheckboxField id={id} label={label}>
      <Checkbox checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} data-testid={id} />
    </CheckboxField>
  );
}

/**
 * Upload one file to /attachments and hand its id back (Phase 4 owner types; the owner is the parent record,
 * see PROGRESS contract request on Phase 4 attachment owners).
 */
export function UploadField({
  id,
  label,
  ownerType,
  ownerId,
  accept,
  value,
  onChange,
  required,
  hint,
}: {
  id: string;
  label: string;
  ownerType: S["AttachmentOwner"];
  ownerId: string;
  accept?: string;
  value: string | null;
  onChange: (attachmentId: string | null, a: S["AttachmentRead"] | null) => void;
  required?: boolean;
  hint?: string;
}) {
  const t = useTranslations("cert");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [name, setName] = useState<string | null>(null);
  async function upload(f: File | undefined) {
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("owner_type", ownerType);
      form.set("owner_id", ownerId);
      form.set("file", f);
      const a = await postForm<S["AttachmentRead"]>("/api/v1/attachments", form);
      setName(a.file_name);
      onChange(a.id, a);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <FormField id={id} label={label} required={required} hint={hint}>
      <div className="flex flex-col gap-1">
        <Input id={id} type="file" accept={accept} disabled={busy} onChange={(e) => void upload(e.target.files?.[0])} data-testid={id} />
        {value ? (
          <span className="text-xs text-success" data-testid={`${id}-done`}>
            {t("uploaded")}
            {name ? `: ${name}` : ""}
          </span>
        ) : null}
        <MutationError error={error} />
      </div>
    </FormField>
  );
}
