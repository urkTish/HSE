"use client";
import { ShieldAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { FormField } from "@/components/common/form-field";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, SubNav } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import type { Schemas } from "@/lib/api/client";
import { useFitnessCodes, useMedicalExaminers, useMedicalProviders } from "@/lib/api/medical";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";

type S = Schemas;

/* ───────────── capabilities (6a §5.15, 146–165) ───────────── */

export function useMedCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  return {
    catalogue: can(me, "fitness_catalogue.view", pid),
    codeEdit: canWrite(me, "fitness_code.edit", pid),
    providerEdit: canWrite(me, "medical_provider.edit", pid),
    providerDecide: canWrite(me, "medical_provider.decide", pid),
    planEdit: canWrite(me, "medical_plan.edit", pid),
    profileEdit: canWrite(me, "health_profile.edit", pid),
    recordClinic: canWrite(me, "fitness.record_clinic", pid),
    submitExternal: canWrite(me, "fitness.submit_external", pid),
    review: canWrite(me, "fitness.review", pid),
    status: can(me, "fitness.status_view", pid),
    functional: can(me, "fitness.functional_view", pid),
    clinical: can(me, "fitness.clinical_view", pid),
    refer: canWrite(me, "fitness_referral.raise", pid),
    holdManage: canWrite(me, "fitness_hold.manage", pid),
    /** Cancelling holds is OH Practitioner / HSE Manager only (row 159 "P (place only)" for officers): both hold 157. */
    holdCancel: canWrite(me, "fitness_hold.manage", pid) && can(me, "fitness.clinical_view", pid),
    scan: can(me, "fitness_scan.view", pid),
    import: canWrite(me, "fitness.import", pid),
    kpi: can(me, "medical_kpi.view", pid),
    export: can(me, "export.medical", pid),
    settings: canWrite(me, "medical_settings.edit", pid),
    subjectReport: can(me, "fitness.subject_report", pid),
    names: can(me, "worker.view", pid),
    manager: me.is_hse_manager,
  };
}

/* ───────────── sub navigation ───────────── */

export function MedicalCatalogueSubNav() {
  const t = useTranslations("medical.nav");
  return (
    <SubNav
      items={[
        { href: "/fitness-codes", label: t("codes"), testId: "sub-med-codes" },
        { href: "/medical-providers", label: t("providers"), testId: "sub-med-providers" },
        { href: "/medical-examiners", label: t("examiners"), testId: "sub-med-examiners" },
      ]}
    />
  );
}

export function MedicalPlanSubNav() {
  const t = useTranslations("medical.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/medical-plan", label: t("plan"), testId: "sub-med-plan" },
        { href: "/fitness-gaps", label: t("gaps"), show: can(me, "fitness.status_view"), testId: "sub-med-gaps" },
        { href: "/worker-health", label: t("workerHealth"), show: can(me, "fitness.status_view"), testId: "sub-med-worker" },
      ]}
    />
  );
}

export function FitnessCasesSubNav() {
  const t = useTranslations("medical.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/fitness-assessments", label: t("assessments"), show: can(me, "fitness.clinical_view") || can(me, "fitness.submit_external") || can(me, "fitness.record_clinic"), testId: "sub-med-assessments" },
        { href: "/fitness-holds", label: t("holds"), show: can(me, "fitness.functional_view"), testId: "sub-med-holds" },
        { href: "/fitness-referrals", label: t("referrals"), show: can(me, "fitness.functional_view") || can(me, "fitness_referral.raise"), testId: "sub-med-referrals" },
        { href: "/medical-imports", label: t("imports"), show: can(me, "fitness.import"), testId: "sub-med-imports" },
      ]}
    />
  );
}

/* ───────────── badges ───────────── */

export function MedProviderStatusBadge({ status }: { status: S["MedicalProviderStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="med-provider-status" data-status={status}>
      <StatusBadge status={status} label={te(`medProviderStatus.${status}`)} />
    </span>
  );
}

export function ExaminerStatusBadge({ status }: { status: S["ExaminerStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="examiner-status" data-status={status}>
      <StatusBadge status={status} label={te(`examinerStatus.${status}`)} />
    </span>
  );
}

const ASSESSMENT_TONE: Record<S["AssessmentStatus"], string> = {
  draft: "draft",
  awaiting_signoff: "pending_approval",
  submitted: "submitted",
  accepted: "accepted",
  rejected: "rejected",
  revoked: "revoked",
};

export function AssessmentStatusBadge({ status }: { status: S["AssessmentStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="assessment-status" data-status={status}>
      <StatusBadge status={ASSESSMENT_TONE[status]} label={te(`assessmentStatus.${status}`)} />
    </span>
  );
}

export function MedVerificationBadge({ status }: { status: S["VerificationStatus"] | null | undefined }) {
  const te = useTranslations("enums");
  if (!status) return null;
  return (
    <span data-testid="med-verification" data-status={status}>
      <StatusBadge status={`verif_${status}`} label={te(`verificationStatus.${status}`)} />
    </span>
  );
}

const OUTCOME_TONE: Record<S["FitnessOutcome"], "success" | "warning" | "danger"> = {
  fit: "success",
  fit_with_restrictions: "warning",
  temporarily_unfit: "danger",
  permanently_unfit: "danger",
};

export function OutcomeBadge({ outcome }: { outcome: S["FitnessOutcome"] | null | undefined }) {
  const te = useTranslations("enums");
  if (!outcome) return null;
  return (
    <Badge tone={OUTCOME_TONE[outcome]} data-testid="fitness-outcome" data-outcome={outcome}>
      {te(`fitnessOutcome.${outcome}`)}
    </Badge>
  );
}

const REQ_TONE: Record<S["FitnessRequirementState"], string> = { met: "valid", expiring: "expiring", due: "scheduled", gap: "gap" };

export function RequirementStateBadge({ state }: { state: S["FitnessRequirementState"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="fitness-req-state" data-state={state}>
      <StatusBadge status={REQ_TONE[state]} label={te(`fitnessReqState.${state}`)} />
    </span>
  );
}

const BAND_TONE: Record<S["HookBand"], string> = { cleared: "valid", not_eligible: "gap", check_due: "expiring", restriction_applies: "partial" };

/** Tier-1 hook band with the server text in the page language (HK6-7; never "medical" for tier 1). */
export function HookBandBadge({ band, en, ar }: { band: S["HookBand"]; en: string; ar: string }) {
  const locale = useLocale();
  return (
    <span data-testid="fitness-band" data-band={band}>
      <StatusBadge status={BAND_TONE[band]} label={locale === "ar" ? ar : en} />
    </span>
  );
}

const HOLD_TONE: Record<S["HoldStatus"], string> = { active: "suspended", released: "valid", cancelled: "cancelled" };

export function HoldStatusBadge({ status }: { status: S["HoldStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="hold-status" data-status={status}>
      <StatusBadge status={HOLD_TONE[status]} label={te(`holdStatus.${status}`)} />
    </span>
  );
}

const REFERRAL_TONE: Record<S["ReferralStatus"], string> = { open: "open", assessed: "closed", cancelled: "cancelled" };

export function ReferralStatusBadge({ status, overdue }: { status: S["ReferralStatus"]; overdue?: boolean }) {
  const te = useTranslations("enums");
  const t = useTranslations("medical.referrals");
  return (
    <span className="inline-flex flex-wrap items-center gap-1" data-testid="referral-status" data-status={status} data-overdue={overdue ? "yes" : "no"}>
      <StatusBadge status={REFERRAL_TONE[status]} label={te(`referralStatus.${status}`)} />
      {overdue ? (
        <Badge tone="danger">
          <ShieldAlert aria-hidden />
          {t("overdue")}
        </Badge>
      ) : null}
    </span>
  );
}

/* ───────────── restrictions ───────────── */

export function RestrictionList({ items }: { items: S["RestrictionRead"][] | null | undefined }) {
  const locale = useLocale();
  const t = useTranslations("medical.common");
  if (!items?.length) return <span className="text-muted-foreground">—</span>;
  return (
    <ul className="flex flex-col gap-0.5 text-sm" data-testid="restrictions">
      {items.map((r, i) => (
        <li key={`${r.code}-${i}`} data-code={r.code}>
          {locale === "ar" ? r.label_ar : r.label_en}
          {r.value != null ? <span className="ltr ms-1">({t("kg", { n: r.value })})</span> : null}
          {r.text ? <span className="ms-1 text-muted-foreground">— {r.text}</span> : null}
        </li>
      ))}
    </ul>
  );
}

/* ───────────── catalogue labels and pickers ───────────── */

export function useFitnessCatalogue(projectId?: string | null) {
  const locale = useLocale();
  const q = useFitnessCodes({ project_id: projectId || null });
  const codes = q.data?.items ?? [];
  const label = (code: string) => {
    const c = codes.find((x) => x.code === code);
    return c ? (locale === "ar" ? c.name_ar : c.name_en) : code;
  };
  return { codes, label, get: (code: string) => codes.find((c) => c.code === code), isLoading: q.isLoading };
}

export function FitnessCodeLabel({ code, name }: { code: string; name?: string | null }) {
  return (
    <span>
      <Code className="font-medium">{code}</Code>
      {name ? <span className="ms-1.5">{name}</span> : null}
    </span>
  );
}

export function FitnessCodeSelect({
  id,
  label,
  value,
  onChange,
  projectId,
  required,
  exclude = [],
}: {
  id: string;
  label: string;
  value: string;
  onChange: (code: string) => void;
  projectId?: string | null;
  required?: boolean;
  exclude?: string[];
}) {
  const tc = useTranslations("common");
  const { codes, label: name } = useFitnessCatalogue(projectId);
  return (
    <FormField id={id} label={label} required={required}>
      <Select value={value} onChange={(e) => onChange(e.target.value)} data-testid={id}>
        <option value="">{tc("select")}</option>
        {codes
          .filter((c) => c.active && (c.code === value || !exclude.includes(c.code)))
          .map((c) => (
            <option key={c.code} value={c.code}>
              {c.code} — {name(c.code)}
            </option>
          ))}
      </Select>
    </FormField>
  );
}

export function MedProviderLabel({ p }: { p: { provider_code: string; legal_name_en: string; legal_name_ar: string } | null | undefined }) {
  const locale = useLocale();
  if (!p) return <>—</>;
  return (
    <span>
      <Code className="font-medium">{p.provider_code}</Code>
      <span className="ms-1.5">{locale === "ar" ? p.legal_name_ar : p.legal_name_en}</span>
    </span>
  );
}

export function MedProviderSelect({
  id,
  label,
  value,
  onChange,
  projectId,
  kinds,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (id: string, p?: S["MedicalProviderRead"]) => void;
  projectId?: string | null;
  kinds?: S["MedicalProviderKind"][];
  required?: boolean;
}) {
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const locale = useLocale();
  const q = useMedicalProviders({ page_size: 200, status: ["approved"], kind: kinds?.length ? kinds : null });
  const items = (q.data?.items ?? []).filter((p) => p.kind !== "site_clinic" || !projectId || p.project_ids.includes(projectId));
  return (
    <FormField id={id} label={label} required={required}>
      <Select value={value} onChange={(e) => onChange(e.target.value, items.find((p) => p.id === e.target.value))} data-testid={id}>
        <option value="">{tc("select")}</option>
        {items.map((p) => (
          <option key={p.id} value={p.id}>
            {p.provider_code} — {locale === "ar" ? p.legal_name_ar : p.legal_name_en} ({te(`medProviderKind.${p.kind}`)})
          </option>
        ))}
      </Select>
    </FormField>
  );
}

export function ExaminerSelect({
  id,
  label,
  value,
  onChange,
  providerId,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (id: string, x?: S["ExaminerRead"]) => void;
  providerId: string;
  required?: boolean;
}) {
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const t = useTranslations("medical.examiners");
  const locale = useLocale();
  const q = useMedicalExaminers({ provider_id: providerId || null, status: ["active"], page_size: 200 }, { enabled: Boolean(providerId) });
  const items = q.data?.items ?? [];
  return (
    <FormField id={id} label={label} required={required}>
      <Select value={value} disabled={!providerId} onChange={(e) => onChange(e.target.value, items.find((x) => x.id === e.target.value))} data-testid={id}>
        <option value="">{tc("select")}</option>
        {items.map((x) => (
          <option key={x.id} value={x.id}>
            {x.examiner_no} — {locale === "ar" ? x.full_name_ar : x.full_name_en} ({te(`examinerClass.${x.classification}`)}){x.user ? ` · ${t("linked")}` : ""}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

/** Tier note shown above tier-aware tables (OH-2): the server omits fields above the caller's tier. */
export function TierNote({ tier }: { tier: S["FitnessTier"] | null | undefined }) {
  const t = useTranslations("medical.common");
  if (!tier) return null;
  return (
    <p className="mb-2 text-xs text-muted-foreground" data-testid="fitness-tier" data-tier={tier}>
      {t(`tier.${tier}`)}
    </p>
  );
}

/** Prohibited-data hint for every 6a free-text field (P6-2). */
export function NoDiagnosisHint() {
  const t = useTranslations("medical.common");
  return <span data-testid="no-diagnosis-hint">{t("noDiagnosis")}</span>;
}

export function DateCell({ d, projectId }: { d: string | null | undefined; projectId?: string | null }) {
  const { date } = useFormatters(projectId);
  return <span className="ltr">{d ? date(d) : "—"}</span>;
}
