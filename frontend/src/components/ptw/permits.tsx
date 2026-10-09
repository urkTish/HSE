"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Layers, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { PossibleIdHint, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { ExportButtons } from "@/components/common/export-buttons";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { WindowsEditor } from "@/components/access/waps";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { useObstacles, useWaps } from "@/lib/api/access";
import { ApiError, api, unwrap, type Schemas } from "@/lib/api/client";
import { useAppointments, useIsolations, useJsaTemplates, usePermit, usePermits } from "@/lib/api/ptw";
import { WEEKDAYS } from "@/lib/access-enums";
import { useFieldErrorTranslator } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { CLOTHING, WORKLOADS } from "@/lib/heat-enums";
import { PERMIT_BLOCKERS, PERMIT_REGISTER_SORTS, PERMIT_STATUSES, PERMIT_TYPES, PTW_EXPOSURES } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { DateTimeInput, DecimalInput, GasStatusBadge, HighRiskBadge, PermitStatusBadge, PermitsSubNav, TypeChips, userLabel } from "./common";
import { sectionOf } from "./sections";
import { SimopsCheckView } from "./simops";

type S = Schemas;
type Permit = S["PermitRead"];
type WindowIn = { start_local: string; end_local: string; weekdays: S["Weekday"][] };
/** Finished permits: their last gas state is history, not an alert (no amber "No valid test" on closed rows). */
const FINISHED: S["PermitStatus"][] = ["closed", "cancelled", "expired"];
const PAGE_SIZE = 50;

/* ───────────────────────── Register ───────────────────────── */

export function PermitListPage() {
  return <ProjectGate>{(p) => <PermitList project={p} />}</ProjectGate>;
}

function PermitList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("permits");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const opts = useProjectOptions(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["PermitStatus"][];
  const types = s.getAll("work_type") as S["PermitType"][];
  const zones = s.getAll("zone_id");
  const engs = s.getAll("engagement_id");
  const q = usePermits(project.id, {
    status: status.length ? status : null,
    work_type: types.length ? types : null,
    site_id: s.get("site_id") || null,
    zone_id: zones.length ? zones : null,
    engagement_id: engs.length ? engs : null,
    live_on: s.get("live_on") || null,
    blocker: (s.get("blocker") as S["PermitBlocker"] | null) || null,
    awaiting_me: s.getBool("awaiting_me") ?? undefined,
    simops_open: s.getBool("simops_open") ?? null,
    worker_id: s.get("worker_id") || null,
    isolation_id: s.get("isolation_id") || null,
    wap_id: s.get("wap_id") || null,
    status_reason: (s.get("status_reason") as S["StatusReason"] | null) || null,
    q: s.get("q") || null,
    sort: (s.get("sort") as S["PermitRegisterSort"] | null) || undefined,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "permit.prepare", project.id) ? (
            <Button asChild>
              <Link href="/permits/new" data-testid="new-permit">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <PermitsSubNav />
      <ListToolbar actions={can(me, "export.ptw", project.id) ? <ExportButtons dataset="permits" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="pm-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="pm-status" label={tc("status")} options={PERMIT_STATUSES.map((x) => ({ value: x, label: te(`permitStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} testId="filter-status" />
        <MultiSelect id="pm-type" label={t("workType")} options={PERMIT_TYPES.map((x) => ({ value: x, label: te(`permitType.${x}`) }))} value={types} onChange={(v) => s.set({ work_type: v })} />
        <SelectFilter id="pm-site" label={tc("site")} value={s.get("site_id") ?? ""} onChange={(v) => s.set({ site_id: v })} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} />
        <MultiSelect id="pm-zone" label={tc("zone")} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={(v) => s.set({ zone_id: v })} />
        <MultiSelect id="pm-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <FormField id="pm-live" label={t("liveOn")}>
          <Input type="date" className="ltr" value={s.get("live_on") ?? ""} onChange={(e) => s.set({ live_on: e.target.value })} />
        </FormField>
        <SelectFilter id="pm-blocker" label={t("blocker")} value={(s.get("blocker") ?? "") as S["PermitBlocker"] | ""} onChange={(v) => s.set({ blocker: v })} options={PERMIT_BLOCKERS.map((x) => ({ value: x, label: te(`permitBlocker.${x}`) }))} />
        <SelectFilter id="pm-awaiting" label={t("awaitingMe")} value={s.get("awaiting_me") === "true" ? "true" : ""} onChange={(v) => s.set({ awaiting_me: v })} options={[{ value: "true", label: tc("yes") }]} />
        <SelectFilter id="pm-simops" label={t("simopsOpen")} value={s.get("simops_open") === "true" ? "true" : ""} onChange={(v) => s.set({ simops_open: v })} options={[{ value: "true", label: tc("yes") }]} />
        <SelectFilter id="pm-sort" label={t("sort")} value={(s.get("sort") ?? "") as S["PermitRegisterSort"] | ""} onChange={(v) => s.set({ sort: v })} options={PERMIT_REGISTER_SORTS.map((x) => ({ value: x, label: te(`permitSort.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="permits-table">
            <THead>
              <TR>
                <TH>{t("permitNo")}</TH>
                <TH>{t("titleCol")}</TH>
                <TH>{tc("zone")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("validity")}</TH>
                <TH>{t("crew")}</TH>
                <TH>{t("gas")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((p) => (
                <TR key={p.id} data-testid="permit-row" data-permit-no={p.permit_no}>
                  <TD label={t("permitNo")}>
                    <Link href={`/permits/${p.id}`} className="ltr font-medium text-primary hover:underline">
                      {p.display_no}
                    </Link>
                    <span className="mt-1 flex flex-wrap gap-1">
                      <TypeChips types={p.work_types} primary={p.primary_type} short />
                      <HighRiskBadge show={p.high_risk} />
                    </span>
                  </TD>
                  <TD label={t("titleCol")}>
                    <span className="line-clamp-2">{p.title}</span>
                    <span className="block text-xs text-muted-foreground">
                      {t("receiverShort")}: {userLabel(p.receiver, locale)}
                    </span>
                  </TD>
                  <TD label={tc("zone")}>
                    <bdi className="ltr">{p.zones.map((z) => z.code).join(", ")}</bdi>
                  </TD>
                  <TD label={tc("contractor")}>{p.engagement.short_code}</TD>
                  <TD label={t("validity")}>
                    <span className="text-xs">
                      {dateTime(p.valid_from_at)}
                      <br />→ {dateTime(p.valid_to_at)}
                    </span>
                  </TD>
                  <TD label={t("crew")}>
                    <bdi className="ltr tabular-nums">{p.crew_count}</bdi>
                  </TD>
                  <TD label={t("gas")}>
                    {p.gas_status !== "not_required" ? <GasStatusBadge status={p.gas_status} muted={FINISHED.includes(p.status)} prefix={false} /> : <span className="text-muted-foreground">—</span>}
                  </TD>
                  <TD label={tc("status")}>
                    <PermitStatusBadge status={p.status} reason={p.status_reason} />
                    {p.blockers.length ? <span className="block text-xs text-danger">{t("blockersN", { n: p.blockers.length })}</span> : null}
                    {p.simops_open ? (
                      <span className="flex items-center gap-1 text-xs text-warning">
                        <Layers aria-hidden className="size-3" />
                        {t("simopsN", { n: p.simops_open })}
                      </span>
                    ) : null}
                    {p.post_expiry_check_pending ? <span className="block text-xs text-warning">{t("postExpiryPending")}</span> : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────────────────── Create / edit ───────────────────────── */

export function PermitCreatePage() {
  const t = useTranslations("permits");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/permits" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <ProjectGate>{(p) => <PermitForm project={p} />}</ProjectGate>
    </div>
  );
}

export function PermitEditPage({ id }: { id: string }) {
  const t = useTranslations("permits");
  const q = usePermit(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return (
    <div>
      <Breadcrumbs
        items={[
          { label: t("title"), href: "/permits" },
          { label: q.data.display_no, href: `/permits/${id}` },
          { label: t("edit") },
        ]}
      />
      <PageHeader title={t("edit")} />
      <ProjectById id={q.data.project_id}>{(p) => <PermitForm project={p} permit={q.data} />}</ProjectById>
    </div>
  );
}

function hhmm(v: string): string {
  return v.slice(0, 5);
}

/** Appointment holders (users) of one function, optionally covering a site, for issuer / area authority pickers. */
function useAppointedUsers(projectId: string, fn: S["AppointmentFunction"], siteId: string) {
  const locale = useLocale();
  const q = useAppointments(projectId, { function: [fn], status: ["active"], site_id: siteId || null, page_size: 200 });
  return useMemo(() => {
    const m = new Map<string, { value: string; label: string; types: S["PermitType"][] }>();
    for (const a of q.data?.items ?? []) if (a.holder_user) m.set(a.holder_user.id, { value: a.holder_user.id, label: `${userLabel(a.holder_user, locale)} · ${a.appointment_no}`, types: a.permit_types });
    return [...m.values()];
  }, [q.data, locale]);
}

function PermitForm({ project, permit }: { project: S["ProjectRead"]; permit?: Permit }) {
  const t = useTranslations("permits");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const fieldMsg = useFieldErrorTranslator();
  const opts = useProjectOptions(project.id);
  const airport = project.is_airport;
  const [site, setSite] = useState(permit?.site.id ?? "");
  const [zones, setZones] = useState<string[]>(permit?.zones.map((z) => z.id) ?? []);
  const [loc, setLoc] = useState(permit?.location_desc ?? "");
  const [gx, setGx] = useState(permit?.grid_x_m ?? "");
  const [gy, setGy] = useState(permit?.grid_y_m ?? "");
  const [level, setLevel] = useState(permit?.level_code ?? "");
  const [elev, setElev] = useState(permit?.elevation_m ?? "");
  const [eng, setEng] = useState(permit?.engagement.id ?? "");
  const [types, setTypes] = useState<S["PermitType"][]>(permit?.work_types ?? []);
  const [primary, setPrimary] = useState<S["PermitType"] | "">(permit?.primary_type ?? "");
  const [title, setTitle] = useState(permit?.title ?? "");
  const [scopeEn, setScopeEn] = useState(permit?.scope_en ?? "");
  const [scopeAr, setScopeAr] = useState(permit?.scope_ar ?? "");
  const [exposure, setExposure] = useState<S["Exposure"] | "">(permit?.exposure ?? "");
  const [heatWorkload, setHeatWorkload] = useState<S["Workload"] | "">(permit?.heat_workload ?? "");
  const [heatClothing, setHeatClothing] = useState<S["Clothing"]>(permit?.heat_clothing ?? "work_clothes");
  const [heatHood, setHeatHood] = useState(permit?.heat_hood ?? false);
  const [flammables, setFlammables] = useState(permit?.flammables_in_use ?? false);
  const [engine, setEngine] = useState(permit?.combustion_engine_plant ?? false);
  const [from, setFrom] = useState(permit?.valid_from_at ?? "");
  const [to, setTo] = useState(permit?.valid_to_at ?? "");
  const [windows, setWindows] = useState<WindowIn[]>(permit?.windows.map((w) => ({ start_local: hhmm(w.start_local), end_local: hhmm(w.end_local), weekdays: w.weekdays })) ?? [{ start_local: "07:00", end_local: "17:00", weekdays: [...WEEKDAYS] }]);
  const iAmReceiver = can(me, "permit.receive", project.id);
  const [receiver, setReceiver] = useState(permit?.receiver.id ?? (iAmReceiver ? me.id : ""));
  const [area, setArea] = useState(permit?.area_authority?.id ?? "");
  const [issuer, setIssuer] = useState(permit?.issuer?.id ?? "");
  const [hse, setHse] = useState(permit?.hse_reviewer?.id ?? "");
  const [condEn, setCondEn] = useState(permit?.conditions_en ?? "");
  const [condAr, setCondAr] = useState(permit?.conditions_ar ?? "");
  const [emergency, setEmergency] = useState(permit?.emergency_info ?? "");
  const [waps, setWaps] = useState<string[]>(permit?.waps.map((w) => w.id) ?? []);
  const [obs, setObs] = useState<string[]>(permit?.obstacle_clearances.map((o) => o.id) ?? []);
  const [isos, setIsos] = useState<string[]>(permit?.isolations.map((i) => i.id) ?? []);
  const [jsaTemplate, setJsaTemplate] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [simops, setSimops] = useState<S["SimopsCheckResult"] | null>(null);
  const [simopsError, setSimopsError] = useState<unknown>(null);
  const areaUsers = useAppointedUsers(project.id, "area_authority", site);
  const issuers = useAppointedUsers(project.id, "issuer", site);
  const wapQ = useWaps(project.id, { status: ["approved", "active", "suspended"], page_size: 200 }, { enabled: airport });
  const obsQ = useObstacles(project.id, { status: ["approved", "approved_with_conditions"], page_size: 200 }, { enabled: airport });
  const isoQ = useIsolations(project.id, { status: ["planned", "isolated", "verified"], page_size: 200 });
  const templates = useJsaTemplates(project.id, { status: ["approved"], page_size: 200 }, { enabled: !permit });
  const siteZones = opts.zones.filter((z) => z.siteId === site);
  const anyAirside = zones.some((z) => opts.zoneById.get(z)?.zone_type === "airside");
  const effectiveTypes = anyAirside && !types.includes("airside_works") ? [...types, "airside_works" as const] : types;

  function body(): S["PermitCreate"] {
    return {
      site_id: site,
      zone_ids: zones,
      location_desc: loc.trim(),
      grid_x_m: gx || null,
      grid_y_m: gy || null,
      level_code: level || null,
      elevation_m: elev || null,
      engagement_id: eng,
      work_types: effectiveTypes,
      primary_type: (primary || effectiveTypes[0]) as S["PermitType"],
      title: title.trim(),
      scope_en: scopeEn.trim(),
      scope_ar: scopeAr.trim() || null,
      exposure: exposure || null,
      heat_workload: exposure === "indoor" ? null : heatWorkload || null,
      heat_clothing: exposure === "indoor" ? null : heatClothing,
      heat_hood: exposure !== "indoor" && heatHood,
      flammables_in_use: flammables,
      combustion_engine_plant: engine,
      valid_from_at: from,
      valid_to_at: to,
      windows,
      receiver_user_id: receiver,
      area_authority_user_id: area || null,
      issuer_user_id: issuer || null,
      hse_reviewer_user_id: hse || null,
      conditions_en: condEn.trim() || null,
      conditions_ar: condAr.trim() || null,
      emergency_info: emergency.trim(),
      linked_wap_ids: waps,
      linked_obs_ids: obs,
      isolation_cert_ids: isos,
      jsa_template_id: jsaTemplate || null,
    };
  }

  function validate(): boolean {
    const e: Record<string, string> = {};
    const req = tc("required");
    if (!site) e.site_id = req;
    if (zones.length < 1 || zones.length > 3) e.zone_ids = t("zones13");
    if (!loc.trim()) e.location_desc = req;
    if (Boolean(gx) !== Boolean(gy)) e.grid_x_m = t("gridBoth");
    if (level && !elev) e.elevation_m = t("elevationNeeded");
    if (!eng) e.engagement_id = req;
    if (!effectiveTypes.length) e.work_types = req;
    if (!title.trim()) e.title = req;
    if (!scopeEn.trim()) e.scope_en = req;
    if (!from) e.valid_from_at = req;
    if (!to) e.valid_to_at = req;
    if (from && to && new Date(to) <= new Date(from)) e.valid_to_at = t("toAfterFrom");
    if (!windows.length || windows.length > 3) e.windows = t("windows13");
    if (!receiver) e.receiver_user_id = req;
    if (!emergency.trim()) e.emergency_info = req;
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function save() {
    if (!validate()) return;
    setBusy(true);
    setError(null);
    try {
      const b = body();
      let out: Permit;
      if (permit) {
        const { jsa_template_id: _j, site_id: _s, engagement_id: _e, ...upd } = b;
        void _j;
        void _s;
        void _e;
        out = await unwrap(api.PATCH("/api/v1/permits/{permit_id}", { params: { path: { permit_id: permit.id } }, body: upd }));
      } else {
        out = await unwrap(api.POST("/api/v1/projects/{project_id}/permits", { params: { path: { project_id: project.id } }, body: b }));
      }
      warn(out.write_warnings);
      await qc.invalidateQueries({ queryKey: ["permits"] });
      qc.setQueryData(["permit", out.id], out);
      toast.success(permit ? tc("saved") : t("created", { no: out.display_no }));
      router.push(`/permits/${out.id}`);
    } catch (err) {
      setError(err);
      if (err instanceof ApiError && err.fieldErrors.length) {
        const m: Record<string, string> = {};
        for (const fe of err.fieldErrors) {
          const k = fe.loc.filter((x) => x !== "body").map(String)[0];
          if (k) m[k] = fieldMsg(fe.type, fe.msg, fe.msg_ar);
        }
        setErrors(m);
      }
    } finally {
      setBusy(false);
    }
  }

  async function checkSimops() {
    setSimopsError(null);
    if (!site || !zones.length || !eng || !effectiveTypes.length || !from || !to) {
      setSimopsError(new ApiError(422, { code: "VALIDATION_ERROR", message: t("simopsNeeds") }));
      return;
    }
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/simops-check", {
          params: { path: { project_id: project.id } },
          body: {
            permit_id: permit?.id ?? null,
            site_id: site,
            zone_ids: zones,
            engagement_id: eng,
            work_types: effectiveTypes,
            grid_x_m: gx || null,
            grid_y_m: gy || null,
            elevation_m: elev || null,
            valid_from_at: from,
            valid_to_at: to,
            windows,
            flammables_in_use: flammables,
            combustion_engine_plant: engine,
            ...sectionGeometry(permit),
          },
        }),
      );
      setSimops(r);
    } catch (e) {
      setSimopsError(e);
    }
  }

  const userOpts = (list: { value: string; label: string }[], v: string, on: (v: string) => void, id: string) => (
    <Select id={id} value={v} onChange={(e) => on(e.target.value)} data-testid={id}>
      <option value="">{tc("select")}</option>
      {list.map((u) => (
        <option key={u.value} value={u.value}>
          {u.label}
        </option>
      ))}
    </Select>
  );

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      noValidate
      data-testid="permit-form"
    >
      <FormSection title={t("s.where")} description={t("h.where")}>
        <FormField id="pf-site" label={tc("site")} required error={errors.site_id}>
          <Select
            value={site}
            disabled={Boolean(permit)}
            onChange={(e) => {
              setSite(e.target.value);
              setZones([]);
            }}
            data-testid="pf-site"
          >
            <option value="">{tc("select")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="flex flex-col gap-1">
          <MultiSelect id="pf-zones" label={`${t("zones")} *`} options={siteZones.map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={setZones} testId="pf-zones" />
          {errors.zone_ids ? <p className="text-xs font-medium text-destructive">{errors.zone_ids}</p> : null}
        </div>
        <FormField id="pf-loc" label={t("location")} required error={errors.location_desc} className="sm:col-span-2">
          <Input value={loc} onChange={(e) => setLoc(e.target.value)} maxLength={200} data-testid="pf-location" />
        </FormField>
        <FormField id="pf-gx" label={t("gridX")} error={errors.grid_x_m} hint={t("gridHint")}>
          <DecimalInput value={gx} onChange={setGx} data-testid="pf-grid-x" />
        </FormField>
        <FormField id="pf-gy" label={t("gridY")}>
          <DecimalInput value={gy} onChange={setGy} data-testid="pf-grid-y" />
        </FormField>
        <FormField id="pf-level" label={t("level")}>
          <Input className="ltr" value={level} onChange={(e) => setLevel(e.target.value)} maxLength={10} />
        </FormField>
        <FormField id="pf-elev" label={t("elevation")} error={errors.elevation_m}>
          <DecimalInput value={elev} onChange={setElev} />
        </FormField>
      </FormSection>

      <FormSection title={t("s.what")} description={t("h.what")}>
        <FormField id="pf-eng" label={tc("contractor")} required error={errors.engagement_id}>
          <Select value={eng} disabled={Boolean(permit)} onChange={(e) => setEng(e.target.value)} data-testid="pf-engagement">
            <option value="">{tc("select")}</option>
            {opts.engagements
              .filter((x) => !site || x.siteIds.length === 0 || x.siteIds.includes(site))
              .map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
          </Select>
        </FormField>
        <FormField id="pf-title" label={t("titleField")} required error={errors.title}>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={150} data-testid="pf-title" />
        </FormField>
        <CheckboxGroup
          id="pf-types"
          legend={t("workTypes")}
          required
          error={errors.work_types}
          options={PERMIT_TYPES.map((x) => ({ value: x, label: te(`permitType.${x}`) }))}
          value={effectiveTypes}
          onChange={(v) => {
            setTypes(v);
            if (primary && !v.includes(primary)) setPrimary("");
          }}
          className="sm:col-span-2"
          hint={anyAirside ? t("airsideAuto") : undefined}
        />
        <FormField id="pf-primary" label={t("primaryType")} required hint={t("primaryHint")}>
          <Select value={primary || effectiveTypes[0] || ""} onChange={(e) => setPrimary(e.target.value as S["PermitType"])} data-testid="pf-primary">
            {effectiveTypes.map((x) => (
              <option key={x} value={x}>
                {te(`permitType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="pf-exposure" label={t("exposure")} hint={t("exposureHint")}>
          <Select value={exposure} onChange={(e) => setExposure(e.target.value as S["Exposure"] | "")}>
            <option value="">{t("fromZone")}</option>
            {PTW_EXPOSURES.map((x) => (
              <option key={x} value={x}>
                {te(`exposure.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {exposure !== "indoor" ? (
          <>
            <FormField id="pf-heat-workload" label={t("heatWorkload")} hint={t("heatWorkloadHint")}>
              <Select value={heatWorkload} onChange={(e) => setHeatWorkload(e.target.value as S["Workload"] | "")} data-testid="pf-heat-workload">
                <option value="">{t("heatByType")}</option>
                {WORKLOADS.map((x) => (
                  <option key={x} value={x}>
                    {te(`workload.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="pf-heat-clothing" label={t("heatClothing")} hint={t("heatClothingHint")}>
              <Select value={heatClothing} onChange={(e) => setHeatClothing(e.target.value as S["Clothing"])} data-testid="pf-heat-clothing">
                {CLOTHING.map((x) => (
                  <option key={x} value={x}>
                    {te(`clothing.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <CheckboxField id="pf-heat-hood" label={t("heatHoodLabel")}>
              <Checkbox checked={heatHood} onChange={(e) => setHeatHood(e.target.checked)} data-testid="pf-heat-hood" />
            </CheckboxField>
          </>
        ) : null}
        <CheckboxField id="pf-flam" label={t("flammables")}>
          <Checkbox checked={flammables} onChange={(e) => setFlammables(e.target.checked)} />
        </CheckboxField>
        <CheckboxField id="pf-engine" label={t("engine")}>
          <Checkbox checked={engine} onChange={(e) => setEngine(e.target.checked)} />
        </CheckboxField>
        <FormField id="pf-scope-en" label={t("scopeEn")} required error={errors.scope_en} className="sm:col-span-2">
          <Textarea value={scopeEn} onChange={(e) => setScopeEn(e.target.value)} maxLength={1000} data-testid="pf-scope" />
        </FormField>
        <PossibleIdHint text={scopeEn} />
        <FormField id="pf-scope-ar" label={t("scopeAr")} className="sm:col-span-2">
          <Textarea dir="rtl" value={scopeAr} onChange={(e) => setScopeAr(e.target.value)} maxLength={1000} />
        </FormField>
        {!permit ? (
          <FormField id="pf-jsa" label={t("jsaTemplate")} hint={t("jsaTemplateHint")}>
            <Select value={jsaTemplate} onChange={(e) => setJsaTemplate(e.target.value)} data-testid="pf-jsa-template">
              <option value="">{t("blankJsa")}</option>
              {(templates.data?.items ?? [])
                .filter((x) => !effectiveTypes.length || x.work_types.some((w) => effectiveTypes.includes(w)))
                .map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.jsa_no} · {locale === "ar" && x.title_ar ? x.title_ar : x.title_en}
                  </option>
                ))}
            </Select>
          </FormField>
        ) : null}
      </FormSection>

      <FormSection title={t("s.when")} description={t("h.when")}>
        <FormField id="pf-from" label={t("validFrom")} required error={errors.valid_from_at}>
          <DateTimeInput value={from} onChange={setFrom} data-testid="pf-from" />
        </FormField>
        <FormField id="pf-to" label={t("validTo")} required error={errors.valid_to_at}>
          <DateTimeInput value={to} onChange={setTo} data-testid="pf-to" />
        </FormField>
        <div className="sm:col-span-2">
          <WindowsEditor value={windows} onChange={setWindows} />
          {errors.windows ? <p className="text-xs font-medium text-destructive">{errors.windows}</p> : null}
        </div>
      </FormSection>

      <FormSection title={t("s.who")} description={t("h.who")}>
        <FormField id="pf-receiver" label={t("receiver")} required error={errors.receiver_user_id}>
          {iAmReceiver && !me.is_hse_manager ? (
            <Select value={receiver} onChange={(e) => setReceiver(e.target.value)} data-testid="pf-receiver">
              <option value={me.id}>{userLabel(me, locale)}</option>
            </Select>
          ) : (
            <UserSelect projectId={project.id} role="permit_receiver" value={receiver} onChange={(e) => setReceiver(e.target.value)} data-testid="pf-receiver" />
          )}
        </FormField>
        <FormField id="pf-area" label={t("areaAuthority")} hint={t("areaHint")}>
          {userOpts(areaUsers, area, setArea, "pf-area")}
        </FormField>
        <FormField id="pf-issuer" label={t("issuer")} hint={t("issuerHint")}>
          {userOpts(
            issuers.filter((u) => effectiveTypes.every((x) => u.types.includes(x))),
            issuer,
            setIssuer,
            "pf-issuer",
          )}
        </FormField>
        <FormField id="pf-hse" label={t("hseReviewer")} hint={t("hseHint")}>
          <UserSelect projectId={project.id} role="hse_officer" value={hse} onChange={(e) => setHse(e.target.value)} data-testid="pf-hse" />
        </FormField>
        <FormField id="pf-emergency" label={t("emergency")} required error={errors.emergency_info} hint={t("emergencyHint")} className="sm:col-span-2">
          <Textarea value={emergency} onChange={(e) => setEmergency(e.target.value)} maxLength={300} data-testid="pf-emergency" />
        </FormField>
        <FormField id="pf-cond-en" label={t("conditionsEn")}>
          <Textarea value={condEn} onChange={(e) => setCondEn(e.target.value)} maxLength={1000} />
        </FormField>
        <FormField id="pf-cond-ar" label={t("conditionsAr")}>
          <Textarea dir="rtl" value={condAr} onChange={(e) => setCondAr(e.target.value)} maxLength={1000} />
        </FormField>
      </FormSection>

      <FormSection title={t("s.links")} description={t("h.links")}>
        {airport ? (
          <>
            <MultiSelect id="pf-waps" label={t("linkedWaps")} options={(wapQ.data?.items ?? []).map((w) => ({ value: w.id, label: `${w.wap_no} · ${w.zones.map((z) => z.code).join(", ")}` }))} value={waps} onChange={setWaps} />
            <MultiSelect id="pf-obs" label={t("linkedObs")} options={(obsQ.data?.items ?? []).map((o) => ({ value: o.id, label: o.obs_no }))} value={obs} onChange={setObs} />
          </>
        ) : null}
        <MultiSelect id="pf-isos" label={t("isolationCerts")} options={(isoQ.data?.items ?? []).map((i) => ({ value: i.id, label: `${i.iso_no} · ${i.equipment_desc}` }))} value={isos} onChange={setIsos} />
      </FormSection>

      <section className="flex flex-col gap-3 rounded-xl border bg-surface p-4" data-testid="simops-preview">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">{t("simopsTitle")}</h2>
            <p className="text-sm text-muted-foreground">{t("simopsHint")}</p>
          </div>
          <Button type="button" variant="outline" onClick={() => void checkSimops()} data-testid="run-simops-preview">
            <Layers aria-hidden />
            {t("checkSimops")}
          </Button>
        </div>
        <MutationError error={simopsError} />
        {simops ? <SimopsCheckView result={simops} /> : null}
      </section>

      {Object.keys(errors).length ? <Alert tone="danger">{t("fixErrors")}</Alert> : null}
      <MutationError error={error} />
      <div className="sticky bottom-0 -mx-4 flex gap-2 border-t bg-background/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0">
        <Button type="submit" disabled={busy} data-testid="save-permit">
          {busy ? tc("saving") : permit ? tc("save") : t("createDraft")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

type Num = string | number | null;
/** Geometry the SIMOPS rules use, taken from the permit's saved sections (absent on a new draft). */
function sectionGeometry(permit: Permit | undefined) {
  const v = (type: S["PermitType"], k: string): Num => {
    if (!permit) return null;
    const x = sectionOf(permit, type)?.[k];
    return typeof x === "string" || typeof x === "number" ? x : null;
  };
  return {
    hot_work_height_above_floor_m: v("hot_work", "work_height_above_floor_m"),
    lifting_landing_grid_x_m: v("lifting", "landing_grid_x_m"),
    lifting_landing_grid_y_m: v("lifting", "landing_grid_y_m"),
    lifting_exclusion_radius_m: v("lifting", "exclusion_radius_m"),
    lifting_appliance_grid_x_m: v("lifting", "appliance_grid_x_m"),
    lifting_appliance_grid_y_m: v("lifting", "appliance_grid_y_m"),
    lifting_slew_radius_m: v("lifting", "slew_radius_m"),
    radiography_planned_barrier_m: v("radiography", "planned_barrier_m"),
    excavation_max_depth_m: v("excavation", "max_depth_m"),
    electrical_energized: permit ? sectionOf(permit, "electrical_isolation")?.work_condition === "energized" : false,
  };
}
