"use client";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { api, unwrap } from "@/lib/api/client";
import { useFormatters } from "@/lib/use-formatters";

const PAGE_SIZE = 25;
// Columns never shown even if an older copy still carries them (the server scrubs new ones).
const SENSITIVE = /(id_number|_enc$|_hash$|blind|token|secret|password|person_name|medical|notes$|date_of_birth|mobile|email|nationality|signature|gosi|employee_no|body_part|nature|illness|_reason$|conditions|licence|passport|iqama)/i;

function scrub(rows: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!rows) return null;
  const out: Record<string, unknown> = {};
  for (const [table, list] of Object.entries(rows)) {
    out[table] = Array.isArray(list) ? list.map((r) => Object.fromEntries(Object.entries(r as Record<string, unknown>).filter(([k]) => !SENSITIVE.test(k)))) : list;
  }
  return out;
}

/** D-271: what the administrator deleted, when, why, and copies of the removed rows. */
export function DeletedItemsPage() {
  const t = useTranslations("deletedItems");
  const { dateTime } = useFormatters();
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["deleted-records", page],
    queryFn: () => unwrap(api.GET("/api/v1/admin/deleted-records", { params: { query: { page, page_size: PAGE_SIZE } } })),
  });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const items = q.data.items;

  return (
    <div data-testid="deleted-items">
      <PageHeader title={t("title")} description={t("subtitle")} />
      {items.length === 0 ? (
        <EmptyState message={t("empty")} />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>{t("cols.when")}</TH>
                <TH>{t("cols.what")}</TH>
                <TH>{t("cols.by")}</TH>
                <TH>{t("cols.reason")}</TH>
                <TH>{t("cols.rows")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="deleted-row">
                  <TD label={t("cols.when")}>{dateTime(r.deleted_at)}</TD>
                  <TD label={t("cols.what")}>
                    <span className="ltr">{r.label}</span>
                  </TD>
                  <TD label={t("cols.by")}>{r.deleted_by_name ?? "—"}</TD>
                  <TD label={t("cols.reason")}>{r.reason}</TD>
                  <TD label={t("cols.rows")}>{r.rows_deleted}</TD>
                  <TD>
                    <Button size="sm" variant="outline" onClick={() => setOpenId(openId === r.id ? null : r.id)} aria-expanded={openId === r.id}>
                      {openId === r.id ? t("hide") : t("show")}
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {openId ? <Detail id={openId} /> : null}
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data.total} onPage={setPage} />
        </>
      )}
    </div>
  );
}

function Detail({ id }: { id: string }) {
  const t = useTranslations("deletedItems");
  const q = useQuery({
    queryKey: ["deleted-record", id],
    queryFn: () => unwrap(api.GET("/api/v1/admin/deleted-records/{record_id}", { params: { path: { record_id: id } } })),
  });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState rows={2} />;
  const d = q.data;
  return (
    <Card className="mt-4" data-testid="deleted-detail">
      <CardContent className="flex flex-col gap-3 pt-6 text-sm">
        <p className="font-medium">{t("byTable")}</p>
        <ul className="ms-4 list-disc">
          {Object.entries(d.row_counts).map(([table, n]) => (
            <li key={table} className="ltr">
              {table}: {n}
            </li>
          ))}
        </ul>
        <p className="font-medium">{t("copies")}</p>
        <pre className="ltr max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs">{JSON.stringify(scrub(d.rows), null, 2)}</pre>
      </CardContent>
    </Card>
  );
}
