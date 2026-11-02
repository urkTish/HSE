"use client";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, openSignedUrl, postForm, unwrap } from "@/lib/api/client";
import { QGate, type Project, type QSettings, type S } from "@/components/quality/q0/common";

export type { Project, QSettings, S };

type TFn = ((key: string, values?: Record<string, string | number>) => string) & { has: (key: string) => boolean };

/** Q4 messages with dynamic keys (list values): a loosely typed `useTranslations`. */
export function useT(ns: string): TFn {
  return useTranslations(ns as never) as unknown as TFn;
}

/** Q4 pages serve both sector profiles (shared parts, §E): only the profile must be chosen. */
export function Q4Gate({ children }: { children: (project: Project, settings: QSettings) => ReactNode }) {
  return <QGate>{(p, s) => <>{children(p, s)}</>}</QGate>;
}

/** Numbers, money, σ and codes stay left-to-right in Arabic (AC-Q4-34). */
export function Ltr({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span dir="ltr" className={`ltr tabular-nums ${className}`}>
      {children}
    </span>
  );
}

const TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  draft: "neutral", for_review: "info", approved: "success", superseded: "neutral", obsolete: "neutral",
  sent: "info", responded: "success", cancelled: "neutral", planned: "neutral", scheduled: "info", done: "success",
  postponed: "warning", in_progress: "info", fieldwork_complete: "warning", issued: "success", closed: "success",
  voided: "neutral", held: "info", minutes_issued: "success", submitted: "info", provisional: "warning", final: "success",
  green: "success", amber: "warning", red: "danger",
};

/** A status chip with the Q4 label (`quality.q4.status.<value>`). */
export function Q4Status({ value }: { value: string | null | undefined }) {
  const t = useT("quality.q4.status");
  if (!value) return <>—</>;
  return (
    <Badge tone={TONE[value] ?? "neutral"} data-status={value}>
      {t.has(value) ? t(value) : value}
    </Badge>
  );
}

export function Band({ band }: { band: string | null | undefined }) {
  if (!band) return <>—</>;
  const tone = band === "A" ? "success" : band === "B" ? "info" : band === "C" ? "warning" : "danger";
  return (
    <Badge tone={tone} data-band={band}>
      <Ltr>{band}</Ltr>
    </Badge>
  );
}

export function useName() {
  const ar = useLocale() === "ar";
  return (en: string | null | undefined, arText: string | null | undefined) => ((ar ? arText || en : en || arText) ?? "") || "—";
}

export function useForm<T extends Record<string, string>>(init: T) {
  const [f, setF] = useState<T>(init);
  const set = (k: keyof T) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  return [f, set, setF] as const;
}

export function clean(f: Record<string, string>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ""));
}

/** Upload one file to a record (attachments engine: scan + shrink) and return its id. */
export async function upload(ownerType: string, ownerId: string, file: File): Promise<string> {
  const fd = new FormData();
  fd.append("owner_type", ownerType);
  fd.append("owner_id", ownerId);
  fd.append("file", file);
  const a = await postForm<{ id: string }>("/api/v1/attachments", fd);
  return a.id;
}

export function FileButton({ id, label, testId }: { id: string | null | undefined; label: string; testId?: string }) {
  if (!id) return null;
  return (
    <Button size="sm" variant="outline" data-testid={testId} onClick={() => void openSignedUrl(() => unwrap(api.POST("/api/v1/attachments/{attachment_id}/signed-url", { params: { path: { attachment_id: id } } })))}>
      {label}
    </Button>
  );
}

export const MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
