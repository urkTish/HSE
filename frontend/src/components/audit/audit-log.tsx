"use client";
import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { Fragment, useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/common/page-header";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { ExportButtons } from "@/components/common/export-buttons";
import { ChangeDiff } from "@/components/common/history-panel";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAuditLog } from "@/lib/api/queries";
import { AUDIT_ACTIONS, AUDIT_RESULTS, ENTITY_TYPES } from "@/lib/enums";
import { useCurrentProject } from "@/lib/current-project";
import { riyadhDayBoundary } from "@/lib/datetime";
import { joinList } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";

const PAGE_SIZE = 50;

export function AuditLog() {
  const t = useTranslations("audit");
  const tr = useTranslations("role");
  const me = useMeData();
  const { dateTime } = useFormatters();
  const { projects } = useCurrentProject();
  const projectCode = new Map(projects.map((p) => [p.id, p.code]));
  const s = useSearchState();
  const projectId = s.get("project_id") ?? "";
  const action = (s.get("action") as Schemas["AuditAction-Output"] | null) ?? "";
  const entity = (s.get("entity_type") as Schemas["EntityType"] | null) ?? "";
  const result = (s.get("result") as Schemas["AuditResult"] | null) ?? "";
  const from = s.get("from") ?? "";
  const to = s.get("to") ?? "";
  const page = s.getInt("page", 1) ?? 1;
  const [open, setOpen] = useState<string | null>(null);
  const [verify, setVerify] = useState<Schemas["AuditChainVerification"] | null>(null);
  const [verifyError, setVerifyError] = useState<unknown>(null);
  const [verifying, setVerifying] = useState(false);
  const query = useAuditLog({
    project_id: projectId || undefined,
    action: action ? [action] : undefined,
    entity_type: entity || undefined,
    result: result || undefined,
    occurred_from: from ? riyadhDayBoundary(from, false) : undefined,
    occurred_to: to ? riyadhDayBoundary(to, true) : undefined,
    page,
    page_size: PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  const showIp = items.some((e) => e.ip_address);

  async function runVerify() {
    setVerifying(true);
    setVerifyError(null);
    try {
      setVerify(await unwrap(api.POST("/api/v1/audit-log/verify")));
    } catch (e) {
      setVerifyError(e);
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          me.is_hse_manager ? (
            <Button variant="outline" onClick={runVerify} disabled={verifying} data-testid="verify-chain">
              <ShieldCheck aria-hidden />
              {verifying ? t("verifying") : t("verify")}
            </Button>
          ) : null
        }
      />
      {verify ? (
        <Alert tone={verify.ok ? "success" : "danger"} className="mb-4" data-testid="verify-result">
          {verify.ok ? t("verifyOk", { count: verify.checked_count }) : t("verifyBroken", { seq: verify.first_break_seq ?? 0 })}
        </Alert>
      ) : null}
      <MutationError error={verifyError} />
      <ListToolbar actions={<ExportButtons dataset="audit_log" params={{ project_id: projectId }} />}>
        <SelectFilter id="audit-project" label={t("filters.project")} value={projectId} onChange={(v) => s.set({ project_id: v })} options={projects.map((p) => ({ value: p.id, label: p.code }))} allLabel={t("filters.anyProject")} />
        <SelectFilter id="audit-action" label={t("filters.action")} value={action} onChange={(v) => s.set({ action: v })} options={AUDIT_ACTIONS.map((a) => ({ value: a, label: t(`action.${a}`) }))} allLabel={t("filters.anyAction")} />
        <SelectFilter id="audit-entity" label={t("filters.entityType")} value={entity} onChange={(v) => s.set({ entity_type: v })} options={ENTITY_TYPES.map((a) => ({ value: a, label: t(`entity.${a}`) }))} allLabel={t("filters.anyEntity")} />
        <SelectFilter id="audit-result" label={t("filters.result")} value={result} onChange={(v) => s.set({ result: v })} options={AUDIT_RESULTS.map((a) => ({ value: a, label: t(`result.${a}`) }))} allLabel={t("filters.anyResult")} />
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="audit-from">{t("filters.from")}</Label>
          <Input id="audit-from" type="date" value={from} onChange={(e) => s.set({ from: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="audit-to">{t("filters.to")}</Label>
          <Input id="audit-to" type="date" value={to} onChange={(e) => s.set({ to: e.target.value })} />
        </div>
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <Table data-testid="audit-table">
            <THead>
              <TR>
                <TH>{t("columns.occurredAt")}</TH>
                <TH>{t("columns.actor")}</TH>
                <TH>{t("columns.action")}</TH>
                <TH>{t("columns.entity")}</TH>
                <TH>{t("columns.project")}</TH>
                <TH>{t("columns.result")}</TH>
                {showIp ? <TH data-testid="ip-column">{t("columns.ip")}</TH> : null}
                <TH>
                  <span className="sr-only">{t("detail.details")}</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {items.map((e) => (
                <Fragment key={e.id}>
                  <TR data-testid="audit-row" data-action={e.action}>
                    <TD label={t("columns.occurredAt")} className="md:whitespace-nowrap">
                      <time dateTime={e.occurred_at} data-testid="audit-time">
                        {dateTime(e.occurred_at)}
                      </time>
                    </TD>
                    <TD label={t("columns.actor")}>
                      {e.actor_name ?? t("system")}
                      {e.actor_role ? <span className="block text-xs text-muted-foreground">{tr(e.actor_role)}</span> : null}
                    </TD>
                    <TD label={t("columns.action")}>{t(`action.${e.action}`)}</TD>
                    <TD label={t("columns.entity")}>{e.entity_type ? t(`entity.${e.entity_type}`) : "—"}</TD>
                    <TD label={t("columns.project")} data-testid="audit-project"><span className="ltr">{e.project_id ? (projectCode.get(e.project_id) ?? "…") : "—"}</span></TD>
                    <TD label={t("columns.result")}>
                      <StatusBadge status={e.result} label={t(`result.${e.result}`)} />
                    </TD>
                    {showIp ? <TD label={t("columns.ip")}><span className="ltr">{e.ip_address ?? "—"}</span></TD> : null}
                    <TD>
                      <Button variant="ghost" size="sm" aria-expanded={open === e.id} onClick={() => setOpen(open === e.id ? null : e.id)}>
                        {open === e.id ? t("detail.hideDetails") : t("detail.showDetails")}
                      </Button>
                    </TD>
                  </TR>
                  {open === e.id ? (
                    <TR>
                      <TD colSpan={showIp ? 8 : 7} className="bg-muted/30">
                        <dl className="grid gap-2 text-xs sm:grid-cols-2">
                          <div>
                            <dt className="text-muted-foreground">{t("detail.seq")}</dt>
                            <dd className="ltr">{e.seq}</dd>
                          </div>
                          {e.request_id ? (
                            <div>
                              <dt className="text-muted-foreground">{t("detail.requestId")}</dt>
                              <dd className="ltr font-mono">{e.request_id}</dd>
                            </div>
                          ) : null}
                          {e.user_agent ? (
                            <div className="sm:col-span-2">
                              <dt className="text-muted-foreground">{t("detail.userAgent")}</dt>
                              <dd className="ltr break-all">{e.user_agent}</dd>
                            </div>
                          ) : null}
                          {e.fields_read?.length ? (
                            <div>
                              <dt className="text-muted-foreground">{t("detail.fieldsRead")}</dt>
                              <dd className="ltr">{joinList(e.fields_read)}</dd>
                            </div>
                          ) : null}
                          {e.details ? (
                            <div className="sm:col-span-2">
                              <dt className="text-muted-foreground">{t("detail.details")}</dt>
                              <dd className="ltr font-mono break-all">{JSON.stringify(e.details)}</dd>
                            </div>
                          ) : null}
                          {e.hash ? (
                            <div className="sm:col-span-2">
                              <dt className="text-muted-foreground">{t("detail.hash")}</dt>
                              <dd className="ltr font-mono break-all">{e.hash}</dd>
                            </div>
                          ) : null}
                        </dl>
                        {e.before || e.after ? (
                          <ChangeDiff before={(e.before as Record<string, unknown> | null) ?? null} after={(e.after as Record<string, unknown> | null) ?? null} />
                        ) : null}
                      </TD>
                    </TR>
                  ) : null}
                </Fragment>
              ))}
            </TBody>
          </Table>
          {query.data ? <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPage={(p) => s.set({ page: p })} /> : null}
        </>
      )}
    </div>
  );
}
