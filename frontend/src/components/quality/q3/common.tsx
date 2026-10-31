"use client";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { api, unwrap } from "@/lib/api/client";
import { useAttachments } from "@/lib/api/hse";
import { QGate, type Project, type QSettings, type S } from "@/components/quality/q0/common";

export type { Project, S };

/** Q3 pages need the logistics profile (Q-PRF-04): other projects see a short note, not the screen. */
export function Q3Gate({ children }: { children: (project: Project, settings: QSettings) => ReactNode }) {
  return (
    <QGate>
      {(p, s) =>
        s.sector_profile === "logistics" ? (
          <>{children(p, s)}</>
        ) : (
          <OtherProfile />
        )
      }
    </QGate>
  );
}

function OtherProfile() {
  const t = useTranslations("quality.logistics.common");
  return (
    <Alert tone="info" data-testid="q3-other-profile">
      {t("otherProfile")}
    </Alert>
  );
}

/** A temperature: always LTR so the minus sign stays before the digits in Arabic (AC-Q3-43). */
export function Temp({ v, unit = "°C" }: { v: string | number | null | undefined; unit?: string }) {
  if (v === null || v === undefined || v === "") return <>—</>;
  const n = Number(v);
  const txt = Number.isFinite(n) ? (Math.round(n * 100) / 100).toString().replace("-", "−") : String(v);
  return (
    <span dir="ltr" className="ltr whitespace-nowrap tabular-nums" data-temp={String(v)}>
      {txt} {unit}
    </span>
  );
}

export function Ltr({ children }: { children: ReactNode }) {
  return (
    <span dir="ltr" className="ltr">
      {children}
    </span>
  );
}

const SEV_TONE: Record<string, "danger" | "warning" | "neutral"> = { critical: "danger", major: "warning", minor: "neutral" };

export function SeverityBadge({ value, label }: { value: string; label: string }) {
  return (
    <Badge tone={SEV_TONE[value] ?? "neutral"} data-severity={value}>
      {label}
    </Badge>
  );
}

const DEC_TONE: Record<string, "success" | "warning" | "danger" | "info"> = { accept: "success", accept_with_deviation: "warning", quarantine: "info", reject: "danger" };

export function DecisionBadge({ value, label }: { value: string | null | undefined; label: string }) {
  if (!value) return <>—</>;
  return (
    <Badge tone={DEC_TONE[value] ?? "neutral"} data-decision={value}>
      {label}
    </Badge>
  );
}

export const LIVE_TONE: Record<string, "success" | "danger" | "warning" | "info"> = { in_range: "success", excursion: "danger", gap: "warning", not_mapped: "info" };

export type SetF<T> = (k: keyof T) => (e: { target: { value: string } }) => void;
export function useForm<T extends Record<string, string>>(init: T): [T, SetF<T>, (v: T | ((x: T) => T)) => void] {
  const [f, setF] = useState(init);
  return [f, (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value })), setF];
}
export const clean = (o: Record<string, string>) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== ""));

/** `datetime-local` value (Riyadh wall time) ↔ ISO with offset +03:00. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(new Date(iso).getTime() + 3 * 3600_000);
  return d.toISOString().slice(0, 16);
}
export function fromLocalInput(v: string): string | null {
  return v ? `${v}:00+03:00` : null;
}
export function nowLocal(): string {
  return toLocalInput(new Date().toISOString());
}

export function Section({ title, children, actions, testId }: { title: string; children: ReactNode; actions?: ReactNode; testId?: string }) {
  return (
    <Card className="mb-4" data-testid={testId}>
      <CardContent className="p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold">{title}</h2>
          {actions}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

/** Pick one of the files already uploaded to a record (owner decision, evidence, signature). */
export function AttachmentPick({
  ownerType,
  ownerId,
  value,
  onChange,
  label,
  id,
}: {
  ownerType: S["AttachmentOwner"];
  ownerId: string;
  value: string;
  onChange: (v: string) => void;
  label: string;
  id: string;
}) {
  const t = useTranslations("quality.logistics.common");
  const files = useAttachments(ownerType, ownerId);
  return (
    <FormField id={id} label={label}>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} data-testid={id}>
        <option value="">{t("noFile")}</option>
        {(files.data?.items ?? []).map((a) => (
          <option key={a.id} value={a.id}>
            {a.file_name}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

type Item = { item_code: string; text_en: string; text_ar: string; critical?: boolean; section_code?: string; na_allowed?: boolean };

/** A published quality checklist (kind `quality`, 6d engine) by template code. */
export function useQualityTemplate(code: string) {
  return useQuery({
    queryKey: ["q-q3-template", code],
    queryFn: async () => {
      const r = await unwrap(api.GET("/api/v1/checklist-templates", { params: { query: { kind: "quality", template_code: code, status: ["published"] as never, page_size: 5 } } }));
      const first = r.items[0];
      if (!first) return null;
      return unwrap(api.GET("/api/v1/checklist-templates/{template_id}", { params: { path: { template_id: first.id } } }));
    },
    staleTime: 10 * 60_000,
  });
}

export type Answer = { item_code: string; answer: string; note?: string };

/** Compact yes / no runner for a quality checklist; a non-compliant item needs a note (6d EXE-2). */
export function ChecklistRunner({ code, onSubmit, submitLabel, extra, busy, error }: { code: string; onSubmit: (a: Answer[]) => void; submitLabel: string; extra?: ReactNode; busy?: boolean; error?: unknown }) {
  const t = useTranslations("quality.logistics.common");
  const ar = useLocale() === "ar";
  const tpl = useQualityTemplate(code);
  const items = ((tpl.data as { items?: Item[] } | null | undefined)?.items ?? []) as Item[];
  const [ans, setAns] = useState<Record<string, Answer>>({});
  const set = useCallback((code: string, patch: Partial<Answer>) => setAns((x) => ({ ...x, [code]: { item_code: code, answer: "compliant", ...x[code], ...patch } })), []);
  const all = items.map((it) => ans[it.item_code] ?? { item_code: it.item_code, answer: "compliant" });
  const missingNote = all.some((a) => a.answer === "non_compliant" && (a.note ?? "").trim().length < 10);
  if (tpl.isLoading) return <p className="text-sm text-muted-foreground">…</p>;
  if (!items.length) return <Alert tone="warning">{t("noTemplate", { code })}</Alert>;
  return (
    <div data-testid={`q3-checklist-${code}`}>
      <MutationError error={error} />
      <ul className="divide-y rounded-md border">
        {items.map((it) => {
          const a = ans[it.item_code];
          const bad = a?.answer === "non_compliant";
          return (
            <li key={it.item_code} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 text-sm">
                {it.critical ? (
                  <Badge tone="danger" className="me-2">
                    {t("critical")}
                  </Badge>
                ) : null}
                {ar ? it.text_ar || it.text_en : it.text_en}
              </div>
              <div className="flex shrink-0 gap-1">
                <Button size="sm" variant={!bad ? "default" : "outline"} onClick={() => set(it.item_code, { answer: "compliant", note: undefined })} data-testid={`ans-${it.item_code}-ok`}>
                  {t("ok")}
                </Button>
                <Button size="sm" variant={bad ? "destructive" : "outline"} onClick={() => set(it.item_code, { answer: "non_compliant" })} data-testid={`ans-${it.item_code}-nc`}>
                  {t("notOk")}
                </Button>
              </div>
              {bad ? (
                <input
                  className="h-10 w-full rounded-md border px-2 text-sm sm:w-72"
                  placeholder={t("noteMin")}
                  value={a?.note ?? ""}
                  onChange={(e) => set(it.item_code, { note: e.target.value })}
                  data-testid={`ans-${it.item_code}-note`}
                />
              ) : null}
            </li>
          );
        })}
      </ul>
      {extra}
      <Button className="mt-3" disabled={busy || missingNote} onClick={() => onSubmit(all)} data-testid={`q3-checklist-${code}-submit`}>
        {submitLabel}
      </Button>
    </div>
  );
}

/** Month picker state for metrics (defaults to the previous month). */
export function usePrevMonth(): { year: number; month: number } {
  const d = new Date();
  const m = d.getUTCMonth();
  return m === 0 ? { year: d.getUTCFullYear() - 1, month: 12 } : { year: d.getUTCFullYear(), month: m };
}

export function Kpi({ label, value, unit, testId, tone }: { label: string; value: ReactNode; unit?: string; testId?: string; tone?: string }) {
  return (
    <div className={`rounded-md border p-3 ${tone === "danger" ? "border-danger/40" : ""}`} data-testid={testId}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums" dir="ltr">
        {value ?? "—"}
        {unit && value !== null && value !== undefined ? <span className="ms-1 text-sm font-normal">{unit}</span> : null}
      </p>
    </div>
  );
}
