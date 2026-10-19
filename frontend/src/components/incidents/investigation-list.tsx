"use client";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useIncidents } from "@/lib/api/hse";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";
import { todayInZone } from "@/lib/datetime";
import { useSearchState } from "@/lib/url-state";

const PAGE_SIZE = 50;

// D-269: an investigation report is pending from the moment the incident is registered, waits for
// the HSE Manager once submitted, and counts as approved after the manager's approval.
const BUCKETS = {
  pending: ["reported", "under_investigation"],
  approval: ["pending_review"],
  approved: ["actions_pending", "closed"],
} as const satisfies Record<string, readonly Schemas["IncidentStatus"][]>;
type Bucket = keyof typeof BUCKETS;

function bucketOf(s: Schemas["IncidentStatus"]): Bucket | null {
  for (const [k, v] of Object.entries(BUCKETS) as [Bucket, readonly Schemas["IncidentStatus"][]][]) if (v.includes(s)) return k;
  return null;
}

export function InvestigationList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("investigations");
  const te = useTranslations("enums");
  const name = useLocalizedName();
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const bucket = ((s.get("bucket") as Bucket | null) ?? "pending") satisfies Bucket;
  const page = s.getInt("page", 1) ?? 1;
  const query = useIncidents(project.id, { status: [...BUCKETS[bucket]], sort: "-occurred_at", page, page_size: PAGE_SIZE });
  const items = query.data?.items ?? [];

  return (
    <div data-testid="investigations">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label={t("title")}>
        {(Object.keys(BUCKETS) as Bucket[]).map((b) => (
          <Button
            key={b}
            role="tab"
            aria-selected={bucket === b}
            size="sm"
            variant={bucket === b ? "default" : "outline"}
            onClick={() => s.set({ bucket: b, page: null })}
            data-testid={`bucket-${b}`}
          >
            {t(`bucket.${b}`)}
          </Button>
        ))}
      </div>
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : query.isLoading ? (
        <LoadingState />
      ) : items.length === 0 ? (
        <EmptyState message={t(`empty.${bucket}`)} />
      ) : (
        <>
          <Table data-testid="investigations-table">
            <THead>
              <TR>
                <TH>{t("cols.ref")}</TH>
                <TH>{t("cols.occurred")}</TH>
                <TH>{t("cols.title")}</TH>
                <TH>{t("cols.contractor")}</TH>
                <TH>{t("cols.level")}</TH>
                <TH>{t("cols.due")}</TH>
                <TH>{t("cols.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((r) => {
                const b = bucketOf(r.status);
                const overdue = b === "pending" && r.investigation_due_date !== null && r.investigation_due_date < todayInZone();
                return (
                  <TR key={r.id} data-testid="investigation-row">
                    <TD label={t("cols.ref")}>
                      <Link href={r.status === "reported" ? `/incidents/${r.id}` : `/incidents/${r.id}/investigation`} className="ltr text-primary hover:underline">
                        {r.ref}
                      </Link>
                    </TD>
                    <TD label={t("cols.occurred")}>{date(r.occurred_at)}</TD>
                    <TD label={t("cols.title")}>{r.title}</TD>
                    <TD label={t("cols.contractor")}>{r.responsible_engagement ? name(r.responsible_engagement.name_en, r.responsible_engagement.name_ar) : "—"}</TD>
                    <TD label={t("cols.level")}>{r.investigation_level ? te(`investigationLevel.${r.investigation_level}`) : "—"}</TD>
                    <TD label={t("cols.due")}>
                      <span className="inline-flex flex-wrap items-center gap-1">
                        {date(r.investigation_due_date)}
                        {overdue ? <StatusBadge status="overdue" label={t("overdue")} /> : null}
                      </span>
                    </TD>
                    <TD label={t("cols.status")}>
                      <StatusBadge status={r.status === "reported" ? "pending" : r.status} label={r.status === "reported" ? t("notStarted") : te(`incidentStatus.${r.status}`)} />
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      )}
    </div>
  );
}
