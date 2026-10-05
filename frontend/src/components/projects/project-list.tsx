"use client";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/common/page-header";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { ExportButtons } from "@/components/common/export-buttons";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { useProjects, type QueryOf } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/client";
import { PROJECT_STATUSES, PROJECT_TYPES } from "@/lib/enums";
import { can } from "@/lib/permissions";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";

type Sort = NonNullable<QueryOf<"list_projects">["sort"]>;
const SORTS: Sort[] = ["code", "-code", "name", "-name", "start_date", "-start_date"];
const PAGE_SIZE = 25;

export function ProjectList() {
  const t = useTranslations("project");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const { date } = useFormatters();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<Schemas["ProjectStatus"] | "">("");
  const [type, setType] = useState<Schemas["ProjectType"] | "">("");
  const [sort, setSort] = useState<Sort>("code");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);

  const query = useProjects({
    q: dq || undefined,
    status: status ? [status] : undefined,
    project_type: type || undefined,
    sort,
    page,
    page_size: PAGE_SIZE,
  });

  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          can(me, "project.manage") ? (
            <Button asChild>
              <Link href="/projects/new" data-testid="new-project">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar actions={can(me, "export.lists") ? <ExportButtons dataset="projects" params={{ q: dq, status }} /> : null}>
        <SearchFilter id="project-q" value={q} onChange={(v) => { setQ(v); setPage(1); }} />
        <SelectFilter
          id="project-status"
          label={t("fields.status")}
          value={status}
          onChange={(v) => { setStatus(v); setPage(1); }}
          options={PROJECT_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))}
        />
        <SelectFilter
          id="project-type"
          label={t("fields.project_type")}
          value={type}
          onChange={(v) => { setType(v); setPage(1); }}
          options={PROJECT_TYPES.map((s) => ({ value: s, label: t(`type.${s}`) }))}
        />
        <SelectFilter
          id="project-sort"
          label={tc("sortBy")}
          value={sort}
          onChange={(v) => setSort(v || "code")}
          options={SORTS.map((s) => ({ value: s, label: t(`sort.${s}`) }))}
          allLabel={t("sort.code")}
        />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : query.data && query.data.items.length > 0 ? (
        <>
          <Table data-testid="projects-table">
            <THead>
              <TR>
                <TH>{t("fields.code")}</TH>
                <TH>{t("fields.name")}</TH>
                <TH>{t("fields.project_type")}</TH>
                <TH>{t("fields.city")}</TH>
                <TH>{t("fields.start_date")}</TH>
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {query.data.items.map((p) => (
                <TR key={p.id} data-testid="project-row">
                  <TD>
                    <Link href={`/projects/${p.id}`} className="font-medium text-primary hover:underline ltr">
                      {p.code}
                    </Link>
                  </TD>
                  <TD>{name(p.name_en, p.name_ar)}</TD>
                  <TD>{t(`type.${p.project_type}`)}</TD>
                  <TD>{p.city}</TD>
                  <TD>{date(p.start_date)}</TD>
                  <TD>
                    <StatusBadge status={p.status} label={t(`status.${p.status}`)} />
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
