"use client";
import { useQueryClient } from "@tanstack/react-query";
import {
  Clock,
  CloudFog,
  GitBranch,
  Pencil,
  Plus,
  Printer,
  Trash2,
  TriangleAlert,
  UserPlus,
} from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiWarnings,
  useWarningToasts,
} from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import {
  ListToolbar,
  SearchFilter,
  SelectFilter,
} from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  MutationError,
} from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import {
  CREDENTIAL_REASONS,
  CREW_ROLES,
  OPS_EVENT_SOURCES,
  OPS_EVENT_TYPES,
  WAP_BLOCKERS,
  WAP_STATUSES,
  WEEKDAYS,
} from "@/lib/access-enums";
import {
  ak,
  useNotams,
  useObstacles,
  useOpsEvent,
  useOpsEvents,
  useWap,
  useWapBoard,
  useWapPrint,
  useWaps,
  useZoneProfiles,
} from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { todayInZone, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { joinList, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import {
  AccessPrintHeader,
  AirportOnly,
  BiLabel,
  Blockers,
  Code,
  DeploymentPicker,
  QrImage,
  ReasonChips,
  StepDialog,
  SubNav,
  VehicleSelect,
  personName,
} from "./common";

const PAGE_SIZE = 50;
type Wap = Schemas["WapRead"];
type Weekday = Schemas["Weekday"];
type WindowIn = { start_local: string; end_local: string; weekdays: Weekday[] };
type CrewRow = {
  worker_id: string;
  worker_no: string;
  name: string;
  crew_role: Schemas["CrewRole"];
  escort_worker_id: string | null;
};
type VehRow = {
  vehicle_id: string;
  label: string;
  escort_vehicle_id: string | null;
  height_limited_to_m: string;
};

function WapSubNav() {
  const t = useTranslations("waps");
  return (
    <SubNav
      items={[
        { href: "/waps", label: t("title"), testId: "sub-waps" },
        { href: "/wap-board", label: t("board"), testId: "sub-wap-board" },
        {
          href: "/ops-events",
          label: t("opsEvents"),
          testId: "sub-ops-events",
        },
      ]}
    />
  );
}

function hhmm(t: string): string {
  return t.slice(0, 5);
}

function WindowsText({ windows }: { windows: Schemas["WapWindowRead"][] }) {
  const te = useTranslations("enums");
  const t = useTranslations("waps");
  return (
    <span className="flex flex-col gap-0.5">
      {windows.map((w, i) => (
        <span key={i} className="text-sm">
          <bdi className="ltr tabular-nums">
            {hhmm(w.start_local)}–{hhmm(w.end_local)}
          </bdi>
          {w.crosses_midnight ? (
            <span className="text-xs text-muted-foreground">
              {" "}
              ({t("overnight")})
            </span>
          ) : null}
          <span className="block text-xs text-muted-foreground">
            {w.weekdays.length === 7
              ? t("everyDay")
              : joinList(w.weekdays.map((d) => te(`weekday.${d}`)))}
          </span>
        </span>
      ))}
    </span>
  );
}

/* ───────────────────────────── List ───────────────────────────── */

export function WapListPage() {
  return (
    <ProjectGate>
      {(p) => <AirportOnly project={p}>{<WapList project={p} />}</AirportOnly>}
    </ProjectGate>
  );
}

function WapList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["WapStatus"][];
  const zones = s.getAll("zone_id");
  const engs = s.getAll("engagement_id");
  const query = useWaps(project.id, {
    status: status.length ? status : null,
    site_id: s.get("site_id") || null,
    zone_id: zones.length ? zones : null,
    engagement_id: engs.length ? engs : null,
    active_on: s.get("active_on") || null,
    blocked: s.getBool("blocked") ?? null,
    blocker: (s.get("blocker") as Schemas["WapBlocker"] | null) || null,
    worker_id: s.get("worker_id") || null,
    vehicle_id: s.get("vehicle_id") || null,
    q: s.get("q") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "wap.edit", project.id) ? (
            <Button asChild>
              <Link href="/waps/new" data-testid="new-wap">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <WapSubNav />
      <ListToolbar
        actions={
          can(me, "export.access", project.id) ? (
            <ExportButtons dataset="waps" params={{ project_id: project.id }} />
          ) : null
        }
      >
        <SearchFilter
          id="wp-q"
          value={s.get("q") ?? ""}
          onChange={(v) => s.set({ q: v })}
          placeholder={t("searchHint")}
        />
        <MultiSelect
          id="wp-status"
          label={tc("status")}
          options={WAP_STATUSES.map((x) => ({
            value: x,
            label: te(`wapStatus.${x}`),
          }))}
          value={status}
          onChange={(v) => s.set({ status: v })}
        />
        <MultiSelect
          id="wp-zone"
          label={tc("zone")}
          options={opts.zones
            .filter((z) => z.zoneType === "airside")
            .map((z) => ({ value: z.value, label: z.label }))}
          value={zones}
          onChange={(v) => s.set({ zone_id: v })}
        />
        <MultiSelect
          id="wp-eng"
          label={tc("contractor")}
          options={opts.engagements}
          value={engs}
          onChange={(v) => s.set({ engagement_id: v })}
          allLabel={tc("anyContractor")}
        />
        <SelectFilter
          id="wp-blocked"
          label={t("blocked")}
          value={s.get("blocked") === "true" ? "true" : ""}
          onChange={(v) => s.set({ blocked: v })}
          options={[{ value: "true", label: tc("yes") }]}
        />
        <SelectFilter
          id="wp-blocker"
          label={t("blocker")}
          value={(s.get("blocker") ?? "") as Schemas["WapBlocker"] | ""}
          onChange={(v) => s.set({ blocker: v })}
          options={WAP_BLOCKERS.map((x) => ({
            value: x,
            label: te(`wapBlocker.${x}`),
          }))}
        />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="waps-table">
            <THead>
              <TR>
                <TH>{t("fields.wap_no")}</TH>
                <TH>{t("fields.zones")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("fields.dates")}</TH>
                <TH>{t("fields.windows")}</TH>
                <TH>{t("crew")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((w) => (
                <TR key={w.id} data-testid="wap-row" data-wap-no={w.wap_no}>
                  <TD label={t("fields.wap_no")}>
                    <Link
                      href={`/waps/${w.id}`}
                      className="ltr font-medium text-primary hover:underline"
                    >
                      {w.wap_no}
                    </Link>
                    {w.revision_no > 0 ? (
                      <span className="ms-1 text-xs text-muted-foreground">
                        r{w.revision_no}
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("fields.zones")}>
                    <span className="ltr">
                      {w.zones.map((z) => z.code).join(", ")}
                    </span>
                  </TD>
                  <TD label={tc("contractor")}>{w.engagement.short_code}</TD>
                  <TD label={t("fields.dates")}>
                    {date(w.valid_from)} – {date(w.valid_to)}
                  </TD>
                  <TD label={t("fields.windows")}>
                    <WindowsText windows={w.windows} />
                  </TD>
                  <TD label={t("crew")}>
                    {w.crew_count} · {t("vehiclesN", { n: w.vehicle_count })}
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge
                      status={w.status}
                      label={te(`wapStatus.${w.status}`)}
                    />
                    {w.blockers.length ? (
                      <span className="block text-xs text-warning">
                        {t("blockersN", { n: w.blockers.length })}
                      </span>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={query.data?.total ?? 0}
            onPage={(p) => s.set({ page: p })}
          />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────────────────────── Form ───────────────────────────── */

export function WapCreatePage() {
  const t = useTranslations("waps");
  return (
    <div>
      <Breadcrumbs
        items={[{ label: t("title"), href: "/waps" }, { label: t("new") }]}
      />
      <PageHeader title={t("new")} description={t("newHint")} />
      <ProjectGate>
        {(p) => (
          <AirportOnly project={p}>{<WapForm project={p} />}</AirportOnly>
        )}
      </ProjectGate>
    </div>
  );
}

export function WapEditPage({ id }: { id: string }) {
  const t = useTranslations("waps");
  const q = useWap(id);
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return (
    <div>
      <Breadcrumbs
        items={[
          { label: t("title"), href: "/waps" },
          { label: q.data.wap_no, href: `/waps/${id}` },
          { label: t("edit") },
        ]}
      />
      <PageHeader title={t("edit")} />
      <ProjectById id={q.data.project_id}>
        {(p) => <WapForm project={p} wap={q.data} />}
      </ProjectById>
    </div>
  );
}

export function WindowsEditor({
  value,
  onChange,
}: {
  value: WindowIn[];
  onChange: (v: WindowIn[]) => void;
}) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  return (
    <div className="flex flex-col gap-3" data-testid="windows-editor">
      {value.map((w, i) => (
        <div
          key={i}
          className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[auto_auto_1fr_auto] sm:items-end"
          data-testid="window-row"
        >
          <FormField id={`win-start-${i}`} label={t("start")}>
            <Input
              type="time"
              className="ltr"
              value={w.start_local}
              onChange={(e) =>
                onChange(
                  value.map((x, j) =>
                    j === i ? { ...x, start_local: e.target.value } : x,
                  ),
                )
              }
            />
          </FormField>
          <FormField id={`win-end-${i}`} label={t("end")}>
            <Input
              type="time"
              className="ltr"
              value={w.end_local}
              onChange={(e) =>
                onChange(
                  value.map((x, j) =>
                    j === i ? { ...x, end_local: e.target.value } : x,
                  ),
                )
              }
            />
          </FormField>
          <MultiSelect
            id={`win-days-${i}`}
            label={t("weekdays")}
            options={WEEKDAYS.map((d) => ({
              value: d,
              label: te(`weekday.${d}`),
            }))}
            value={w.weekdays}
            onChange={(v) =>
              onChange(
                value.map((x, j) =>
                  j === i ? { ...x, weekdays: v as Weekday[] } : x,
                ),
              )
            }
            className="lg:w-full"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={tc("remove")}
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            <Trash2 aria-hidden />
          </Button>
          {w.end_local && w.start_local && w.end_local <= w.start_local ? (
            <p className="text-xs text-muted-foreground sm:col-span-4">
              {t("overnightHint")}
            </p>
          ) : null}
        </div>
      ))}
      {value.length < 3 ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() =>
            onChange([
              ...value,
              {
                start_local: "07:00",
                end_local: "17:00",
                weekdays: [...WEEKDAYS],
              },
            ])
          }
          data-testid="add-window"
        >
          <Plus aria-hidden />
          {t("addWindow")}
        </Button>
      ) : null}
    </div>
  );
}

function useLinkOptions(projectId: string) {
  const notams = useNotams(projectId, {
    status: ["draft", "submitted_to_ops", "requested_from_ais", "issued"],
    page_size: 200,
  });
  const obs = useObstacles(projectId, {
    status: ["submitted", "approved", "approved_with_conditions", "suspended"],
    page_size: 200,
  });
  return {
    notams: (notams.data?.items ?? []).map((n) => ({
      value: n.id,
      label: `${n.ntm_no}${n.notam_number ? ` · ${n.notam_number}` : ""}`,
    })),
    obstacles: (obs.data?.items ?? []).map((o) => ({
      value: o.id,
      label: `${o.obs_no} · ${o.heights.max_height_m_agl} m`,
    })),
  };
}

function WapForm({
  project,
  wap,
}: {
  project: Schemas["ProjectRead"];
  wap?: Wap;
}) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const locale = useLocale();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const opts = useProjectOptions(project.id);
  const links = useLinkOptions(project.id);
  const [site, setSite] = useState(wap?.site.id ?? "");
  const profiles = useZoneProfiles(project.id, site || null);
  const [zones, setZones] = useState<string[]>(
    wap?.zones.map((z) => z.id) ?? [],
  );
  const [eng, setEng] = useState(wap?.engagement.id ?? "");
  const [scopeEn, setScopeEn] = useState(wap?.scope_en ?? "");
  const [scopeAr, setScopeAr] = useState(wap?.scope_ar ?? "");
  const [wsp, setWsp] = useState(wap?.works_safety_plan_ref ?? "");
  const [from, setFrom] = useState(wap?.valid_from ?? todayInZone());
  const [to, setTo] = useState(wap?.valid_to ?? todayInZone());
  const [windows, setWindows] = useState<WindowIn[]>(
    wap?.windows.map((w) => ({
      start_local: hhmm(w.start_local),
      end_local: hhmm(w.end_local),
      weekdays: w.weekdays,
    })) ?? [
      { start_local: "23:00", end_local: "05:00", weekdays: [...WEEKDAYS] },
    ],
  );
  const [crew, setCrew] = useState<CrewRow[]>(
    wap?.crew
      .filter((c) => c.status !== "removed")
      .map((c) => ({
        worker_id: c.worker.id,
        worker_no: c.worker.worker_no,
        name: personName(c.worker, locale),
        crew_role: c.crew_role,
        escort_worker_id: c.escort_worker_id,
      })) ?? [],
  );
  const [vehicles, setVehicles] = useState<VehRow[]>(
    wap?.vehicles
      .filter((v) => v.status !== "removed")
      .map((v) => ({
        vehicle_id: v.vehicle.id,
        label: `${v.vehicle.vehicle_no} · ${v.vehicle.fleet_no}`,
        escort_vehicle_id: v.escort_vehicle_id,
        height_limited_to_m: v.height_limited_to_m ?? "",
      })) ?? [],
  );
  const [opRef, setOpRef] = useState(wap?.operator_permit_ref ?? "");
  const [ntms, setNtms] = useState<string[]>(wap?.linked_ntm_ids ?? []);
  const [obs, setObs] = useState<string[]>(wap?.linked_obs_ids ?? []);
  const [condEn, setCondEn] = useState(wap?.conditions_en ?? "");
  const [condAr, setCondAr] = useState(wap?.conditions_ar ?? "");
  const [picker, setPicker] = useState<Schemas["DeploymentRead"] | null>(null);
  const [vehPick, setVehPick] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const siteZones = opts.zones.filter(
    (z) => z.siteId === site && z.zoneType === "airside",
  );
  const permitZones = new Set(
    (profiles.data?.items ?? [])
      .filter((p) => p.access_permit_required)
      .map((p) => p.zone.id),
  );
  const supervisor = crew.find((c) => c.crew_role === "supervisor");
  // The supervisor may also escort (v0.3.1).
  const escorts = crew.filter(
    (c) => c.crew_role === "escort" || c.crew_role === "supervisor",
  );

  function addCrew(d: Schemas["DeploymentRead"] | null) {
    setPicker(null);
    if (!d || crew.some((c) => c.worker_id === d.worker_id)) return;
    setCrew((cs) => [
      ...cs,
      {
        worker_id: d.worker_id,
        worker_no: d.worker_no,
        name: personName(d, locale),
        crew_role: cs.some((c) => c.crew_role === "supervisor")
          ? "worker"
          : "supervisor",
        escort_worker_id: null,
      },
    ]);
  }
  async function save() {
    setFormError(null);
    if (
      !site ||
      !zones.length ||
      !eng ||
      !scopeEn.trim() ||
      !scopeAr.trim() ||
      !from ||
      !to ||
      !windows.length ||
      windows.some((w) => !w.weekdays.length)
    ) {
      setFormError(tv("required"));
      return;
    }
    if (!supervisor) {
      setFormError(t("supervisorRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    const common = {
      zone_ids: zones,
      supervisor_worker_id: supervisor.worker_id,
      scope_en: scopeEn.trim(),
      scope_ar: scopeAr.trim(),
      works_safety_plan_ref: wsp.trim() || null,
      valid_from: from,
      valid_to: to,
      windows: windows.map((w) => ({
        start_local: w.start_local,
        end_local: w.end_local,
        weekdays: w.weekdays,
      })),
      crew: crew.map((c) => ({
        worker_id: c.worker_id,
        crew_role: c.crew_role,
        escort_worker_id: c.escort_worker_id,
      })),
      vehicles: vehicles.map((v) => ({
        vehicle_id: v.vehicle_id,
        escort_vehicle_id: v.escort_vehicle_id,
        height_limited_to_m: v.height_limited_to_m || null,
      })),
      operator_permit_ref: opRef.trim() || null,
      linked_ntm_ids: ntms,
      linked_obs_ids: obs,
      conditions_en: condEn.trim() || null,
      conditions_ar: condAr.trim() || null,
    };
    try {
      const w = wap
        ? await unwrap(
            api.PATCH("/api/v1/waps/{wap_id}", {
              params: { path: { wap_id: wap.id } },
              body: common,
            }),
          )
        : await unwrap(
            api.POST("/api/v1/projects/{project_id}/waps", {
              params: { path: { project_id: project.id } },
              body: { ...common, site_id: site, engagement_id: eng },
            }),
          );
      qc.setQueryData(ak.wap(w.id), w);
      await qc.invalidateQueries({ queryKey: ["waps"] });
      await qc.invalidateQueries({ queryKey: ["wap-board"] });
      warn(w.warnings);
      toast.success(tc("saved"));
      router.push(`/waps/${w.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="flex max-w-4xl flex-col gap-6"
      noValidate
      autoComplete="off"
      data-testid="wap-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <FormSection title={t("where")}>
        <FormField id="wf-site" label={tc("site")} required>
          <Select
            value={site}
            disabled={Boolean(wap)}
            onChange={(e) => {
              setSite(e.target.value);
              setZones([]);
            }}
          >
            <option value="">{tc("select")}</option>
            {opts.sites.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="wf-eng" label={tc("contractor")} required>
          <Select
            value={eng}
            disabled={Boolean(wap)}
            onChange={(e) => setEng(e.target.value)}
          >
            <option value="">{tc("select")}</option>
            {opts.engagements
              .filter((e) => !site || e.siteIds.includes(site))
              .map((e) => (
                <option key={e.value} value={e.value}>
                  {e.label}
                </option>
              ))}
          </Select>
        </FormField>
        <div className="sm:col-span-2">
          <MultiSelect
            id="wf-zones"
            label={t("fields.zones")}
            options={siteZones.map((z) => ({
              value: z.value,
              label: z.label,
              hint: permitZones.has(z.value) ? t("permitRequired") : undefined,
            }))}
            value={zones}
            onChange={setZones}
            className="lg:w-full"
          />
        </div>
        <FormField
          id="wf-wsp"
          label={t("fields.works_safety_plan_ref")}
          hint={t("wspHint")}
        >
          <Input
            className="ltr"
            maxLength={40}
            value={wsp}
            onChange={(e) => setWsp(e.target.value)}
          />
        </FormField>
        <FormField id="wf-op" label={t("fields.operator_permit_ref")}>
          <Input
            className="ltr"
            maxLength={40}
            value={opRef}
            onChange={(e) => setOpRef(e.target.value)}
          />
        </FormField>
      </FormSection>
      <FormSection title={t("what")}>
        <FormField
          id="wf-scope-en"
          label={t("fields.scope_en")}
          required
          className="sm:col-span-2"
        >
          <Textarea
            dir="ltr"
            rows={2}
            maxLength={500}
            value={scopeEn}
            onChange={(e) => setScopeEn(e.target.value)}
          />
        </FormField>
        <FormField
          id="wf-scope-ar"
          label={t("fields.scope_ar")}
          required
          className="sm:col-span-2"
        >
          <Textarea
            dir="rtl"
            lang="ar"
            rows={2}
            maxLength={500}
            value={scopeAr}
            onChange={(e) => setScopeAr(e.target.value)}
          />
        </FormField>
      </FormSection>
      <FormSection title={t("when")} description={t("whenHint")}>
        <FormField id="wf-from" label={t("fields.valid_from")} required>
          <Input
            type="date"
            min={wap ? undefined : todayInZone()}
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </FormField>
        <FormField id="wf-to" label={t("fields.valid_to")} required>
          <Input
            type="date"
            min={from}
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </FormField>
        <div className="sm:col-span-2">
          <WindowsEditor value={windows} onChange={setWindows} />
        </div>
      </FormSection>
      <FormSection
        title={t("crewTitle", { n: crew.length })}
        description={t("crewHint")}
      >
        <div className="sm:col-span-2">
          <DeploymentPicker
            id="wf-crew-add"
            projectId={project.id}
            value={picker}
            onChange={addCrew}
            status={["mobilised"]}
            label={t("addCrew")}
          />
        </div>
        <ul
          className="flex flex-col gap-2 sm:col-span-2"
          data-testid="crew-editor"
        >
          {crew.map((c, i) => (
            <li
              key={c.worker_id}
              className="flex flex-wrap items-end gap-2 rounded-lg border p-2"
              data-testid="crew-row"
            >
              <span className="min-w-40 flex-1 text-sm">
                <Code>{c.worker_no}</Code> {c.name}
              </span>
              <Select
                aria-label={t("role")}
                className="w-36"
                value={c.crew_role}
                onChange={(e) =>
                  setCrew((cs) =>
                    cs.map((x, j) =>
                      j === i
                        ? {
                            ...x,
                            crew_role: e.target.value as Schemas["CrewRole"],
                          }
                        : x,
                    ),
                  )
                }
                data-testid={`crew-role-${i}`}
              >
                {CREW_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {te(`crewRole.${r}`)}
                  </option>
                ))}
              </Select>
              <Select
                aria-label={t("escort")}
                className="w-48"
                value={c.escort_worker_id ?? ""}
                onChange={(e) =>
                  setCrew((cs) =>
                    cs.map((x, j) =>
                      j === i
                        ? { ...x, escort_worker_id: e.target.value || null }
                        : x,
                    ),
                  )
                }
              >
                <option value="">{t("noEscort")}</option>
                {escorts
                  .filter((e) => e.worker_id !== c.worker_id)
                  .map((e) => (
                    <option key={e.worker_id} value={e.worker_id}>
                      {e.worker_no}
                    </option>
                  ))}
              </Select>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={tc("remove")}
                onClick={() => setCrew((cs) => cs.filter((_, j) => j !== i))}
              >
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      </FormSection>
      <FormSection
        title={t("vehiclesTitle", { n: vehicles.length })}
        description={t("vehiclesHint")}
      >
        <div className="flex items-end gap-2 sm:col-span-2">
          <FormField id="wf-veh" label={t("addVehicle")} className="flex-1">
            <VehicleSelect
              id="wf-veh-sel"
              projectId={project.id}
              value={vehPick}
              engagementId={eng || null}
              onChange={(id, v) => {
                setVehPick("");
                if (v && !vehicles.some((x) => x.vehicle_id === id))
                  setVehicles((vs) => [
                    ...vs,
                    {
                      vehicle_id: id,
                      label: `${v.vehicle_no} · ${v.fleet_no}`,
                      escort_vehicle_id: null,
                      height_limited_to_m: "",
                    },
                  ]);
              }}
              placeholder={tc("select")}
            />
          </FormField>
        </div>
        <ul className="flex flex-col gap-2 sm:col-span-2">
          {vehicles.map((v, i) => (
            <li
              key={v.vehicle_id}
              className="flex flex-wrap items-end gap-2 rounded-lg border p-2"
              data-testid="vehicle-row-edit"
            >
              <span className="ltr min-w-40 flex-1 text-sm">{v.label}</span>
              <Select
                aria-label={t("escortVehicle")}
                className="w-48"
                value={v.escort_vehicle_id ?? ""}
                onChange={(e) =>
                  setVehicles((vs) =>
                    vs.map((x, j) =>
                      j === i
                        ? { ...x, escort_vehicle_id: e.target.value || null }
                        : x,
                    ),
                  )
                }
              >
                <option value="">{t("noEscortVehicle")}</option>
                {vehicles
                  .filter((x) => x.vehicle_id !== v.vehicle_id)
                  .map((x) => (
                    <option key={x.vehicle_id} value={x.vehicle_id}>
                      {x.label}
                    </option>
                  ))}
              </Select>
              <Input
                aria-label={t("heightLimit")}
                placeholder={t("heightLimit")}
                type="number"
                step="0.01"
                className="ltr w-36"
                value={v.height_limited_to_m}
                onChange={(e) =>
                  setVehicles((vs) =>
                    vs.map((x, j) =>
                      j === i
                        ? { ...x, height_limited_to_m: e.target.value }
                        : x,
                    ),
                  )
                }
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={tc("remove")}
                onClick={() =>
                  setVehicles((vs) => vs.filter((_, j) => j !== i))
                }
              >
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      </FormSection>
      <FormSection title={t("links")} description={t("linksHint")}>
        <MultiSelect
          id="wf-ntm"
          label={t("linkedNotams")}
          options={links.notams}
          value={ntms}
          onChange={setNtms}
          className="lg:w-full"
        />
        <MultiSelect
          id="wf-obs"
          label={t("linkedObstacles")}
          options={links.obstacles}
          value={obs}
          onChange={setObs}
          className="lg:w-full"
        />
        <FormField
          id="wf-cond-en"
          label={t("fields.conditions_en")}
          className="sm:col-span-2"
        >
          <Textarea
            dir="ltr"
            rows={2}
            maxLength={1000}
            value={condEn}
            onChange={(e) => setCondEn(e.target.value)}
          />
        </FormField>
        <FormField
          id="wf-cond-ar"
          label={t("fields.conditions_ar")}
          className="sm:col-span-2"
        >
          <Textarea
            dir="rtl"
            rows={2}
            maxLength={1000}
            value={condAr}
            onChange={(e) => setCondAr(e.target.value)}
          />
        </FormField>
      </FormSection>
      {formError ? <Alert tone="danger">{formError}</Alert> : null}
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-wap">
          {busy ? tc("saving") : tc("save")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

/* ───────────────────────────── Detail ───────────────────────────── */

type WapStep =
  | "submit"
  | "return"
  | "approve"
  | "reject"
  | "suspend"
  | "resume"
  | "close"
  | "cancel"
  | "revision"
  | "crew"
  | "vehicle";

export function WapDetail({ id }: { id: string }) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const name = useLocalizedName();
  const q = useWap(id);
  const qc = useQueryClient();
  const [step, setStep] = useState<WapStep | null>(null);
  const { date, dateTime } = useFormatters(q.data?.project_id);
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const w = q.data;
  const pid = w.project_id;
  const edit = canWrite(me, "wap.edit", pid);
  const approve = canWrite(me, "wap.approve", pid);
  const suspend = canWrite(me, "wap.suspend", pid);
  const close = canWrite(me, "wap.close", pid);
  const showNames = can(me, "worker.view", pid);
  const s = w.status;
  const steps: {
    k: WapStep;
    show: boolean;
    destructive?: boolean;
    primary?: boolean;
  }[] = [
    { k: "submit", show: s === "draft" && edit, primary: true },
    { k: "return", show: s === "submitted" && approve },
    { k: "approve", show: s === "submitted" && approve, primary: true },
    { k: "reject", show: s === "submitted" && approve, destructive: true },
    { k: "suspend", show: s === "active" && suspend, destructive: true },
    { k: "resume", show: s === "suspended" && approve, primary: true },
    {
      k: "revision",
      show:
        (s === "active" || s === "approved") && edit && !w.pending_revision_id,
    },
    { k: "close", show: (s === "active" || s === "suspended") && close },
    {
      k: "cancel",
      show: (s === "draft" || s === "submitted" || s === "approved") && close,
      destructive: true,
    },
  ];
  async function refresh(u: Wap) {
    qc.setQueryData(ak.wap(w.id), u);
    for (const k of ["waps", "wap-board"])
      await qc.invalidateQueries({ queryKey: [k] });
  }
  async function transition(body: Schemas["WapTransitionRequest"]) {
    const u = await unwrap(
      api.POST("/api/v1/waps/{wap_id}/transitions", {
        params: { path: { wap_id: w.id } },
        body,
      }),
    );
    await refresh(u);
    toast.success(te(`wapStatus.${body.to_status}`));
  }
  const crewEditable =
    edit &&
    ["draft", "submitted", "approved", "active", "suspended"].includes(s);
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs
          items={[{ label: t("title"), href: "/waps" }, { label: w.wap_no }]}
        />
        <PageHeader
          title={`${w.wap_no}${w.revision_no > 0 ? ` · r${w.revision_no}` : ""}`}
          description={locale === "ar" ? w.scope_ar : w.scope_en}
          actions={
            <>
              <span data-testid="wap-status" data-status={s}>
                <StatusBadge status={s} label={te(`wapStatus.${s}`)} />
              </span>
              {s === "draft" && edit ? (
                <Button variant="outline" asChild>
                  <Link href={`/waps/${w.id}/edit`} data-testid="edit-wap">
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Link>
                </Button>
              ) : null}
              {["approved", "active", "suspended"].includes(s) ? (
                <Button variant="outline" asChild>
                  <Link href={`/waps/${w.id}/print`} data-testid="print-wap">
                    <Printer aria-hidden />
                    {tc("print")}
                  </Link>
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {steps.some((x) => x.show) ? (
        <div className="flex flex-wrap gap-2" data-testid="wap-actions">
          {steps
            .filter((x) => x.show)
            .map((x) => (
              <Button
                key={x.k}
                variant={
                  x.destructive
                    ? "destructive"
                    : x.primary
                      ? "default"
                      : "outline"
                }
                onClick={() => setStep(x.k)}
                data-testid={`wap-${x.k}`}
              >
                {x.k === "revision" ? <GitBranch aria-hidden /> : null}
                {t(`step.${x.k}`)}
              </Button>
            ))}
        </div>
      ) : null}
      {s === "suspended" && w.suspension_reason ? (
        <Alert tone="danger" data-testid="suspension-reason">
          {t("suspendedBecause", {
            reason: te(`credentialReason.${w.suspension_reason}`),
          })}
        </Alert>
      ) : null}
      {s === "approved" && w.blockers.length ? (
        <Alert tone="warning">{t("approvedBlocked")}</Alert>
      ) : null}
      {w.pending_revision_id ? (
        <Alert tone="info">
          {t("pendingRevision")}{" "}
          <Link
            href={`/waps/${w.pending_revision_id}`}
            className="font-medium underline"
          >
            {t("openRevision")}
          </Link>
        </Alert>
      ) : null}
      {w.revision_of_id ? (
        <Alert tone="info">
          {t("isRevision")}{" "}
          <Link
            href={`/waps/${w.revision_of_id}`}
            className="font-medium underline"
          >
            {t("openOriginal")}
          </Link>
        </Alert>
      ) : null}
      <ApiWarnings warnings={w.warnings} />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("blockersTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Blockers blockers={w.blockers} />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem
              label={tc("site")}
            >{`${w.site.code} — ${name(w.site.name_en, w.site.name_ar)}`}</FieldItem>
            <FieldItem label={t("fields.zones")}>
              {w.zones.map((z) => (
                <span key={z.id} className="me-2">
                  <Code>{z.code}</Code> {name(z.name_en, z.name_ar)}
                </span>
              ))}
            </FieldItem>
            <FieldItem label={tc("contractor")}>
              {w.engagement.short_code}
            </FieldItem>
            {/* The API sends no supervisor without worker access (v0.3.1). */}
            {w.supervisor ? (
              <FieldItem
                label={t("fields.supervisor")}
              >{`${w.supervisor.worker_no} ${personName(w.supervisor, locale)}`}</FieldItem>
            ) : null}
            <FieldItem label={t("fields.dates")}>
              {date(w.valid_from)} – {date(w.valid_to)}
            </FieldItem>
            <FieldItem label={t("fields.windows")}>
              <WindowsText windows={w.windows} />
            </FieldItem>
            <FieldItem label={t("currentWindow")}>
              {w.current_window
                ? `${dateTime(w.current_window.start_utc)} – ${dateTime(w.current_window.end_utc)}`
                : "—"}
            </FieldItem>
            <FieldItem label={t("nextWindow")}>
              {w.next_window
                ? `${dateTime(w.next_window.start_utc)} – ${dateTime(w.next_window.end_utc)}`
                : "—"}
            </FieldItem>
            <FieldItem label={t("fields.works_safety_plan_ref")} ltr>
              {w.works_safety_plan_ref ?? "—"}
            </FieldItem>
            <FieldItem label={t("fields.operator_permit_ref")} ltr>
              {w.operator_permit_ref ?? "—"}
            </FieldItem>
            <FieldItem label={t("linkedNotams")}>
              {w.linked_ntm_ids.length
                ? w.linked_ntm_ids.map((n, i) => (
                    <Link
                      key={n}
                      href={`/notams/${n}`}
                      className="me-2 text-primary hover:underline"
                    >
                      NOTAM {i + 1}
                    </Link>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={t("linkedObstacles")}>
              {w.linked_obs_ids.length
                ? w.linked_obs_ids.map((n, i) => (
                    <Link
                      key={n}
                      href={`/obstacle-clearances/${n}`}
                      className="me-2 text-primary hover:underline"
                    >
                      OBS {i + 1}
                    </Link>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={t("fodHandback")}>
              {w.fod_handback_required ? tc("yes") : tc("no")}
            </FieldItem>
            <FieldItem label={t("fodCheck")}>
              {w.fod_check
                ? `${te(`fodResult.${w.fod_check.result}`)} · ${dateTime(w.fod_check.checked_at)}`
                : "—"}
            </FieldItem>
            <FieldItem label={t("fields.requested_by")}>
              {name(w.requested_by.full_name_en, w.requested_by.full_name_ar)}
            </FieldItem>
            <FieldItem label={t("fields.approved_by")}>
              {w.approved_by
                ? `${name(w.approved_by.full_name_en, w.approved_by.full_name_ar)} · ${dateTime(w.approved_at)}`
                : "—"}
            </FieldItem>
            {w.conditions_en || w.conditions_ar ? (
              <FieldItem label={t("fields.conditions")} wide>
                {locale === "ar"
                  ? (w.conditions_ar ?? w.conditions_en)
                  : (w.conditions_en ?? w.conditions_ar)}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">
            {t("crewTitle", { n: w.crew_count })}
          </CardTitle>
          {crewEditable && showNames ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setStep("crew")}
              data-testid="add-crew"
            >
              <UserPlus aria-hidden />
              {t("addCrew")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {!showNames ? (
            <p
              className="text-sm text-muted-foreground"
              data-testid="crew-hidden"
            >
              {t("crewHidden", { n: w.crew_count })}
            </p>
          ) : (
            <ul className="flex flex-col divide-y" data-testid="crew-list">
              {w.crew.map((c) => (
                <li
                  key={c.worker.id}
                  className="flex flex-wrap items-center gap-2 py-2 text-sm"
                  data-testid="crew-member"
                  data-status={c.status}
                >
                  <Link
                    href={`/workers/${c.worker.id}`}
                    className="hover:underline"
                  >
                    <Code>{c.worker.worker_no}</Code>{" "}
                    {personName(c.worker, locale)}
                  </Link>
                  <span className="text-muted-foreground">
                    {te(`crewRole.${c.crew_role}`)}
                  </span>
                  {c.escorted ? (
                    <StatusBadge status="warn" label={t("escorted")} />
                  ) : null}
                  <StatusBadge
                    status={c.status}
                    label={te(`crewStatus.${c.status}`)}
                  />
                  {c.exclusion_reasons.length ? (
                    <ReasonChips codes={c.exclusion_reasons} />
                  ) : null}
                  {crewEditable && c.status !== "removed" ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="ms-auto"
                      onClick={async () => {
                        try {
                          const u = await unwrap(
                            api.DELETE(
                              "/api/v1/waps/{wap_id}/crew/{worker_id}",
                              {
                                params: {
                                  path: {
                                    wap_id: w.id,
                                    worker_id: c.worker.id,
                                  },
                                },
                              },
                            ),
                          );
                          await refresh(u);
                        } catch (e) {
                          toast.error(
                            e instanceof Error ? e.message : String(e),
                          );
                        }
                      }}
                    >
                      {tc("remove")}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">
            {t("vehiclesTitle", { n: w.vehicle_count })}
          </CardTitle>
          {crewEditable ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setStep("vehicle")}
              data-testid="add-vehicle"
            >
              <Plus aria-hidden />
              {t("addVehicle")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {w.vehicles.length === 0 ? (
            <p className="text-sm text-muted-foreground">—</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {w.vehicles.map((v) => (
                <li
                  key={v.vehicle.id}
                  className="flex flex-wrap items-center gap-2 py-2 text-sm"
                  data-testid="wap-vehicle"
                  data-status={v.status}
                >
                  <Link
                    href={`/vehicles/${v.vehicle.id}`}
                    className="ltr hover:underline"
                  >
                    <Code>{v.vehicle.vehicle_no}</Code> {v.vehicle.fleet_no}
                  </Link>
                  <span className="text-muted-foreground">
                    {v.avp_no
                      ? `AVP ${v.avp_no}`
                      : v.escort_vehicle_id
                        ? t("escortedVehicle")
                        : t("noAvp")}
                  </span>
                  {v.height_limited_to_m ? (
                    <span className="ltr text-xs">
                      ≤ {v.height_limited_to_m} m
                    </span>
                  ) : null}
                  <StatusBadge
                    status={v.status}
                    label={te(`crewStatus.${v.status}`)}
                  />
                  {v.exclusion_reasons.length ? (
                    <ReasonChips codes={v.exclusion_reasons} />
                  ) : null}
                  {crewEditable && v.status !== "removed" ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="ms-auto"
                      onClick={async () => {
                        try {
                          const u = await unwrap(
                            api.DELETE(
                              "/api/v1/waps/{wap_id}/vehicles/{vehicle_id}",
                              {
                                params: {
                                  path: {
                                    wap_id: w.id,
                                    vehicle_id: v.vehicle.id,
                                  },
                                },
                              },
                            ),
                          );
                          await refresh(u);
                        } catch (e) {
                          toast.error(
                            e instanceof Error ? e.message : String(e),
                          );
                        }
                      }}
                    >
                      {tc("remove")}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <HistoryPanel entityType="wap" entityId={w.id} />
      {step === "submit" ? (
        <StepDialog
          title={t("step.submit")}
          description={t("help.submit")}
          confirmLabel={t("step.submit")}
          onConfirm={() => transition({ to_status: "submitted" })}
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "approve" ? (
        <StepDialog
          title={t("step.approve")}
          description={t("help.approve")}
          warning={w.blockers.length ? t("approveWithBlockers") : undefined}
          confirmLabel={t("step.approve")}
          onConfirm={() => transition({ to_status: "approved" })}
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "return" || step === "reject" || step === "cancel" ? (
        <WapReasonDialog
          title={t(`step.${step}`)}
          destructive={step !== "return"}
          onConfirm={(r) =>
            transition({
              to_status:
                step === "return"
                  ? "draft"
                  : step === "reject"
                    ? "rejected"
                    : "cancelled",
              reason: r,
            })
          }
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "suspend" ? (
        <SuspendWapDialog
          onConfirm={(code, r) =>
            transition({ to_status: "suspended", reason_code: code, reason: r })
          }
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "resume" || step === "close" ? (
        <FodDialog
          wap={w}
          mode={step}
          onConfirm={(fod) =>
            transition({
              to_status: step === "resume" ? "active" : "closed",
              fod_check: fod,
            })
          }
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "revision" ? (
        <RevisionDialog wap={w} onClose={() => setStep(null)} />
      ) : null}
      {step === "crew" ? (
        <AddCrewDialog
          wap={w}
          onSaved={refresh}
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "vehicle" ? (
        <AddVehicleDialog
          wap={w}
          onSaved={refresh}
          onClose={() => setStep(null)}
        />
      ) : null}
    </div>
  );
}

function WapReasonDialog({
  title,
  destructive,
  onConfirm,
  onClose,
}: {
  title: string;
  destructive?: boolean;
  onConfirm: (r: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const tc = useTranslations("common");
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={title}
      destructive={destructive}
      confirmLabel={title}
      disabled={reason.trim().length < 3}
      onConfirm={() => onConfirm(reason.trim())}
      onClose={onClose}
    >
      <FormField id="wr-reason" label={tc("reason")} required>
        <Textarea
          rows={3}
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </FormField>
    </StepDialog>
  );
}

function SuspendWapDialog({
  onConfirm,
  onClose,
}: {
  onConfirm: (code: Schemas["CredentialReason"], r: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [code, setCode] = useState<Schemas["CredentialReason"]>("violation");
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("step.suspend")}
      description={t("help.suspend")}
      destructive
      confirmLabel={t("step.suspend")}
      disabled={reason.trim().length < 10}
      onConfirm={() => onConfirm(code, reason.trim())}
      onClose={onClose}
    >
      <FormField id="ws-code" label={t("reasonCode")} required>
        <Select
          value={code}
          onChange={(e) =>
            setCode(e.target.value as Schemas["CredentialReason"])
          }
        >
          {CREDENTIAL_REASONS.filter((r) =>
            [
              "violation",
              "investigation_pending",
              "security_request",
              "ops_suspension",
              "other",
            ].includes(r),
          ).map((r) => (
            <option key={r} value={r}>
              {te(`credentialReason.${r}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="ws-reason" label={tc("reason")} required hint={t("min10")}>
        <Textarea
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </FormField>
    </StepDialog>
  );
}

function FodDialog({
  wap,
  mode,
  onConfirm,
  onClose,
}: {
  wap: Wap;
  mode: "resume" | "close";
  onConfirm: (fod: Schemas["FodCheckInput"] | null) => Promise<unknown>;
  onClose: () => void;
}) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const [at, setAt] = useState(() => utcToZonedInput(new Date().toISOString()));
  const [result, setResult] = useState<Schemas["FodCheckResult"]>("clear");
  const [by, setBy] = useState("");
  const need = wap.fod_handback_required;
  return (
    <StepDialog
      title={t(`step.${mode}`)}
      description={need ? t("fodHint") : t(`help.${mode}`)}
      confirmLabel={t(`step.${mode}`)}
      testId="fod-confirm"
      disabled={need && result !== "clear"}
      onConfirm={() =>
        onConfirm(
          need
            ? {
                checked_at: zonedInputToUtc(at),
                result,
                checked_by_worker_id: by || null,
              }
            : null,
        )
      }
      onClose={onClose}
    >
      {need ? (
        <>
          <FormField id="fod-at" label={t("fodCheckedAt")} required>
            <Input
              type="datetime-local"
              value={at}
              onChange={(e) => setAt(e.target.value)}
            />
          </FormField>
          <FormField id="fod-by" label={t("fodCheckedBy")}>
            <Select value={by} onChange={(e) => setBy(e.target.value)}>
              <option value="">{t("fodByMe")}</option>
              {wap.crew
                .filter((c) => c.status === "included")
                .map((c) => (
                  <option key={c.worker.id} value={c.worker.id}>
                    {c.worker.worker_no}
                  </option>
                ))}
            </Select>
          </FormField>
          <FormField id="fod-result" label={t("fodResult")} required>
            <Select
              value={result}
              onChange={(e) =>
                setResult(e.target.value as Schemas["FodCheckResult"])
              }
              data-testid="fod-result"
            >
              {(["clear", "not_clear"] as const).map((r) => (
                <option key={r} value={r}>
                  {te(`fodResult.${r}`)}
                </option>
              ))}
            </Select>
          </FormField>
          {result !== "clear" ? (
            <Alert tone="danger">{t("fodNotClear")}</Alert>
          ) : null}
        </>
      ) : null}
    </StepDialog>
  );
}

function RevisionDialog({ wap, onClose }: { wap: Wap; onClose: () => void }) {
  const t = useTranslations("waps");
  const router = useRouter();
  const qc = useQueryClient();
  const opts = useProjectOptions(wap.project_id);
  const links = useLinkOptions(wap.project_id);
  const [zones, setZones] = useState(wap.zones.map((z) => z.id));
  const [from, setFrom] = useState(wap.valid_from);
  const [to, setTo] = useState(wap.valid_to);
  const [windows, setWindows] = useState<WindowIn[]>(
    wap.windows.map((w) => ({
      start_local: hhmm(w.start_local),
      end_local: hhmm(w.end_local),
      weekdays: w.weekdays,
    })),
  );
  const [ntms, setNtms] = useState(wap.linked_ntm_ids);
  const [obs, setObs] = useState(wap.linked_obs_ids);
  const [reason, setReason] = useState("");
  const siteZones = opts.zones.filter(
    (z) => z.siteId === wap.site.id && z.zoneType === "airside",
  );
  return (
    <StepDialog
      title={t("step.revision")}
      description={t("help.revision")}
      confirmLabel={t("step.revision")}
      testId="revision-confirm"
      wide
      disabled={reason.trim().length < 10}
      onConfirm={async () => {
        const r = await unwrap(
          api.POST("/api/v1/waps/{wap_id}/revisions", {
            params: { path: { wap_id: wap.id } },
            body: {
              zone_ids: zones,
              valid_from: from,
              valid_to: to,
              windows,
              linked_ntm_ids: ntms,
              linked_obs_ids: obs,
              reason: reason.trim(),
            },
          }),
        );
        qc.setQueryData(ak.wap(r.id), r);
        for (const k of ["waps", "wap", "wap-board"])
          await qc.invalidateQueries({ queryKey: [k] });
        router.push(`/waps/${r.id}`);
      }}
      onClose={onClose}
    >
      <MultiSelect
        id="rv-zones"
        label={t("fields.zones")}
        options={siteZones.map((z) => ({ value: z.value, label: z.label }))}
        value={zones}
        onChange={setZones}
        className="lg:w-full"
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="rv-from" label={t("fields.valid_from")}>
          <Input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </FormField>
        <FormField id="rv-to" label={t("fields.valid_to")}>
          <Input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </FormField>
      </div>
      <WindowsEditor value={windows} onChange={setWindows} />
      <MultiSelect
        id="rv-ntm"
        label={t("linkedNotams")}
        options={links.notams}
        value={ntms}
        onChange={setNtms}
        className="lg:w-full"
      />
      <MultiSelect
        id="rv-obs"
        label={t("linkedObstacles")}
        options={links.obstacles}
        value={obs}
        onChange={setObs}
        className="lg:w-full"
      />
      <FormField
        id="rv-reason"
        label={t("revisionReason")}
        required
        hint={t("min10")}
      >
        <Textarea
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </FormField>
    </StepDialog>
  );
}

function AddCrewDialog({
  wap,
  onSaved,
  onClose,
}: {
  wap: Wap;
  onSaved: (w: Wap) => Promise<void>;
  onClose: () => void;
}) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const [dep, setDep] = useState<Schemas["DeploymentRead"] | null>(null);
  const [role, setRole] = useState<Schemas["CrewRole"]>("worker");
  const [escort, setEscort] = useState("");
  const escorts = wap.crew.filter(
    (c) =>
      (c.crew_role === "escort" || c.crew_role === "supervisor") &&
      c.status === "included",
  );
  return (
    <StepDialog
      title={t("addCrew")}
      description={t("addCrewHint")}
      confirmLabel={t("addCrew")}
      testId="add-crew-confirm"
      disabled={!dep}
      onConfirm={async () => {
        const u = await unwrap(
          api.POST("/api/v1/waps/{wap_id}/crew", {
            params: { path: { wap_id: wap.id } },
            body: {
              worker_id: dep!.worker_id,
              crew_role: role,
              escort_worker_id: escort || null,
            },
          }),
        );
        await onSaved(u);
      }}
      onClose={onClose}
    >
      <DeploymentPicker
        id="ac-worker"
        projectId={wap.project_id}
        value={dep}
        onChange={setDep}
        status={["mobilised"]}
        label={t("worker")}
        required
      />
      <FormField id="ac-role" label={t("role")}>
        <Select
          value={role}
          onChange={(e) => setRole(e.target.value as Schemas["CrewRole"])}
        >
          {CREW_ROLES.map((r) => (
            <option key={r} value={r}>
              {te(`crewRole.${r}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="ac-escort" label={t("escort")}>
        <Select value={escort} onChange={(e) => setEscort(e.target.value)}>
          <option value="">{t("noEscort")}</option>
          {escorts.map((e) => (
            <option key={e.worker.id} value={e.worker.id}>
              {e.worker.worker_no}
            </option>
          ))}
        </Select>
      </FormField>
    </StepDialog>
  );
}

function AddVehicleDialog({
  wap,
  onSaved,
  onClose,
}: {
  wap: Wap;
  onSaved: (w: Wap) => Promise<void>;
  onClose: () => void;
}) {
  const t = useTranslations("waps");
  const tc = useTranslations("common");
  const [vid, setVid] = useState("");
  const [escort, setEscort] = useState("");
  const [limit, setLimit] = useState("");
  return (
    <StepDialog
      title={t("addVehicle")}
      confirmLabel={t("addVehicle")}
      testId="add-vehicle-confirm"
      disabled={!vid}
      onConfirm={async () => {
        const u = await unwrap(
          api.POST("/api/v1/waps/{wap_id}/vehicles", {
            params: { path: { wap_id: wap.id } },
            body: {
              vehicle_id: vid,
              escort_vehicle_id: escort || null,
              height_limited_to_m: limit || null,
            },
          }),
        );
        await onSaved(u);
      }}
      onClose={onClose}
    >
      <FormField id="av-vehicle" label={t("vehicle")} required>
        <VehicleSelect
          id="av-vehicle-sel"
          projectId={wap.project_id}
          value={vid}
          onChange={(v) => setVid(v)}
          engagementId={wap.engagement.id}
          placeholder={tc("select")}
        />
      </FormField>
      <FormField id="av-escort" label={t("escortVehicle")}>
        <Select value={escort} onChange={(e) => setEscort(e.target.value)}>
          <option value="">{t("noEscortVehicle")}</option>
          {wap.vehicles
            .filter((v) => v.status === "included")
            .map((v) => (
              <option key={v.vehicle.id} value={v.vehicle.id}>
                {v.vehicle.vehicle_no}
              </option>
            ))}
        </Select>
      </FormField>
      <FormField
        id="av-limit"
        label={t("heightLimit")}
        hint={t("heightLimitHint")}
      >
        <Input
          type="number"
          step="0.01"
          className="ltr"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
        />
      </FormField>
    </StepDialog>
  );
}

/* ───────────────────────────── Board ───────────────────────────── */

export function WapBoardPage() {
  return (
    <ProjectGate>
      {(p) => <AirportOnly project={p}>{<WapBoard project={p} />}</AirportOnly>}
    </ProjectGate>
  );
}

function WapBoard({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const name = useLocalizedName();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const on = s.get("on") || todayInZone();
  const site = s.get("site_id") || null;
  const q = useWapBoard(project.id, { on, site_id: site });
  const zones = q.data?.zones ?? [];
  const { dateTime } = useFormatters(project.id);
  return (
    <div>
      <PageHeader title={t("board")} description={t("boardHint")} />
      <WapSubNav />
      <ListToolbar>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="wb-on" className="text-sm font-medium">
            {tc("date")}
          </label>
          <Input
            id="wb-on"
            type="date"
            value={on}
            onChange={(e) => s.set({ on: e.target.value })}
            className="w-44"
          />
        </div>
        <SelectFilter
          id="wb-site"
          label={tc("site")}
          value={site ?? ""}
          onChange={(v) => s.set({ site_id: v })}
          options={opts.sites.map((x) => ({ value: x.value, label: x.label }))}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : zones.length === 0 ? (
        <EmptyState message={t("boardEmpty")} />
      ) : (
        <div
          className="grid gap-4 md:grid-cols-2 xl:grid-cols-3"
          data-testid="wap-board"
        >
          {zones.map((z) => (
            <Card
              key={z.zone.id}
              data-testid="board-zone"
              data-zone={z.zone.code}
              className={
                z.ops_suspension_active ? "border-destructive" : undefined
              }
            >
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between gap-2 text-base">
                  <span>
                    <Code>{z.zone.code}</Code>{" "}
                    {name(z.zone.name_en, z.zone.name_ar)}
                  </span>
                  {z.ops_suspension_active ? (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-destructive">
                      <CloudFog aria-hidden className="size-4" />
                      {t("opsActive")}
                    </span>
                  ) : null}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {z.waps.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    {t("noWapsZone")}
                  </p>
                ) : (
                  z.waps.map((w) => (
                    <Link
                      key={w.id}
                      href={`/waps/${w.id}`}
                      className={cn(
                        "flex flex-col gap-1 rounded-lg border p-2.5 hover:bg-accent",
                        // Working now: a solid start bar so live works stand out on a wall screen.
                        w.current_window && "border-s-4 border-s-success",
                        w.blockers.length > 0 && "border-s-4 border-s-warning",
                      )}
                      data-testid="board-wap"
                      data-status={w.status}
                    >
                      <span className="flex flex-wrap items-center justify-between gap-2">
                        <span className="ltr font-medium">{w.wap_no}</span>
                        <StatusBadge
                          status={w.status}
                          label={te(`wapStatus.${w.status}`)}
                        />
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {w.engagement.short_code} ·{" "}
                        {locale === "ar" ? w.scope_ar : w.scope_en}
                      </span>
                      <span className={cn("flex items-start gap-1.5 text-xs", w.current_window && "font-semibold text-success")}>
                        {w.current_window ? (
                          <span aria-hidden className="relative mt-1 flex size-2 shrink-0">
                            <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
                            <span className="relative inline-flex size-2 rounded-full bg-success" />
                          </span>
                        ) : (
                          <Clock aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                        )}
                        <span>
                        {w.current_window
                          ? t("nowWindow", {
                              to: dateTime(w.current_window.end_utc),
                            })
                          : w.next_window
                            ? t("nextAt", {
                                at: dateTime(w.next_window.start_utc),
                              })
                            : t("noWindowToday")}
                        </span>
                      </span>
                      <span className="text-xs">
                        {t("crewN", { n: w.crew_count })} ·{" "}
                        {t("vehiclesN", { n: w.vehicle_count })}
                      </span>
                      {w.blockers.length ? (
                        <span className="flex flex-wrap gap-1" data-testid="board-blockers">
                          {w.blockers.map((b, i) => (
                            <Badge key={`${b.code}-${i}`} tone="warning">
                              <TriangleAlert aria-hidden />
                              {te(`wapBlocker.${b.code}`)}
                            </Badge>
                          ))}
                        </span>
                      ) : null}
                    </Link>
                  ))
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

/* ───────────────────────────── Print ───────────────────────────── */

export function WapPrint({ id }: { id: string }) {
  const t = useTranslations("waps");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const locale = useLocale();
  const name = useLocalizedName();
  const q = useWapPrint(id);
  const { date } = useFormatters(q.data?.wap.project_id);
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const p = q.data;
  const w = p.wap;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2 print:hidden">
        <Button onClick={() => window.print()} data-testid="do-print">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={`/waps/${id}`}>{tc("back")}</Link>
        </Button>
      </div>
      {/* A4 permit for display at the work site: bilingual labels (EN / AR) whatever the screen language,
          black on white so it prints the same from a dark screen. */}
      <article
        className="paper mx-auto flex w-full max-w-3xl flex-col gap-4 rounded-xl border bg-white p-6 text-black print:max-w-none print:rounded-none print:border-0 print:p-0"
        data-testid="wap-print"
      >
        <AccessPrintHeader title="wapTitle" projectId={w.project_id} />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-2">
            <p className="ltr text-2xl font-bold tracking-wide">
              {w.wap_no}
              {w.revision_no ? <span className="text-lg font-semibold"> · r{w.revision_no}</span> : null}
            </p>
            <p className="flex items-center gap-2 text-sm">
              <BiLabel k="status" className="text-xs" />
              <span className="rounded border-2 border-black px-2 py-0.5 text-base font-bold">{te(`wapStatus.${w.status}`)}</span>
            </p>
            <p className="flex flex-col text-sm">
              <BiLabel k="dates" className="text-xs" />
              <span className="text-lg font-semibold">
                {date(w.valid_from)} – {date(w.valid_to)}
              </span>
            </p>
          </div>
          <div className="flex flex-col items-center gap-1 rounded-lg border-2 border-black p-2">
            <QrImage payload={p.qr_payload} size={150} label={t("wapQr", { no: w.wap_no })} />
            <span className="ltr font-mono font-bold">{p.printed_ref}</span>
            <BiLabel k="scanAtGate" className="text-[8pt]" />
          </div>
        </div>
        <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-6 gap-y-2 border-y border-black py-3 text-sm">
          <dt><BiLabel k="site" stack className="text-xs font-medium" /></dt>
          <dd>{name(w.site.name_en, w.site.name_ar)}</dd>
          <dt><BiLabel k="zones" stack className="text-xs font-medium" /></dt>
          <dd>
            {w.zones.map((z) => (
              <span key={z.id} className="me-3 inline-block">
                <Code className="font-semibold">{z.code}</Code> {name(z.name_en, z.name_ar)}
              </span>
            ))}
          </dd>
          <dt><BiLabel k="contractor" stack className="text-xs font-medium" /></dt>
          <dd><Code>{w.engagement.short_code}</Code></dd>
          <dt><BiLabel k="windows" stack className="text-xs font-medium" /></dt>
          <dd>
            <WindowsText windows={w.windows} />
          </dd>
          <dt><BiLabel k="scope" stack className="text-xs font-medium" /></dt>
          <dd className="flex flex-col items-start gap-1">
            <span lang="en" dir="ltr">{w.scope_en}</span>
            {w.scope_ar ? (
              <span lang="ar" dir="rtl" className="text-start">
                {w.scope_ar}
              </span>
            ) : null}
          </dd>
        </dl>
        <section>
          <h2 className="mb-2 flex items-baseline gap-2 font-semibold">
            <BiLabel k="crew" />
            <span className="tabular-nums">({w.crew_count})</span>
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b-2 border-black text-start text-xs">
                <th className="py-1 text-start font-medium"><BiLabel k="workerNo" stack /></th>
                <th className="py-1 text-start font-medium"><BiLabel k="name" stack /></th>
                <th className="py-1 text-start font-medium"><BiLabel k="role" stack /></th>
              </tr>
            </thead>
            <tbody>
              {w.crew
                .filter((c) => c.status === "included")
                .map((c) => (
                  <tr key={c.worker.id} className="border-b">
                    <td className="py-1"><Code>{c.worker.worker_no}</Code></td>
                    <td className="py-1">{personName(c.worker, locale)}</td>
                    <td className="py-1">{te(`crewRole.${c.crew_role}`)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
        {w.vehicles.length ? (
          <section>
            <h2 className="mb-2 flex items-baseline gap-2 font-semibold">
              <BiLabel k="vehicles" />
              <span className="tabular-nums">({w.vehicle_count})</span>
            </h2>
            <p className="ltr text-sm">
              {w.vehicles
                .filter((v) => v.status === "included")
                .map((v) => `${v.vehicle.vehicle_no} (${v.vehicle.fleet_no})`)
                .join(" · ")}
            </p>
          </section>
        ) : null}
        <footer className="mt-auto border-t-2 border-black pt-2 text-xs">
          <BiLabel k="wapFooter" stack className="gap-1" />
        </footer>
      </article>
    </div>
  );
}

/* ───────────────────────────── Ops events ───────────────────────────── */

export function OpsEventListPage() {
  return (
    <ProjectGate>
      {(p) => (
        <AirportOnly project={p}>{<OpsEventList project={p} />}</AirportOnly>
      )}
    </ProjectGate>
  );
}

function OpsEventList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const types = s.getAll("type") as Schemas["OpsEventType"][];
  const [declare, setDeclare] = useState(false);
  const q = useOpsEvents(project.id, {
    active: s.getBool("active") ?? null,
    type: types.length ? types : null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("opsEvents")}
        description={t("opsHint")}
        actions={
          canWrite(me, "wap.suspend", project.id) ? (
            <Button
              variant="destructive"
              onClick={() => setDeclare(true)}
              data-testid="declare-ops"
            >
              <CloudFog aria-hidden />
              {t("declare")}
            </Button>
          ) : null
        }
      />
      <WapSubNav />
      <ListToolbar
        actions={
          can(me, "export.access", project.id) ? (
            <ExportButtons
              dataset="ops_events"
              params={{ project_id: project.id }}
            />
          ) : null
        }
      >
        <SelectFilter
          id="op-active"
          label={t("activeOnly")}
          value={s.get("active") === "true" ? "true" : ""}
          onChange={(v) => s.set({ active: v })}
          options={[{ value: "true", label: tc("yes") }]}
        />
        <MultiSelect
          id="op-type"
          label={t("fields.type")}
          options={OPS_EVENT_TYPES.map((x) => ({
            value: x,
            label: te(`opsEventType.${x}`),
          }))}
          value={types}
          onChange={(v) => s.set({ type: v })}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="ops-table">
            <THead>
              <TR>
                <TH>{t("fields.ops_no")}</TH>
                <TH>{t("fields.type")}</TH>
                <TH>{t("fields.zones")}</TH>
                <TH>{t("fields.source")}</TH>
                <TH>{t("fields.started_at")}</TH>
                <TH>{t("fields.ended_at")}</TH>
                <TH>{t("suspendedWaps")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((o) => (
                <TR key={o.id} data-testid="ops-row">
                  <TD label={t("fields.ops_no")}>
                    <Link
                      href={`/ops-events/${o.id}`}
                      className="ltr font-medium text-primary hover:underline"
                    >
                      {o.ops_no}
                    </Link>
                  </TD>
                  <TD label={t("fields.type")}>
                    {te(`opsEventType.${o.type}`)}{" "}
                    {o.active ? (
                      <StatusBadge status="danger" label={t("activeNow")} />
                    ) : null}
                  </TD>
                  <TD label={t("fields.zones")}>
                    <span className="ltr">
                      {o.zones.map((z) => z.code).join(", ")}
                    </span>
                  </TD>
                  <TD label={t("fields.source")}>
                    {te(`opsEventSource.${o.source}`)}{" "}
                    <span className="ltr text-xs">{o.source_ref}</span>
                  </TD>
                  <TD label={t("fields.started_at")}>
                    {dateTime(o.started_at)}
                  </TD>
                  <TD label={t("fields.ended_at")}>
                    {o.ended_at ? dateTime(o.ended_at) : "—"}
                  </TD>
                  <TD label={t("suspendedWaps")}>
                    {o.suspended_wap_ids.length}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={q.data?.total ?? 0}
            onPage={(p) => s.set({ page: p })}
          />
        </>
      ) : (
        <EmptyState />
      )}
      {declare ? (
        <DeclareDialog project={project} onClose={() => setDeclare(false)} />
      ) : null}
    </div>
  );
}

function DeclareDialog({
  project,
  onClose,
}: {
  project: Schemas["ProjectRead"];
  onClose: () => void;
}) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const router = useRouter();
  const qc = useQueryClient();
  const opts = useProjectOptions(project.id);
  const [type, setType] = useState<Schemas["OpsEventType"]>("lvp");
  const [site, setSite] = useState(opts.sites[0]?.value ?? "");
  const profiles = useZoneProfiles(project.id, site || null);
  const defaults = useMemo(
    () =>
      type === "lvp" || type === "dust_sandstorm"
        ? (profiles.data?.items ?? [])
            .filter((p) => p.lvp_withdrawal_required)
            .map((p) => p.zone.id)
        : [],
    [type, profiles.data],
  );
  const [extra, setExtra] = useState<string[]>([]);
  const zones = Array.from(new Set([...defaults, ...extra]));
  const [source, setSource] = useState<Schemas["OpsEventSource"]>("aocc");
  const [ref, setRef] = useState("");
  const [notes, setNotes] = useState("");
  return (
    <StepDialog
      title={t("declare")}
      description={t("declareHint")}
      destructive
      confirmLabel={t("declare")}
      testId="declare-confirm"
      wide
      disabled={!site || !ref.trim() || zones.length === 0}
      onConfirm={async () => {
        const o = await unwrap(
          api.POST("/api/v1/projects/{project_id}/ops-events", {
            params: { path: { project_id: project.id } },
            body: {
              type,
              site_id: site,
              zone_ids: zones,
              source,
              source_ref: ref.trim(),
              notes: notes.trim() || null,
            },
          }),
        );
        for (const k of ["ops-events", "waps", "wap", "wap-board"])
          await qc.invalidateQueries({ queryKey: [k] });
        router.push(`/ops-events/${o.id}`);
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="dc-type" label={t("fields.type")} required>
          <Select
            value={type}
            onChange={(e) => setType(e.target.value as Schemas["OpsEventType"])}
          >
            {OPS_EVENT_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`opsEventType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="dc-site" label={tc("site")} required>
          <Select value={site} onChange={(e) => setSite(e.target.value)}>
            <option value="">{tc("select")}</option>
            {opts.sites.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="dc-source" label={t("fields.source")} required>
          <Select
            value={source}
            onChange={(e) =>
              setSource(e.target.value as Schemas["OpsEventSource"])
            }
          >
            {OPS_EVENT_SOURCES.map((x) => (
              <option key={x} value={x}>
                {te(`opsEventSource.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="dc-ref" label={t("fields.source_ref")} required>
          <Input
            className="ltr"
            maxLength={40}
            value={ref}
            onChange={(e) => setRef(e.target.value)}
          />
        </FormField>
      </div>
      {defaults.length ? (
        <p className="text-sm" data-testid="default-zones">
          {t("defaultZones", {
            zones: opts.zones
              .filter((z) => defaults.includes(z.value))
              .map((z) => z.label.split(" — ")[0])
              .join(", "),
          })}
        </p>
      ) : null}
      <MultiSelect
        id="dc-zones"
        label={t("extraZones")}
        options={opts.zones
          .filter((z) => z.siteId === site && !defaults.includes(z.value))
          .map((z) => ({ value: z.value, label: z.label }))}
        value={extra}
        onChange={setExtra}
        className="lg:w-full"
      />
      <FormField id="dc-notes" label={t("fields.notes")}>
        <Textarea
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </FormField>
    </StepDialog>
  );
}

export function OpsEventDetail({ id }: { id: string }) {
  const t = useTranslations("waps");
  const te = useTranslations("enums");
  const me = useMeData();
  const name = useLocalizedName();
  const q = useOpsEvent(id);
  const qc = useQueryClient();
  const [end, setEnd] = useState(false);
  const { dateTime } = useFormatters(q.data?.project_id);
  if (q.isError)
    return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const o = q.data;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs
          items={[
            { label: t("opsEvents"), href: "/ops-events" },
            { label: o.ops_no },
          ]}
        />
        <PageHeader
          title={o.ops_no}
          description={te(`opsEventType.${o.type}`)}
          actions={
            <>
              {o.active ? (
                <StatusBadge status="danger" label={t("activeNow")} />
              ) : (
                <StatusBadge status="closed" label={t("ended")} />
              )}
              {o.active && canWrite(me, "wap.suspend", o.project_id) ? (
                <Button onClick={() => setEnd(true)} data-testid="end-ops">
                  {t("endEvent")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {!o.active && o.suspended_wap_ids.length ? (
        <Alert tone="info">{t("resumeHint")}</Alert>
      ) : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem
              label={tc_site()}
            >{`${o.site.code} — ${name(o.site.name_en, o.site.name_ar)}`}</FieldItem>
            <FieldItem label={t("fields.zones")}>
              <span className="ltr">
                {o.zones.map((z) => z.code).join(", ")}
              </span>
            </FieldItem>
            <FieldItem label={t("fields.source")}>
              {te(`opsEventSource.${o.source}`)} ·{" "}
              <span className="ltr">{o.source_ref}</span>
            </FieldItem>
            <FieldItem label={t("fields.started_at")}>
              {dateTime(o.started_at)}
            </FieldItem>
            <FieldItem label={t("fields.ended_at")}>
              {o.ended_at ? dateTime(o.ended_at) : "—"}
            </FieldItem>
            <FieldItem label={t("fields.declared_by")}>
              {name(o.declared_by.full_name_en, o.declared_by.full_name_ar)}
            </FieldItem>
            <FieldItem label={t("fields.notes")} wide>
              {o.notes ?? "—"}
            </FieldItem>
            <FieldItem label={t("suspendedWaps")} wide>
              {o.suspended_wap_ids.length
                ? o.suspended_wap_ids.map((w, i) => (
                    <Link
                      key={w}
                      href={`/waps/${w}`}
                      className="me-2 text-primary hover:underline"
                      data-testid="suspended-wap"
                    >
                      {t("wapN", { n: i + 1 })}
                    </Link>
                  ))
                : "—"}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <HistoryPanel entityType="ops_event" entityId={o.id} />
      {end ? (
        <StepDialog
          title={t("endEvent")}
          description={t("endHint")}
          confirmLabel={t("endEvent")}
          testId="end-ops-confirm"
          onConfirm={async () => {
            const u = await unwrap(
              api.POST("/api/v1/ops-events/{event_id}/end", {
                params: { path: { event_id: o.id } },
                body: {},
              }),
            );
            qc.setQueryData(ak.opsEvent(o.id), u);
            for (const k of ["ops-events", "wap-board"])
              await qc.invalidateQueries({ queryKey: [k] });
          }}
          onClose={() => setEnd(false)}
        />
      ) : null}
    </div>
  );
  function tc_site() {
    return t("site");
  }
}
