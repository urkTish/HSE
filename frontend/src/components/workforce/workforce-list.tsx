"use client";
import { CalendarClock, FileUp, Plus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ExportButtons } from "@/components/common/export-buttons";
import { LinkFilterNote } from "@/components/common/link-filter-note";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { useWorkforceReturns } from "@/lib/api/hse";
import { useDisplay } from "@/lib/digits";
import { SHIFTS, WORKFORCE_STATUSES } from "@/lib/enums";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";

const PAGE_SIZE = 50;

export function WorkforceList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("workforce");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const msg = useErrorMessage();
  const show = useDisplay(project.id);
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["WorkforceStatus"][];
  const sites = s.getAll("site_id");
  const engs = s.getAll("engagement_id");
  const shift = (s.get("shift") ?? "") as Schemas["Shift"] | "";
  const batch = s.get("import_batch_id");
  const q = {
    date_from: s.get("date_from") || null,
    date_to: s.get("date_to") || null,
    site_id: sites.length ? sites : null,
    engagement_id: engs.length ? engs : null,
    include_subcontractors: s.getBool("include_subcontractors") ?? true,
    status: status.length ? status : null,
    shift: shift || null,
    source: (s.get("source") as Schemas["WorkforceSource"] | null) || null,
    import_batch_id: batch,
    has_warnings: s.getBool("has_warnings") ?? null,
    sort: "-work_date" as const,
    page,
    page_size: PAGE_SIZE,
  };
  const query = useWorkforceReturns(project.id, q);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const canVerify = canWrite(me, "workforce.verify", project.id);
  const items = query.data?.items ?? [];
  const verifiable = items.filter((r) => r.status === "submitted").map((r) => r.id);

  async function bulkVerify() {
    setBusy(true);
    try {
      const res = await unwrap(api.POST("/api/v1/projects/{project_id}/workforce-returns/verify", { params: { path: { project_id: project.id } }, body: { ids: selected } }));
      toast.success(t("verifyResult", { ok: res.verified.length, failed: res.failed.length }));
      for (const f of res.failed) toast.error(msg(new ApiError(409, { code: f.code as Schemas["ErrorCode"], message: f.message, message_ar: f.message_ar })));
      setSelected([]);
      await qc.invalidateQueries({ queryKey: ["workforce-returns"] });
    } catch (e) {
      toast.error(msg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <>
            {canWrite(me, "workforce.edit", project.id) ? (
              <Button asChild>
                <Link href="/workforce/new" data-testid="new-return">
                  <Plus aria-hidden />
                  {t("new")}
                </Link>
              </Button>
            ) : null}
            {canWrite(me, "workforce.import", project.id) ? (
              <Button variant="outline" asChild>
                <Link href="/workforce/import" data-testid="open-import">
                  <FileUp aria-hidden />
                  {t("import")}
                </Link>
              </Button>
            ) : null}
            <Button variant="outline" asChild>
              <Link href="/workforce/months" data-testid="open-months">
                <CalendarClock aria-hidden />
                {t("months")}
              </Link>
            </Button>
          </>
        }
      />
      <LinkFilterNote keys={["import_batch_id", "has_warnings", "source"]} />
      <ListToolbar
        actions={
          <>
            {canVerify && selected.length > 0 ? (
              <Button size="sm" onClick={() => void bulkVerify()} disabled={busy} data-testid="bulk-verify">
                {t("verifySelected")} ({show(selected.length)})
              </Button>
            ) : null}
            {can(me, "export.lists", project.id) || can(me, "export.kpis", project.id) ? (
              <ExportButtons dataset="workforce_returns" params={{ project_id: project.id, status: status.join(",") || null }} />
            ) : null}
          </>
        }
      >
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="wf-from">{tc("dateFrom")}</Label>
          <Input id="wf-from" type="date" value={q.date_from ?? ""} onChange={(e) => s.set({ date_from: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="wf-to">{tc("dateTo")}</Label>
          <Input id="wf-to" type="date" value={q.date_to ?? ""} onChange={(e) => s.set({ date_to: e.target.value })} />
        </div>
        <MultiSelect id="wf-site" label={tc("site")} options={opts.sites} value={sites} onChange={(v) => s.set({ site_id: v })} />
        <MultiSelect id="wf-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <SelectFilter id="wf-shift" label={t("fields.shift")} value={shift} onChange={(v) => s.set({ shift: v })} options={SHIFTS.map((x) => ({ value: x, label: te(`shift.${x}`) }))} />
        <MultiSelect
          id="wf-status"
          label={t("fields.status")}
          options={WORKFORCE_STATUSES.map((x) => ({ value: x, label: te(`workforceStatus.${x}`) }))}
          value={status}
          onChange={(v) => s.set({ status: v })}
          testId="wf-status-filter"
        />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length > 0 ? (
        <>
          <Table data-testid="returns-table">
            <THead>
              <TR>
                {canVerify ? (
                  <TH className="w-10">
                    <Checkbox
                      aria-label={tc("selectAll")}
                      checked={verifiable.length > 0 && verifiable.every((id) => selected.includes(id))}
                      onChange={(e) => setSelected(e.target.checked ? verifiable : [])}
                    />
                  </TH>
                ) : null}
                <TH>{t("fields.work_date")}</TH>
                <TH>{t("fields.site")}</TH>
                <TH>{t("fields.zone")}</TH>
                <TH>{t("fields.engagement")}</TH>
                <TH>{t("fields.shift")}</TH>
                <TH className="text-end">{t("fields.headcount")}</TH>
                <TH className="text-end">{t("fields.man_hours")}</TH>
                <TH>{t("fields.source")}</TH>
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="return-row">
                  {canVerify ? (
                    <TD label={tc("select")}>
                      {r.status === "submitted" ? (
                        <Checkbox
                          aria-label={`${tc("select")} ${r.work_date} ${r.engagement.short_code}`}
                          checked={selected.includes(r.id)}
                          onChange={(e) => setSelected(e.target.checked ? [...selected, r.id] : selected.filter((x) => x !== r.id))}
                        />
                      ) : null}
                    </TD>
                  ) : null}
                  <TD label={t("fields.work_date")}>
                    <Link href={`/workforce/${r.id}`} className="font-medium text-primary hover:underline">
                      {date(r.work_date)}
                    </Link>
                  </TD>
                  <TD label={t("fields.site")}>
                    <span className="ltr">{r.site.code}</span>
                  </TD>
                  <TD label={t("fields.zone")}>{r.zone ? <span className="ltr">{r.zone.code}</span> : "—"}</TD>
                  <TD label={t("fields.engagement")}>
                    <span className="ltr">{r.engagement.short_code}</span>
                  </TD>
                  <TD label={t("fields.shift")}>{te(`shift.${r.shift}`)}</TD>
                  <TD label={t("fields.headcount")} className="text-end tabular-nums">
                    {show(r.headcount)}
                  </TD>
                  <TD label={t("fields.man_hours")} className="text-end tabular-nums">
                    {show(r.man_hours)}
                  </TD>
                  <TD label={t("fields.source")}>{te(`workforceSource.${r.source}`)}</TD>
                  <TD label={t("fields.status")}>
                    <span className="inline-flex flex-wrap items-center gap-1">
                      <StatusBadge status={r.status} label={te(`workforceStatus.${r.status}`)} />
                      {(r.warnings?.length ?? 0) > 0 ? <StatusBadge status="warning" label={t("hasWarnings")} /> : null}
                    </span>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}
