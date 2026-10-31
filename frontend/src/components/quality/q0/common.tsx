"use client";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useWarningToasts } from "@/components/common/api-warnings";
import { FormField } from "@/components/common/form-field";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useQReference, useQSettings, useQualityRefresh } from "@/lib/api/quality/q0";
import { useMeData } from "@/components/shell/me-context";
import { can, canWrite, type Capability } from "@/lib/permissions";

export type S = Schemas;
export type Project = S["ProjectRead"];
export type QSettings = S["QSettingsRead"];

/** Server list labels (EN / AR) from GET /quality/reference: one source for every list value. */
export function useQLabels() {
  const ref = useQReference();
  const ar = useLocale() === "ar";
  const labels = ref.data?.labels;
  const types = ref.data?.record_types;
  return {
    l: useCallback(
      (kind: string, value: string | null | undefined): string => {
        if (!value) return "—";
        const pair = labels?.[kind]?.[value];
        return pair ? (ar ? pair[1] : pair[0]) || value : value;
      },
      [labels, ar],
    ),
    recordType: useCallback(
      (code: string) => {
        const d = types?.find((x) => x.code === code);
        return d ? (ar ? d.ar : d.en) : code;
      },
      [types, ar],
    ),
    /** EN / AR name of a record type's step from the reference (any part). */
    step: useCallback(
      (code: string, stepCode: string) => {
        const s = types?.find((x) => x.code === code)?.steps.find((x) => x.code === stepCode);
        return s ? String((ar ? s.ar : s.en) || stepCode) : stepCode;
      },
      [types, ar],
    ),
    options: useCallback(
      (kind: string) => Object.entries(labels?.[kind] ?? {}).map(([value, pair]) => ({ value, label: (ar ? pair[1] : pair[0]) || value })),
      [labels, ar],
    ),
    ready: Boolean(ref.data),
  };
}

/** Capability checks on the current project (the server is the control; this hides actions). */
export function useQCaps(projectId: string) {
  const me = useMeData();
  return {
    has: (c: Capability) => can(me, c, projectId),
    write: (c: Capability) => canWrite(me, c, projectId),
    manager: me.is_hse_manager,
    me,
  };
}

/**
 * Project + Quality settings for every Q0 page. Before the profile is chosen the page says "Choose the
 * sector profile" to 239 holders and nothing to others (Q-PRF-01).
 */
export function QGate({ children }: { children: (project: Project, settings: QSettings) => ReactNode }) {
  return <ProjectGate>{(p) => <Inner project={p}>{children}</Inner>}</ProjectGate>;
}

function Inner({ project, children }: { project: Project; children: (project: Project, settings: QSettings) => ReactNode }) {
  const t = useTranslations("quality.common");
  const q = useQSettings(project.id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data;
  if (!s) return <LoadingState />;
  if (!s.sector_profile) {
    return (
      <Alert tone="info" data-testid="q-choose-profile">
        <p className="font-medium">{t("chooseProfileTitle")}</p>
        <p>{s.can_edit ? t("chooseProfileBody") : t("notConfigured")}</p>
        {s.can_edit ? (
          <Button asChild size="sm" className="mt-2">
            <Link href="/quality/settings">{t("openSettings")}</Link>
          </Button>
        ) : null}
      </Alert>
    );
  }
  return <>{children(project, s)}</>;
}

export function ProfileBadge({ profile }: { profile: string | null | undefined }) {
  const { l } = useQLabels();
  if (!profile) return null;
  return (
    <Badge tone="info" data-testid="q-profile-badge" data-profile={profile}>
      {l("profile", profile)}
    </Badge>
  );
}

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  draft: "neutral",
  open: "warning",
  disposition_proposed: "info",
  disposition_approved: "info",
  pending_verification: "info",
  closed: "success",
  voided: "neutral",
  received: "warning",
  acknowledged: "info",
  under_investigation: "info",
  responded: "info",
  withdrawn: "neutral",
  issued: "warning",
  expired: "neutral",
  actioned: "info",
  approved: "success",
  conditional: "warning",
  pending_approval: "info",
  suspended: "danger",
  disqualified: "danger",
  published: "success",
  superseded: "neutral",
  retired: "neutral",
  calibrated: "success",
  due_soon: "warning",
  overdue: "danger",
  out_of_service: "danger",
  limited_use: "warning",
  not_required: "neutral",
  unknown: "neutral",
};

export function StatusBadge({ kind, value }: { kind: string; value: string | null | undefined }) {
  const { l } = useQLabels();
  if (!value) return <>—</>;
  return (
    <Badge tone={STATUS_TONE[value] ?? "neutral"} data-status={value}>
      {l(kind, value)}
    </Badge>
  );
}

export function ClassBadge({ value }: { value: string | null | undefined }) {
  const { l } = useQLabels();
  if (!value) return <>—</>;
  const tone = value === "critical" ? "danger" : value === "major" ? "warning" : "neutral";
  return (
    <Badge tone={tone} data-class={value}>
      {l("ncr_class", value)}
    </Badge>
  );
}

/** Runs one write: busy flag, error for MutationError, warning toasts, success toast and refresh. */
export function useRun() {
  const refresh = useQualityRefresh();
  const warn = useWarningToasts();
  const t = useTranslations("quality.common");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = useCallback(
    async <T,>(fn: () => Promise<T>, done?: string): Promise<T | undefined> => {
      setBusy(true);
      setError(null);
      try {
        const out = await fn();
        const w = (out as { warnings?: S["ApiWarning"][] } | undefined)?.warnings;
        if (w?.length) warn(w);
        toast.success(done ?? t("saved"));
        await refresh();
        return out;
      } catch (e) {
        setError(e);
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [refresh, warn, t],
  );
  return { run, busy, error, setError };
}

/** A dialog asking for a reason or comment (≥ `min` characters) before an action. */
export function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  min = 20,
  label,
  confirm,
  onSubmit,
  testId,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: string;
  min?: number;
  label?: string;
  confirm: string;
  onSubmit: (text: string) => Promise<unknown>;
  testId?: string;
}) {
  const t = useTranslations("quality.common");
  const tc = useTranslations("common");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const short = text.trim().length < min;
  async function go() {
    setBusy(true);
    setError(null);
    try {
      await onSubmit(text.trim());
      setText("");
      onOpenChange(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={tc("close")} data-testid={testId}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <MutationError error={error} />
        <FormField id="q-reason" label={label ?? t("reason")} hint={t("minChars", { n: min })} required>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} data-testid="q-reason-input" />
        </FormField>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tc("cancel")}
          </Button>
          <Button onClick={go} disabled={busy || short} data-testid="q-reason-confirm">
            {confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function userText(u: { full_name_en: string; full_name_ar?: string | null } | null | undefined, ar: boolean): string {
  if (!u) return "—";
  return ar && u.full_name_ar ? u.full_name_ar : u.full_name_en;
}

/** Bilingual free text: the page language first, else the other. */
export function useBilingual() {
  const ar = useLocale() === "ar";
  return (en: string | null | undefined, arText: string | null | undefined) => ((ar ? arText || en : en || arText) ?? "") || "—";
}
