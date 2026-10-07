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

/** Top-of-form error summary for a failed mutation. */
export function MutationError({ error }: { error: unknown }) {
  const msg = useErrorMessage();
  const ar = useLocale() === "ar";
  if (!error) return null;
  return (
    <Alert tone="danger" data-testid="form-error">
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
    </Alert>
  );
}
