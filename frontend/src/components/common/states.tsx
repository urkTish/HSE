"use client";
import { Inbox, SearchX } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useErrorMessage } from "@/lib/i18n-helpers";

export function LoadingState({ rows = 4 }: { rows?: number }) {
  const t = useTranslations("common");
  return (
    <div className="flex flex-col gap-2" aria-busy="true" aria-live="polite">
      <span className="sr-only">{t("loading")}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function NotFoundState() {
  const t = useTranslations("common");
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-xl border bg-surface p-10 text-center"
      data-testid="not-found"
    >
      <SearchX aria-hidden className="size-8 text-muted-foreground" />
      <h2 className="text-lg font-semibold">{t("notFoundTitle")}</h2>
      <p className="text-sm text-muted-foreground">{t("notFoundBody")}</p>
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const t = useTranslations("common");
  const msg = useErrorMessage();
  if (error instanceof ApiError && error.status === 404)
    return <NotFoundState />;
  return (
    <Alert tone="danger" data-testid="error-state">
      <p className="font-medium">{t("loadError")}</p>
      <p>{msg(error)}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
          {t("retry")}
        </Button>
      ) : null}
    </Alert>
  );
}

export function EmptyState({ message }: { message?: string }) {
  const t = useTranslations("common");
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-input/60 bg-surface p-8 text-center text-sm text-muted-foreground">
      <Inbox aria-hidden className="size-7" />
      <p>{message ?? t("noResults")}</p>
    </div>
  );
}

type MetaBlocker = { code: string; detail_en?: string | null; detail_ar?: string | null; ref?: string | null };

/** Blockers sent with a refused transition (422 with meta.blockers): strings (WAP) or BlockerItem objects (PTW). */
function metaBlockers(error: unknown): MetaBlocker[] {
  if (!(error instanceof ApiError)) return [];
  const raw = error.meta.blockers ?? error.meta.items;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((b): MetaBlocker | null => (typeof b === "string" ? { code: b } : b && typeof b === "object" && "code" in b ? (b as MetaBlocker) : null))
    .filter((b): b is MetaBlocker => b !== null);
}

/** Top-of-form error summary for a failed mutation. */
export function MutationError({ error }: { error: unknown }) {
  const msg = useErrorMessage();
  const ar = useLocale() === "ar";
  const te = useTranslations("enums");
  if (!error) return null;
  const blockers = metaBlockers(error);
  // 6c ERP_INCOMPLETE / evaluation: meta.missing lists what is still to be filled (codes or field paths).
  const missing = error instanceof ApiError && Array.isArray(error.meta.missing) ? (error.meta.missing as unknown[]).map(String) : [];
  return (
    <Alert tone="danger" data-testid="form-error" data-code={error instanceof ApiError ? error.code : undefined}>
      {msg(error)}
      {/* Dialogs have no per-field slots: list the API's field errors in the page language. */}
      {error instanceof ApiError &&
      error.code === "VALIDATION_ERROR" &&
      error.fieldErrors.length ? (
        <ul
          className="mt-1 list-inside list-disc text-xs"
          data-testid="form-field-errors"
        >
          {error.fieldErrors.map((f, i) => (
            <li key={i}>
              <bdi className="ltr font-mono">
                {String(f.loc[f.loc.length - 1] ?? "")}
              </bdi>
              : <bdi>{ar ? f.msg_ar || f.msg : f.msg}</bdi>
            </li>
          ))}
        </ul>
      ) : null}
      {blockers.length ? (
        <ul className="mt-1 list-inside list-disc text-sm" data-testid="error-blockers">
          {blockers.map((b, i) => {
            const key = `permitBlocker.${b.code}`;
            const label = te.has(key as "permitBlocker.JSA_MISSING") ? te(key as "permitBlocker.JSA_MISSING") : te.has(`wapBlocker.${b.code}` as "wapBlocker.NOTAM_NOT_ISSUED") ? te(`wapBlocker.${b.code}` as "wapBlocker.NOTAM_NOT_ISSUED") : b.code;
            const detail = ar ? b.detail_ar : b.detail_en;
            return (
              <li key={`${b.code}-${i}`} data-testid="error-blocker" data-code={b.code}>
                {label}
                {detail ? <span className="text-xs text-muted-foreground"> — {detail}</span> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
      {missing.length ? (
        <ul className="mt-1 list-inside list-disc text-xs" data-testid="error-missing">
          {missing.map((m) => (
            <li key={m}>
              <bdi className="ltr font-mono">{m}</bdi>
            </li>
          ))}
        </ul>
      ) : null}
    </Alert>
  );
}
