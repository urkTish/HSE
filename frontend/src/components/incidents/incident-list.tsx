"use client";
import { Plus, ShieldOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ExportButtons } from "@/components/common/export-buttons";
import { LinkFilterNote } from "@/components/common/link-filter-note";
import { ListToolbar, SearchFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useExcludedCases, useIncidents } from "@/lib/api/hse";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { useDisplay } from "@/lib/digits";
import { CASE_CATEGORIES, INCIDENT_STATUSES, INCIDENT_TYPES } from "@/lib/enums";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";

const PAGE_SIZE = 50;

export function IncidentList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("incidents");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["IncidentStatus"][];
  const types = s.getAll("incident_type") as Schemas["IncidentType"][];
  const cats = s.getAll("case_category") as Schemas["CaseCategory"][];
  const sites = s.getAll("site_id");
  const zones = s.getAll("zone_id");
  const engs = s.getAll("engagement_id");
  const q = {
    status: status.length ? status : null,
    incident_type: types.length ? types : null,
    case_category: cats.length ? cats : null,
    classification_status: (s.get("classification_status") as Schemas["ClassificationStatus"] | null) || null,
    site_id: sites.length ? sites : null,
    zone_id: zones.length ? zones : null,
    engagement_id: engs.length ? engs : null,
    include_subcontractors: s.getBool("include_subcontractors") ?? true,
    activity: (s.get("activity") as Schemas["Activity"] | null) || null,
    mechanism: (s.get("mechanism") as Schemas["Mechanism"] | null) || null,
    airside_flag: (s.get("airside_flag") as Schemas["AirsideFlag"] | null) || null,
    hipo: s.getBool("hipo") ?? null,
    late_report: s.getBool("late_report") ?? null,
    investigation_level: (s.get("investigation_level") as Schemas["InvestigationLevel"] | null) || null,
    investigation_overdue: s.getBool("investigation_overdue") ?? null,
    unclassified_over_hours: s.getInt("unclassified_over_hours", 0) || null,
    notification_due: s.getBool("notification_due") ?? null,
    open_lti: s.getBool("open_lti") ?? null,
    date_from: s.get("date_from") || null,
    date_to: s.get("date_to") || null,
    q: s.get("q") || null,
    sort: "-occurred_at" as const,
    page,
    page_size: PAGE_SIZE,
  };
  const query = useIncidents(project.id, q);
  const items = query.data?.items ?? [];

  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <>
            {canWrite(me, "incident.report", project.id) ? (
              <Button asChild>
                <Link href="/incidents/new" data-testid="new-incident">
                  <Plus aria-hidden />
                  {t("new")}
                </Link>
              </Button>
            ) : null}
            <Button variant="outline" asChild>
              <Link href="/incidents/excluded" data-testid="open-excluded">
                <ShieldOff aria-hidden />
                {t("excluded")}
              </Link>
            </Button>
          </>
        }
      />
      <LinkFilterNote
        keys={["unclassified_over_hours", "notification_due", "open_lti", "investigation_overdue", "classification_status", "activity", "mechanism", "airside_flag", "investigation_level", "zone_id", "late_report"]}
      />
      <ListToolbar
        actions={
          can(me, "export.lists", project.id) ? (
            <ExportButtons dataset="incidents" params={{ project_id: project.id, status: status.join(",") || null }} />
          ) : null
        }
      >
        <SearchFilter id="inc-q" placeholder={t("filters.search")} value={q.q ?? ""} onChange={(v) => s.set({ q: v })} />
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="inc-from">{tc("dateFrom")}</Label>
          <Input id="inc-from" type="date" value={q.date_from ?? ""} onChange={(e) => s.set({ date_from: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="inc-to">{tc("dateTo")}</Label>
          <Input id="inc-to" type="date" value={q.date_to ?? ""} onChange={(e) => s.set({ date_to: e.target.value })} />
        </div>
        <MultiSelect id="inc-site" label={tc("site")} options={opts.sites} value={sites} onChange={(v) => s.set({ site_id: v })} />
        <MultiSelect id="inc-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <MultiSelect
          id="inc-type"
          label={t("filters.type")}
          options={INCIDENT_TYPES.map((x) => ({ value: x, label: te(`incidentType.${x}`) }))}
          value={types}
          onChange={(v) => s.set({ incident_type: v })}
          testId="inc-type-filter"
        />
        <MultiSelect
          id="inc-cat"
          label={t("filters.category")}
          options={CASE_CATEGORIES.map((x) => ({ value: x, label: te(`caseCategory.${x}`) }))}
          value={cats}
          onChange={(v) => s.set({ case_category: v })}
        />
        <MultiSelect
          id="inc-status"
          label={t("fields.status")}
          options={INCIDENT_STATUSES.map((x) => ({ value: x, label: te(`incidentStatus.${x}`) }))}
          value={status}
          onChange={(v) => s.set({ status: v })}
          testId="inc-status-filter"
        />
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <Checkbox checked={q.hipo === true} onChange={(e) => s.set({ hipo: e.target.checked ? "true" : null })} data-testid="hipo-filter" />
          {t("filters.hipoOnly")}
        </label>
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length > 0 ? (
        <>
          <Table data-testid="incidents-table">
            <THead>
              <TR>
                <TH>{t("list.ref")}</TH>
                <TH>{t("list.occurred")}</TH>
                <TH>{t("list.type")}</TH>
                <TH>{t("list.title")}</TH>
                <TH>{t("list.site")}</TH>
                <TH>{t("list.contractor")}</TH>
                <TH>{t("list.severity")}</TH>
                <TH>{t("list.cases")}</TH>
                <TH>{t("list.investigation")}</TH>
                <TH>{t("list.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="incident-row" data-ref={r.ref}>
                  <TD label={t("list.ref")}>
                    <Link href={`/incidents/${r.id}`} className="ltr font-medium text-primary hover:underline">
                      {r.ref}
                    </Link>
                  </TD>
                  <TD label={t("list.occurred")}>{dateTime(r.occurred_at)}</TD>
                  <TD label={t("list.type")}>
                    <span className="inline-flex flex-wrap gap-1">
                      {r.incident_types.map((x) => (
                        <span key={x} className={x === r.primary_type ? "font-medium" : "text-muted-foreground"}>
                          {te(`incidentType.${x}`)}
                        </span>
                      ))}
                    </span>
                  </TD>
                  <TD label={t("list.title")}>{r.title}</TD>
                  <TD label={t("list.site")}>
                    <span className="ltr">
                      {r.site.code}
                      {r.zone ? ` / ${r.zone.code}` : ""}
                    </span>
                  </TD>
                  <TD label={t("list.contractor")}>{r.responsible_engagement ? <span className="ltr">{r.responsible_engagement.short_code}</span> : "—"}</TD>
                  <TD label={t("list.severity")}>
                    <span className="inline-flex items-center gap-1">
                      <span className="tabular-nums">
                        {show(r.actual_severity)}/{show(r.potential_severity)}
                      </span>
                      {r.hipo ? <StatusBadge status="warning" label={t("hipo")} /> : null}
                    </span>
                  </TD>
                  <TD label={t("list.cases")}>
                    {r.case_count > 0 ? (
                      <span className="inline-flex flex-wrap gap-1 text-xs">
                        {r.case_categories.map((c, i) => (
                          <span key={`${c}-${i}`} className="rounded bg-muted px-1.5 py-0.5 ltr">
                            {c}
                          </span>
                        ))}
                        {r.provisional_cases > 0 ? <span className="text-warning">{te("classificationStatus.provisional")} {show(r.provisional_cases)}</span> : null}
                        {r.excluded_cases > 0 ? <span className="text-muted-foreground">{t("excludedFromRates")} {show(r.excluded_cases)}</span> : null}
                      </span>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD label={t("list.investigation")}>
                    {r.investigation_level ? (
                      <span className="text-xs">
                        <span className="ltr">{r.investigation_level}</span>
                        {r.investigation_due_date ? ` · ${r.investigation_due_date}` : ""}
                      </span>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD label={t("list.status")}>
                    <span className="inline-flex flex-wrap items-center gap-1">
                      <StatusBadge status={r.status} label={te(`incidentStatus.${r.status}`)} />
                      {r.late_report ? <StatusBadge status="late" label={t("late")} /> : null}
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

export function ExcludedCases({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("incidents");
  const tcs = useTranslations("cases");
  const te = useTranslations("enums");
  const tn = useTranslations("nav");
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const q = { date_from: s.get("date_from") || null, date_to: s.get("date_to") || null };
  const query = useExcludedCases(project.id, q);
  const items = query.data?.items ?? [];
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("incidents"), href: "/incidents" }, { label: t("excluded") }]} />
      <PageHeader title={t("excludedTitle")} description={t("excludedSubtitle")} />
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <Table data-testid="excluded-table">
          <THead>
            <TR>
              <TH>{t("list.ref")}</TH>
              <TH>{tcs("fields.case_no")}</TH>
              <TH>{t("list.occurred")}</TH>
              <TH>{tcs("fields.case_category")}</TH>
              <TH>{tcs("fields.exclusion")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((r) => (
              <TR key={`${r.incident_id}-${r.case_id ?? "x"}`} data-testid="excluded-row">
                <TD label={t("list.ref")}>
                  <Link href={`/incidents/${r.incident_id}`} className="ltr text-primary hover:underline">
                    {r.incident_ref}
                  </Link>
                </TD>
                <TD label={tcs("fields.case_no")}>{r.case_no ? <span className="ltr">{r.case_no}</span> : "—"}</TD>
                <TD label={t("list.occurred")}>{date(r.occurred_at)}</TD>
                <TD label={tcs("fields.case_category")}>{r.case_category ? te(`caseCategory.${r.case_category}`) : "—"}</TD>
                <TD label={tcs("fields.exclusion")}>
                  {r.reasons.map((x) => te(`rateExclusion.${x}`)).join(" · ")}
                  {r.reason_detail ? <span className="text-muted-foreground"> ({te.has(`notWorkRelated.${r.reason_detail as Schemas["NotWorkRelatedReason"]}`) ? te(`notWorkRelated.${r.reason_detail as Schemas["NotWorkRelatedReason"]}`) : r.reason_detail})</span> : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
