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
import { useContractors, type QueryOf } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/client";
import { CONTRACTOR_CATEGORIES, CONTRACTOR_STATUSES } from "@/lib/enums";
import { useCurrentProject } from "@/lib/current-project";
import { can } from "@/lib/permissions";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";

type Sort = NonNullable<QueryOf<"list_contractors">["sort"]>;
const SORTS: Sort[] = ["short_code", "-short_code", "name", "-name", "cr_expiry_date"];
const PAGE_SIZE = 25;

export function ContractorList() {
  const t = useTranslations("contractor");
  const tc = useTranslations("common");
  const ts = useTranslations("shell");
  const me = useMeData();
  const name = useLocalizedName();
  const { date } = useFormatters();
  const { projects } = useCurrentProject();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<Schemas["ContractorStatus"] | "">("");
  const [category, setCategory] = useState<Schemas["ContractorCategory"] | "">("");
  const [projectId, setProjectId] = useState("");
  const [sort, setSort] = useState<Sort>("short_code");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const query = useContractors({
    q: dq || undefined,
    status: status ? [status] : undefined,
    category: category || undefined,
    project_id: projectId || undefined,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  const showContact = items.some((c) => c.primary_contact_name || c.primary_contact_email);
  const reset = () => setPage(1);

  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          can(me, "contractor.create") ? (
            <Button asChild>
              <Link href="/contractors/new" data-testid="new-contractor">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar actions={can(me, "export.lists") ? <ExportButtons dataset="contractors" params={{ q: dq, status, project_id: projectId }} /> : null}>
        <SearchFilter id="contractor-q" value={q} onChange={(v) => { setQ(v); reset(); }} placeholder={t("searchHint")} />
        <SelectFilter id="contractor-status" label={t("fields.status")} value={status} onChange={(v) => { setStatus(v); reset(); }} options={CONTRACTOR_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))} />
        <SelectFilter id="contractor-category" label={t("fields.contractor_category")} value={category} onChange={(v) => { setCategory(v); reset(); }} options={CONTRACTOR_CATEGORIES.map((s) => ({ value: s, label: t(`category.${s}`) }))} />
        <SelectFilter id="contractor-project" label={ts("projectSwitcher")} value={projectId} onChange={(v) => { setProjectId(v); reset(); }} options={projects.map((p) => ({ value: p.id, label: p.code }))} allLabel={t("anyProject")} />
        <SelectFilter id="contractor-sort" label={tc("sortBy")} value={sort} onChange={(v) => setSort(v || "short_code")} options={SORTS.map((s) => ({ value: s, label: t(`sort.${s}`) }))} allLabel={t("sort.short_code")} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length > 0 && query.data ? (
        <>
          <Table data-testid="contractors-table">
            <THead>
              <TR>
                <TH>{t("fields.short_code")}</TH>
                <TH>{t("fields.legal_name")}</TH>
                <TH>{t("fields.cr_number")}</TH>
                <TH>{t("fields.contractor_category")}</TH>
                <TH>{t("fields.cr_expiry_date")}</TH>
                {showContact ? <TH>{t("contact")}</TH> : null}
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="contractor-row" data-code={c.short_code}>
                  <TD>
                    <Link href={`/contractors/${c.id}`} className="font-medium text-primary hover:underline ltr">
                      {c.short_code}
                    </Link>
                  </TD>
                  <TD>{name(c.legal_name_en, c.legal_name_ar)}</TD>
                  <TD className="ltr">{c.cr_number}</TD>
                  <TD>{t(`category.${c.contractor_category}`)}</TD>
                  <TD>{date(c.cr_expiry_date)}</TD>
                  {showContact ? (
                    <TD data-testid="contractor-contact">
                      {c.primary_contact_name ?? "—"}
                      {c.primary_contact_email ? <span className="block text-xs text-muted-foreground ltr">{c.primary_contact_email}</span> : null}
                    </TD>
                  ) : null}
                  <TD>
                    <StatusBadge status={c.status} label={t(`status.${c.status}`)} />
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
