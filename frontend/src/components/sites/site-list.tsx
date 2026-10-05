"use client";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { ExportButtons } from "@/components/common/export-buttons";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { useProject, useSites } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/client";
import { SITE_SIDES, SITE_STATUSES } from "@/lib/enums";
import { can, canWrite } from "@/lib/permissions";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useDebounced } from "@/lib/use-debounced";

const PAGE_SIZE = 50;

export function SiteList({ projectId }: { projectId: string }) {
  const t = useTranslations("site");
  const me = useMeData();
  const name = useLocalizedName();
  const project = useProject(projectId);
  const [q, setQ] = useState("");
  const [side, setSide] = useState<Schemas["SiteSide"] | "">("");
  const [status, setStatus] = useState<Schemas["SiteStatus"] | "">("");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const query = useSites(projectId, { q: dq || undefined, site_side: side || undefined, status: status || undefined, page, page_size: PAGE_SIZE, sort: "code" });
  const manage = canWrite(me, "site_zone.manage", projectId) && project.data?.status !== "closed";

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{t("title")}</h2>
        {manage ? (
          <Button asChild>
            <Link href={`/projects/${projectId}/sites/new`} data-testid="new-site">
              <Plus aria-hidden />
              {t("new")}
            </Link>
          </Button>
        ) : null}
      </div>
      <ListToolbar actions={can(me, "export.lists", projectId) ? <ExportButtons dataset="sites" params={{ project_id: projectId, q: dq, status }} /> : null}>
        <SearchFilter id="site-q" value={q} onChange={(v) => { setQ(v); setPage(1); }} />
        <SelectFilter id="site-side" label={t("fields.site_side")} value={side} onChange={(v) => { setSide(v); setPage(1); }} options={SITE_SIDES.map((s) => ({ value: s, label: t(`side.${s}`) }))} />
        <SelectFilter id="site-status" label={t("fields.status")} value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={SITE_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : query.data && query.data.items.length > 0 ? (
        <>
          <Table data-testid="sites-table">
            <THead>
              <TR>
                <TH>{t("fields.code")}</TH>
                <TH>{t("fields.name")}</TH>
                <TH>{t("fields.site_side")}</TH>
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {query.data.items.map((s) => (
                <TR key={s.id} data-testid="site-row">
                  <TD>
                    <Link href={`/projects/${projectId}/sites/${s.id}`} className="font-medium text-primary hover:underline ltr">
                      {s.code}
                    </Link>
                  </TD>
                  <TD>{name(s.name_en, s.name_ar)}</TD>
                  <TD>{t(`side.${s.site_side}`)}</TD>
                  <TD>
                    <StatusBadge status={s.status} label={t(`status.${s.status}`)} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPage={setPage} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}
