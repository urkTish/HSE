"use client";
import { AlarmClock, CheckCircle2, Clock, Paperclip, TriangleAlert, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SubNav } from "@/components/access/common";
import { StatusBadge } from "@/components/common/status-badge";
import { ChoiceMark } from "@/components/heat/common";
import { useMeData } from "@/components/shell/me-context";
import type { Schemas } from "@/lib/api/client";
import { useFuReference } from "@/lib/api/followup";
import { useDisplay } from "@/lib/digits";
import { can, canWrite } from "@/lib/permissions";
import { cn } from "@/lib/utils";

type S = Schemas;

/* ───────────── capabilities (6f §5.10, 215–223) ───────────── */

export function useFuCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  const record = canWrite(me, "followup.record", pid);
  const approve = canWrite(me, "followup.approve", pid);
  return {
    me,
    view: can(me, "followup.view", pid),
    record,
    approve,
    /** Packs are never shown to Viewer / Client (P6f-5): only to those who prepare or approve them. */
    packs: can(me, "followup.record", pid) || can(me, "followup.approve", pid),
    settings: canWrite(me, "followup.settings", pid),
    draft: canWrite(me, "lesson.draft", pid),
    publish: canWrite(me, "lesson.publish", pid),
    acknowledge: canWrite(me, "lesson.acknowledge", pid),
    library: can(me, "lesson_library.view", pid),
    effectiveness: canWrite(me, "lesson.effectiveness", pid),
    rejectChange: canWrite(me, "field_library.publish", pid),
  };
}

/* ───────────── sub navigation ───────────── */

export function FuSubNav() {
  const t = useTranslations("fu.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/followup-overview", label: t("overview"), testId: "sub-fu-overview" },
        { href: "/notification-register", label: t("register"), testId: "sub-fu-register" },
        { href: "/followup-kpis", label: t("kpis"), testId: "sub-fu-kpis" },
        { href: "/followup-settings", label: t("settings"), show: can(me, "followup.view"), testId: "sub-fu-settings" },
      ]}
    />
  );
}

export function LessonSubNav() {
  const t = useTranslations("fu.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/lessons", label: t("library"), testId: "sub-fu-lessons" },
        { href: "/lesson-acknowledgements", label: t("acks"), show: can(me, "followup.view") || can(me, "lesson.acknowledge"), testId: "sub-fu-acks" },
        { href: "/effectiveness-checks", label: t("checks"), show: can(me, "followup.view"), testId: "sub-fu-checks" },
      ]}
    />
  );
}

/* ───────────── reference lists (server EN/AR labels, §3.11) ───────────── */

/** Labels of the 6f reference lists in the page language; the code while loading or when unknown. */
export function useFuRef() {
  const q = useFuReference();
  const ar = useLocale() === "ar";
  const lists = q.data?.lists as Record<string, S["FuRefItem"][]> | undefined;
  const items = useCallback((l: string): S["FuRefItem"][] => lists?.[l] ?? [], [lists]);
  const label = useCallback(
    (l: string, code: string | null | undefined): string => {
      if (!code) return "—";
      const it = lists?.[l]?.find((x) => x.code === code);
      return it ? (ar ? it.label_ar : it.label_en) : code;
    },
    [lists, ar],
  );
  return { items, label, lists: Object.keys(lists ?? {}) };
}

/** Bilingual text of a record in the page language (EN fallback). */
export function useBi() {
  const ar = useLocale() === "ar";
  return useCallback((en: string | null | undefined, arText: string | null | undefined) => (ar && arText?.trim() ? arText : (en ?? arText ?? "")), [ar]);
}

/* ───────────── status badges (colour + icon + words) ───────────── */

const REQ_TONE: Record<S["FuRequirementStatus"], string> = {
  due: "due",
  overdue: "overdue",
  submitted: "submitted",
  acknowledged: "completed",
  waived: "closed",
  not_required: "voided",
};

export function RequirementBadge({ status }: { status: S["FuRequirementStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="fu-status" data-status={status}>
      <StatusBadge status={REQ_TONE[status]} label={te(`fuRequirementStatus.${status}`)} />
    </span>
  );
}

type FuGroup = "fuPackStatus" | "fuSubmissionStatus" | "fuLessonStatus" | "fuDistributionStatus" | "fuCheckStatus" | "fuChangeStatus";
const TONE: Record<string, string> = { recorded: "submitted", in_review: "pending_review", acknowledged: "completed", not_applicable: "closed", withdrawn: "voided", scheduled: "planned", adopted: "completed" };

export function FuBadge({ group, status, testId = "fu-badge" }: { group: FuGroup; status: string; testId?: string }) {
  const te = useTranslations("enums");
  return (
    <span data-testid={testId} data-status={status}>
      <StatusBadge status={TONE[status] ?? status} label={te(`${group}.${status}` as "fuPackStatus.draft")} />
    </span>
  );
}

export function OnTimeBadge({ onTime }: { onTime: boolean | null | undefined }) {
  const t = useTranslations("fu.common");
  if (onTime === null || onTime === undefined) return null;
  return (
    <span data-testid="fu-on-time" data-on-time={onTime}>
      <StatusBadge status={onTime ? "on_time" : "late"} label={onTime ? t("onTime") : t("late")} />
    </span>
  );
}

export function ResultBadge({ result }: { result: S["FuEffectResult"] | null | undefined }) {
  const te = useTranslations("enums");
  if (!result) return <span>—</span>;
  return (
    <span data-testid="fu-result" data-result={result}>
      <StatusBadge status={result === "effective" ? "ok" : result === "partly_effective" ? "warning" : "error"} label={te(`fuEffectResult.${result}`)} />
    </span>
  );
}

/* ───────────── countdown to a due time (re-rendered every 30 s) ───────────── */

function useNow(intervalMs = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const h = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(h);
  }, [intervalMs]);
  return now;
}

/** "in 3 h 20 min" / "2 d 4 h overdue" with an icon; only while the item is still open. Presentation of the server's due time only. */
export function Countdown({ due, open = true, projectId, className }: { due: string | null | undefined; open?: boolean; projectId?: string | null; className?: string }) {
  const t = useTranslations("fu.common");
  const show = useDisplay(projectId);
  const now = useNow();
  if (!due || !open) return null;
  const ms = Date.parse(due) - now;
  const abs = Math.abs(ms);
  const d = Math.floor(abs / 86_400_000);
  const h = Math.floor((abs % 86_400_000) / 3_600_000);
  const m = Math.floor((abs % 3_600_000) / 60_000);
  let span: string;
  if (d > 0) span = t("spanDH", { d: show(String(d)), h: show(String(h)) });
  else if (h > 0) span = t("spanHM", { h: show(String(h)), m: show(String(m)) });
  else span = t("spanM", { m: show(String(Math.max(m, 0))) });
  const over = ms < 0;
  const soon = !over && ms < 6 * 3_600_000;
  const Icon = over ? TriangleAlert : soon ? AlarmClock : Clock;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", over ? "text-danger" : soon ? "text-warning" : "text-muted-foreground", className)} data-testid="fu-countdown" data-overdue={over}>
      <Icon aria-hidden className="size-3.5 shrink-0" />
      {over ? t("overdueBy", { span }) : t("dueIn", { span })}
    </span>
  );
}

/* ───────────── radio-style choice buttons (ChoiceMark, ≥ 48 px) ───────────── */

export function Choices<V extends string>({
  value,
  options,
  onChange,
  testId,
  label,
}: {
  value: V | "";
  options: { value: V; label: ReactNode; disabled?: boolean }[];
  onChange: (v: V) => void;
  testId: string;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2" data-testid={testId}>
      {options.map((o) => {
        const on = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            data-testid={`${testId}-${o.value}`}
            className={cn(
              "inline-flex min-h-12 items-center gap-2 rounded-md border px-3 text-start text-sm disabled:opacity-50",
              on ? "border-2 border-primary bg-primary/5 font-medium" : "border-input hover:bg-muted/50",
            )}
          >
            <ChoiceMark on={on} />
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ───────────── files sent as base64 (FuFileInput) ───────────── */

export async function toFileInput(f: File): Promise<S["FuFileInput"]> {
  const data = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(f);
  });
  return { file_name: f.name, content_base64: data.slice(data.indexOf(",") + 1), content_type: f.type || null };
}

/** File picker that keeps a list of chosen files (≤ max), each removable. */
export function FilePick({ files, onChange, max = 1, testId, accept }: { files: File[]; onChange: (f: File[]) => void; max?: number; testId: string; accept?: string }) {
  const t = useTranslations("fu.common");
  return (
    <div className="flex flex-col gap-2">
      {files.length < max ? (
        <Input
          type="file"
          accept={accept ?? "image/*,application/pdf,.eml,.msg"}
          multiple={max > 1}
          data-testid={testId}
          onChange={(e) => {
            const picked = Array.from(e.target.files ?? []);
            onChange([...files, ...picked].slice(0, max));
            e.target.value = "";
          }}
        />
      ) : null}
      {files.length ? (
        <ul className="flex flex-col gap-1 text-sm">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center gap-2">
              <Paperclip aria-hidden className="size-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate">{f.name}</span>
              <Button type="button" size="sm" variant="ghost" aria-label={t("removeFile")} onClick={() => onChange(files.filter((_, j) => j !== i))}>
                <X aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** "Fixed at generation" note for frozen pack fields (PK-2). */
export function FrozenNote() {
  const t = useTranslations("fu.pack");
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <CheckCircle2 aria-hidden className="size-3.5" />
      {t("frozen")}
    </span>
  );
}
