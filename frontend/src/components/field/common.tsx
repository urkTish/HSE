"use client";
import { Camera, CheckCircle2, Eraser, ImagePlus, OctagonAlert, Star, Trash2, WifiOff, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { StatusBadge } from "@/components/common/status-badge";
import { PossibleIdHint } from "@/components/common/api-warnings";
import { Code, StepDialog, SubNav } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import type { Schemas } from "@/lib/api/client";
import { useFieldReference, useFieldRefresh } from "@/lib/api/field";
import { compressPhoto } from "@/lib/field-offline";
import { can, canWrite } from "@/lib/permissions";
import { cn } from "@/lib/utils";

type S = Schemas;

/* ───────────── capabilities (6d §5.13, 191–201; Phase 1 33 records inspections) ───────────── */

export function useFieldCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  return {
    libraryView: can(me, "field_library.view", pid),
    author: canWrite(me, "field_library.author", pid),
    publish: canWrite(me, "field_library.publish", pid),
    /** 6d settings and switch dates are edited with 193 (HSE Manager). */
    settings: canWrite(me, "field_library.publish", pid),
    audit: canWrite(me, "field_audit.conduct", pid),
    issue: canWrite(me, "field_audit.issue", pid),
    release: canWrite(me, "stop_work.release", pid),
    campaign: canWrite(me, "briefing_campaign.manage", pid),
    talk: canWrite(me, "toolbox.record", pid),
    names: can(me, "toolbox_names.view", pid),
    view: can(me, "field.view", pid),
    void: canWrite(me, "field.void", pid),
    record: canWrite(me, "inspection.record", pid),
    plans: canWrite(me, "inspection.plan_manage", pid),
    meId: me.id,
  };
}

/* ───────────── sub navigation ───────────── */

export function FieldOverviewSubNav() {
  const t = useTranslations("field.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/field-overview", label: t("overview"), testId: "sub-fd-overview" },
        { href: "/field-kpis", label: t("kpis"), show: can(me, "field.view"), testId: "sub-fd-kpis" },
        { href: "/field-settings", label: t("settings"), show: can(me, "field.view"), testId: "sub-fd-settings" },
      ]}
    />
  );
}

export function FieldInspectSubNav() {
  const t = useTranslations("field.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/field-inspections/new", label: t("run"), show: can(me, "inspection.record"), testId: "sub-fd-run" },
        { href: "/field-findings", label: t("findings"), show: can(me, "field.view"), testId: "sub-fd-findings" },
        { href: "/stop-work-orders", label: t("stops"), show: can(me, "field.view"), testId: "sub-fd-stops" },
      ]}
    />
  );
}

export function FieldLibrarySubNav() {
  const t = useTranslations("field.nav");
  return (
    <SubNav
      items={[
        { href: "/checklist-templates", label: t("templates"), testId: "sub-fd-templates" },
        { href: "/toolbox-topics", label: t("topics"), testId: "sub-fd-topics" },
      ]}
    />
  );
}

export function FieldAuditSubNav() {
  const t = useTranslations("field.nav");
  return (
    <SubNav
      items={[
        { href: "/field-audits", label: t("audits"), testId: "sub-fd-audits" },
        { href: "/audit-programme", label: t("programme"), testId: "sub-fd-programme" },
      ]}
    />
  );
}

export function FieldTalkSubNav() {
  const t = useTranslations("field.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/toolbox-talks", label: t("talks"), testId: "sub-fd-talks" },
        { href: "/toolbox-talks/new", label: t("recordTalk"), show: can(me, "toolbox.record"), testId: "sub-fd-talk-new" },
        { href: "/briefing-campaigns", label: t("campaigns"), testId: "sub-fd-campaigns" },
      ]}
    />
  );
}

/* ───────────── reference lists (IT, FS, AT, AF, AG, categories, roles, reasons) ───────────── */

type RefList = keyof S["FieldReference"];

/** Labels of the seeded 6d reference lists in the page language (server EN/AR); the code while loading. */
export function useFieldRef() {
  const q = useFieldReference();
  const ar = useLocale() === "ar";
  const label = useCallback(
    (list: RefList, code: string | null | undefined): string => {
      if (!code) return "—";
      const item = q.data?.[list]?.find((x) => x.code === code);
      return item ? (ar ? item.label_ar : item.label_en) : code;
    },
    [q.data, ar],
  );
  const items = useCallback((list: RefList): S["FieldRefItem"][] => q.data?.[list] ?? [], [q.data]);
  /** A finding severity (inspection FS) or an audit grade (AF). */
  const severity = useCallback((code: string) => (["minor", "major", "critical"].includes(code) ? label("finding_severities", code) : label("audit_finding_grades", code)), [label]);
  return { label, items, severity, ready: Boolean(q.data) };
}

/** Bilingual text of a record in the page language (EN fallback). */
export function useBi() {
  const ar = useLocale() === "ar";
  return useCallback((en: string | null | undefined, arText: string | null | undefined) => (ar && arText?.trim() ? arText : (en ?? arText ?? "")), [ar]);
}

/* ───────────── badges (colour + icon + words) ───────────── */

export function VersionStatusBadge({ status, overdue }: { status: S["VersionStatus"]; overdue?: boolean }) {
  const te = useTranslations("enums");
  const t = useTranslations("field.common");
  return (
    <span className="inline-flex flex-wrap items-center gap-1" data-testid="version-status" data-status={status}>
      <StatusBadge status={status} label={te(`fdVersionStatus.${status}`)} />
      {overdue && status === "published" ? (
        <span data-testid="review-overdue">
          <StatusBadge status="overdue" label={t("reviewOverdue")} />
        </span>
      ) : null}
    </span>
  );
}

export function ResultBadge({ result, testId = "result" }: { result: S["ResponseResult"] | null | undefined; testId?: string }) {
  const te = useTranslations("enums");
  if (!result) return <span>—</span>;
  return (
    <span data-testid={testId} data-result={result}>
      <Badge tone={result === "pass" ? "success" : "danger"}>
        {result === "pass" ? <CheckCircle2 aria-hidden /> : <XCircle aria-hidden />}
        {te(`fdResult.${result}`)}
      </Badge>
    </span>
  );
}

export function FieldSeverityBadge({ severity }: { severity: string }) {
  const { severity: label } = useFieldRef();
  const tone = severity === "critical" || severity === "major_nc" ? "danger" : severity === "major" || severity === "minor_nc" ? "warning" : severity === "minor" ? "info" : "neutral";
  return (
    <Badge tone={tone} data-testid="fd-severity" data-severity={severity}>
      {severity === "critical" ? <OctagonAlert aria-hidden /> : null}
      {label(severity)}
    </Badge>
  );
}

export function CriticalMark() {
  const t = useTranslations("field.common");
  return (
    <Badge tone="danger" className="shrink-0" data-testid="critical-mark">
      <Star aria-hidden />
      {t("critical")}
    </Badge>
  );
}

const STOP_TONE: Record<S["StopOrderStatus"], string> = { active: "overdue", released: "done", voided: "voided" };
export function StopStatusBadge({ status }: { status: S["StopOrderStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="stop-status" data-status={status}>
      {status === "active" ? (
        <Badge tone="danger">
          <OctagonAlert aria-hidden />
          {te("fdStopStatus.active")}
        </Badge>
      ) : (
        <StatusBadge status={STOP_TONE[status]} label={te(`fdStopStatus.${status}`)} />
      )}
    </span>
  );
}

const AUDIT_TONE: Record<S["AuditStatus"], string> = {
  planned: "planned",
  in_progress: "in_progress",
  fieldwork_complete: "pending_review",
  issued: "issued",
  closed: "closed",
  cancelled: "cancelled",
  voided: "voided",
};
export function AuditStatusBadge({ status }: { status: S["AuditStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="audit-status" data-status={status}>
      <StatusBadge status={AUDIT_TONE[status]} label={te(`fdAuditStatus.${status}`)} />
    </span>
  );
}

const TALK_TONE: Record<S["TalkStatus"], string> = { delivered: "done", locked: "locked", voided: "voided" };
export function TalkStatusBadge({ status }: { status: S["TalkStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="talk-status" data-status={status}>
      <StatusBadge status={TALK_TONE[status]} label={te(`fdTalkStatus.${status}`)} />
    </span>
  );
}

const CMP_TONE: Record<S["CampaignStatus"], string> = { draft: "draft", issued: "issued", closed: "closed", cancelled: "cancelled" };
export function CampaignStatusBadge({ status }: { status: S["CampaignStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="campaign-status" data-status={status}>
      <StatusBadge status={CMP_TONE[status]} label={te(`fdCampaignStatus.${status}`)} />
    </span>
  );
}

export function GradeBadge({ grade }: { grade: S["AuditGrade"] | null | undefined }) {
  const { label } = useFieldRef();
  if (!grade) return <span>—</span>;
  const tone = grade === "A" ? "success" : grade === "B" ? "info" : grade === "C" ? "warning" : "danger";
  return (
    <Badge tone={tone} data-testid="audit-grade" data-grade={grade}>
      <span className="font-semibold ltr">{grade}</span> {label("audit_grades", grade)}
    </Badge>
  );
}

/** "Recorded offline" label (EXE-7). */
export function OfflineLabel({ show, minutes }: { show: boolean | null | undefined; minutes?: number | null }) {
  const t = useTranslations("field.common");
  if (!show) return null;
  return (
    <Badge tone="warning" data-testid="recorded-offline">
      <WifiOff aria-hidden />
      {minutes ? t("recordedOfflineMin", { n: minutes }) : t("recordedOffline")}
    </Badge>
  );
}

/** Score as the server sends it ("—" when not applicable); never computed here (FM-1). */
export function Score({ v, className, testId = "score" }: { v: string | null | undefined; className?: string; testId?: string }) {
  return (
    <bdi className={cn("ltr tabular-nums", className)} data-testid={testId}>
      {v === null || v === undefined ? "—" : `${v} %`}
    </bdi>
  );
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

/** Hint under every 6d free text (P6d-2, P1-8). */
export function NoNamesHint() {
  const t = useTranslations("field.common");
  return <span data-testid="no-names-hint">{t("noNames")}</span>;
}

/* ───────────── inputs ───────────── */

/** Up to `max` photos taken with the camera or picked, compressed on the phone (EXE-5). */
export function PhotoPicker({ value, onChange, max = 3, testId = "photos", required }: { value: S["PhotoInput"][]; onChange: (v: S["PhotoInput"][]) => void; max?: number; testId?: string; required?: boolean }) {
  const t = useTranslations("field.common");
  const ref = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  async function add(files: FileList | null) {
    if (!files?.length) return;
    setError("");
    const next = [...value];
    for (const f of Array.from(files)) {
      if (next.length >= max) break;
      try {
        next.push(await compressPhoto(f));
      } catch {
        setError(t("photoTooLarge"));
      }
    }
    onChange(next);
    if (ref.current) ref.current.value = "";
  }
  return (
    <div className="flex flex-col gap-2" data-testid={testId} data-count={value.length}>
      <div className="flex flex-wrap items-center gap-2">
        {value.map((p, i) => (
          <span key={`${p.file_name}-${i}`} className="relative inline-flex">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`data:image/jpeg;base64,${p.content_base64}`} alt={t("photoN", { n: i + 1 })} className="size-16 rounded-md border object-cover" />
            <Button type="button" variant="outline" size="sm" className="absolute -end-2 -top-2 size-7 rounded-full p-0" aria-label={t("removePhoto", { n: i + 1 })} onClick={() => onChange(value.filter((_, j) => j !== i))}>
              <Trash2 aria-hidden className="size-3.5" />
            </Button>
          </span>
        ))}
        {value.length < max ? (
          <Button type="button" variant="outline" className="min-h-11" onClick={() => ref.current?.click()} data-testid={`${testId}-add`}>
            {value.length ? <ImagePlus aria-hidden /> : <Camera aria-hidden />}
            {t("addPhoto")}
            {required && !value.length ? <span className="text-danger">*</span> : null}
          </Button>
        ) : null}
        <input ref={ref} type="file" accept="image/jpeg,image/png" capture="environment" multiple className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => void add(e.target.files)} data-testid={`${testId}-input`} />
      </div>
      <span className="text-xs text-muted-foreground">{t("photoHint")}</span>
      {error ? <span className="text-xs text-danger">{error}</span> : null}
    </div>
  );
}

/** Signature drawn on the phone (TBT-7); returned as a PNG PhotoInput. */
export function SignaturePad({ onDone, onCancel }: { onDone: (p: S["PhotoInput"]) => void; onCancel: () => void }) {
  const t = useTranslations("field.common");
  const ref = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const c = ref.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx) return;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#111";
  }, []);
  const pos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: ((e.clientX - r.left) * e.currentTarget.width) / r.width, y: ((e.clientY - r.top) * e.currentTarget.height) / r.height };
  };
  function clear() {
    const c = ref.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx) return;
    ctx.fillRect(0, 0, c.width, c.height);
    setDrawn(false);
  }
  return (
    <div className="flex flex-col gap-2" data-testid="signature-pad">
      <canvas
        ref={ref}
        width={600}
        height={200}
        className="h-32 w-full touch-none rounded-md border bg-white"
        aria-label={t("signHere")}
        data-testid="signature-canvas"
        onPointerDown={(e) => {
          drawing.current = true;
          const ctx = e.currentTarget.getContext("2d");
          const p = pos(e);
          ctx?.beginPath();
          ctx?.moveTo(p.x, p.y);
        }}
        onPointerMove={(e) => {
          if (!drawing.current) return;
          const ctx = e.currentTarget.getContext("2d");
          const p = pos(e);
          ctx?.lineTo(p.x, p.y);
          ctx?.stroke();
          setDrawn(true);
        }}
        onPointerUp={() => (drawing.current = false)}
        onPointerLeave={() => (drawing.current = false)}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          className="min-h-11"
          disabled={!drawn}
          onClick={() => {
            const data = ref.current?.toDataURL("image/png") ?? "";
            onDone({ file_name: "signature.png", content_base64: data.slice(data.indexOf(",") + 1) });
          }}
          data-testid="signature-done"
        >
          {t("signDone")}
        </Button>
        <Button type="button" variant="outline" className="min-h-11" onClick={clear}>
          <Eraser aria-hidden />
          {t("signClear")}
        </Button>
        <Button type="button" variant="ghost" className="min-h-11" onClick={onCancel}>
          {t("back")}
        </Button>
      </div>
    </div>
  );
}

/** Reason ≥ min characters (void, retire, cancel). */
export function FieldReasonDialog({
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
  const t = useTranslations("field.common");
  const refresh = useFieldRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      destructive={destructive}
      dismissLabel={t("back")}
      disabled={reason.trim().length < min}
      testId="fd-reason-confirm"
      onConfirm={async () => {
        await onConfirm(reason.trim());
        await refresh();
      }}
      onClose={onClose}
    >
      {children}
      <FormField id="fd-reason" label={t("reason")} required hint={t("reasonMin", { min, n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="fd-reason" />
      </FormField>
      <PossibleIdHint text={reason} />
    </StepDialog>
  );
}
