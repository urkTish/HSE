"use client";
import { Camera, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/common/form-field";
import { EmptyState } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { useFormatters } from "@/lib/use-formatters";
import { useQLabels, type S } from "../q0/common";

/** A photo for the API (6d `PhotoInput`): file name + base64 (EXIF stripped by the server). */
export type PhotoIn = { file_name: string; content_base64: string };

export function fileToBase64(file: File): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",")[1] ?? "");
    r.onerror = () => rej(r.error);
    r.readAsDataURL(file);
  });
}

/** Camera / file picker that keeps the chosen photos as base64 (works on the phone without upload calls). */
export function PhotoPicker({ value, onChange, max = 5, testId = "q1-photo-input" }: { value: PhotoIn[]; onChange: (v: PhotoIn[]) => void; max?: number; testId?: string }) {
  const t = useTranslations("quality.q1.common");
  const ref = useRef<HTMLInputElement>(null);
  async function add(files: FileList | null) {
    if (!files) return;
    const next = [...value];
    for (const f of Array.from(files).slice(0, max - value.length)) next.push({ file_name: f.name, content_base64: await fileToBase64(f) });
    onChange(next);
    if (ref.current) ref.current.value = "";
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => ref.current?.click()} disabled={value.length >= max}>
          <Camera aria-hidden />
          {t("addPhoto")}
        </Button>
        <span className="text-xs text-muted-foreground">{t("photoCount", { n: value.length, max })}</span>
        <input ref={ref} type="file" accept="image/jpeg,image/png" capture="environment" multiple className="sr-only" data-testid={testId} onChange={(e) => void add(e.target.files)} />
      </div>
      {value.length ? (
        <ul className="flex flex-wrap gap-2">
          {value.map((p, i) => (
            <li key={`${p.file_name}-${i}`} className="flex items-center gap-1 rounded border px-2 py-1 text-xs">
              <span className="ltr max-w-40 truncate">{p.file_name}</span>
              <button type="button" aria-label={t("removePhoto")} onClick={() => onChange(value.filter((_, j) => j !== i))}>
                <X aria-hidden className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-xs text-muted-foreground">{t("photoHint")}</p>
    </div>
  );
}

export type PaperIn = { name: string; organisation: string; position: string; signed_on: string; scans: PhotoIn[] };

/** Q-RPM-08: record the decision of an external signatory with the signed scan. */
export function PaperFields({ value, onChange }: { value: PaperIn; onChange: (v: PaperIn) => void }) {
  const t = useTranslations("quality.q1.paper");
  const set = (k: keyof Omit<PaperIn, "scans">) => (e: { target: { value: string } }) => onChange({ ...value, [k]: e.target.value });
  return (
    <div className="grid gap-3 rounded-lg border p-3 sm:grid-cols-2" data-testid="q1-paper-fields">
      <p className="text-sm font-medium sm:col-span-2">{t("title")}</p>
      <FormField id="pp-name" label={t("name")} required><Input value={value.name} onChange={set("name")} data-testid="q1-paper-name" /></FormField>
      <FormField id="pp-org" label={t("organisation")} required><Input value={value.organisation} onChange={set("organisation")} data-testid="q1-paper-org" /></FormField>
      <FormField id="pp-pos" label={t("position")} required><Input value={value.position} onChange={set("position")} data-testid="q1-paper-position" /></FormField>
      <FormField id="pp-date" label={t("signedOn")} required><Input type="date" value={value.signed_on} onChange={set("signed_on")} data-testid="q1-paper-date" /></FormField>
      <FormField id="pp-scan" label={t("scan")} required className="sm:col-span-2">
        <Input type="file" accept=".pdf,.jpg,.jpeg,.png" data-testid="q1-paper-scan"
          onChange={async (e) => { const f = e.target.files?.[0]; if (f) onChange({ ...value, scans: [{ file_name: f.name, content_base64: await fileToBase64(f) }] }); }} />
      </FormField>
    </div>
  );
}

export function emptyPaper(): PaperIn {
  return { name: "", organisation: "", position: "", signed_on: "", scans: [] };
}

export function paperReady(p: PaperIn): boolean {
  return Boolean(p.name && p.organisation && p.position && p.signed_on && p.scans.length);
}

const TYPE_TONE: Record<string, "danger" | "warning" | "info" | "neutral"> = { H: "danger", W: "warning", R: "info", S: "neutral" };

/** Hold / Witness / Review / Surveillance chip (colour plus the letter, never colour alone). */
export function PointTypeChip({ value }: { value: string | null | undefined }) {
  const { l } = useQLabels();
  if (!value) return <>—</>;
  return (
    <Badge tone={TYPE_TONE[value] ?? "neutral"} data-point-type={value} title={l("point_type", value)}>
      <span className="ltr font-semibold">{value}</span>
      <span className="ms-1 hidden sm:inline">{l("point_type", value)}</span>
    </Badge>
  );
}

const Q1_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  draft: "neutral",
  submitted: "info",
  scheduled: "info",
  approved: "success",
  approved_with_comments: "success",
  rejected: "danger",
  witness_waived: "warning",
  reinspection_requested: "warning",
  cancelled: "neutral",
  voided: "neutral",
  revise_resubmit: "warning",
  superseded: "neutral",
  withdrawn: "neutral",
  open: "warning",
  ready_for_review: "info",
  closed: "success",
  compiled: "info",
  accepted: "success",
  returned: "warning",
  not_ready: "warning",
  waived: "warning",
  responded: "info",
  current: "success",
};

export function Q1Status({ kind, value }: { kind: string; value: string | null | undefined }) {
  const { l } = useQLabels();
  if (!value) return <>—</>;
  return (
    <Badge tone={Q1_TONE[value] ?? "neutral"} data-status={value}>
      {l(kind, value)}
    </Badge>
  );
}

export function SignoffList({ items, recordType }: { items: S["QSignoffRead"][]; recordType: string }) {
  const t = useTranslations("quality.q1.common");
  const ar = useLocale() === "ar";
  const { dateTime } = useFormatters();
  const { step, l } = useQLabels();
  if (!items.length) return <EmptyState message={t("noSignoffs")} />;
  return (
    <ul className="flex flex-col gap-2" data-testid="q1-signoffs">
      {items.map((s) => (
        <li key={s.id} className="glass rounded-lg border p-3 text-sm" data-step={s.step} data-channel={s.channel}>
          <p className="font-medium">
            {step(recordType, s.step)} · {l("ir_result", s.decision)}
          </p>
          <p>{ar ? s.text_ar : s.text_en}</p>
          <p className="text-xs text-muted-foreground">
            {dateTime(s.signed_at)}
            {s.comment ? ` — ${s.comment}` : ""}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function LinkList({ items }: { items: S["QLinkRead"][] }) {
  const t = useTranslations("quality.q1.common");
  const { l, recordType } = useQLabels();
  if (!items.length) return <EmptyState message={t("noLinks")} />;
  return (
    <ul className="flex flex-col gap-2" data-testid="q1-links">
      {items.map((k) => (
        <li key={k.id} className="glass flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm">
          <span className="text-muted-foreground">{l("link_kind", k.kind)}</span>
          <span>{recordType(k.record_type)}</span>
          {k.visible && k.link_path ? (
            <Link href={k.link_path} className="ltr text-primary hover:underline">
              {k.ref}
            </Link>
          ) : (
            <span>{t("notVisible")}</span>
          )}
          {k.voided ? <span className="text-xs text-danger">{t("voided")}</span> : null}
        </li>
      ))}
    </ul>
  );
}

/** Blockers or warnings returned by the server (hold points, dossier completeness). */
export function BlockerList({ items, tone = "danger", testId }: { items: S["QBlockerRead"][]; tone?: "danger" | "warning"; testId: string }) {
  const ar = useLocale() === "ar";
  if (!items.length) return null;
  return (
    <ul className={`flex flex-col gap-1 rounded-lg border p-3 text-sm ${tone === "danger" ? "border-danger/40" : "border-warning/40"}`} data-testid={testId}>
      {items.map((b, i) => (
        <li key={`${b.code}-${i}`} data-code={b.code} data-letter={b.letter ?? ""}>
          {b.letter ? <span className="ltr me-1 font-mono text-xs">({b.letter})</span> : null}
          <span dir="auto">{ar ? b.detail_ar : b.detail_en}</span>
        </li>
      ))}
    </ul>
  );
}

/** Small tab bar used by the Q1 detail pages. */
export function Tabs<T extends string>({ tabs, value, onChange, label, prefix }: { tabs: readonly T[]; value: T; onChange: (v: T) => void; label: (v: T) => string; prefix: string }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b" role="tablist">
      {tabs.map((k) => (
        <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)} data-testid={`${prefix}-tab-${k}`}
          className={`min-h-touch shrink-0 rounded-t-md px-3 text-sm ${value === k ? "border-b-2 border-primary font-semibold" : "text-muted-foreground"}`}>
          {label(k)}
        </button>
      ))}
    </div>
  );
}

export function useLocalState<T>(init: T): [T, (v: T) => void] {
  return useState<T>(init);
}
