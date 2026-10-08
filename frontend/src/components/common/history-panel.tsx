"use client";
import { History, Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Pagination } from "@/components/common/pagination";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useHistory } from "@/lib/api/queries";
import { ApiError, type Schemas } from "@/lib/api/client";
import { useFormatters } from "@/lib/use-formatters";

function show(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function ChangeDiff({ before, after }: { before: Record<string, unknown> | null; after: Record<string, unknown> | null }) {
  const t = useTranslations("history");
  const fields = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  if (fields.length === 0) return <p className="text-xs text-muted-foreground">{t("noFieldChanges")}</p>;
  return (
    <table className="mt-2 w-full text-xs">
      <thead>
        <tr className="text-muted-foreground">
          <th className="py-1 text-start font-medium">{t("field")}</th>
          <th className="py-1 text-start font-medium">{t("before")}</th>
          <th className="py-1 text-start font-medium">{t("after")}</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((f) => (
          <tr key={f} className="border-t align-top">
            <td className="py-1 pe-2 font-mono ltr">{f}</td>
            <td className="py-1 pe-2 break-all ltr">{show(before?.[f])}</td>
            <td className="py-1 break-all ltr">{show(after?.[f])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Who changed what and when on a record the user can see (capability 17). */
export function HistoryPanel({
  entityType,
  entityId,
  projectId,
}: {
  entityType: Schemas["EntityType"];
  entityId: string;
  projectId?: string | null;
}) {
  const t = useTranslations("history");
  const td = useTranslations("certDesign");
  const ta = useTranslations("audit.action");
  const { dateTime } = useFormatters(projectId);
  const [page, setPage] = useState(1);
  const q = useHistory(entityType, entityId, page);
  const items = q.data?.items ?? [];

  return (
    <Card data-testid="history-panel">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History aria-hidden className="size-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {q.isLoading ? (
          <LoadingState rows={2} />
        ) : q.isError && q.error instanceof ApiError && q.error.status === 404 ? (
          // The record itself is on screen, so a 404 here means no history is kept for this record type yet:
          // a calm grey "not available yet" note, not a full-size "Not found" error under a record that exists.
          <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="history-unavailable">
            <Info aria-hidden className="size-4 shrink-0" />
            {td("historyUnavailable")}
          </p>
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ol className="flex flex-col gap-4">
            {items.map((e) => (
              <li key={e.id} className="border-s-2 border-border ps-3" data-testid="history-entry">
                <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className="font-medium">{ta(e.action)}</span>
                  <span className="text-muted-foreground">{t("by", { name: e.actor_name ?? t("system") })}</span>
                  <time className="text-xs text-muted-foreground" dateTime={e.occurred_at}>
                    {dateTime(e.occurred_at)}
                  </time>
                </div>
                <ChangeDiff
                  before={(e.before as Record<string, unknown> | null) ?? null}
                  after={(e.after as Record<string, unknown> | null) ?? null}
                />
              </li>
            ))}
          </ol>
        )}
        {q.data && q.data.total > q.data.page_size ? (
          <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onPage={setPage} />
        ) : null}
      </CardContent>
    </Card>
  );
}
