"use client";
import { useQuery } from "@tanstack/react-query";
import { MapPinCheck, Plus, XCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { DeploymentPicker, StepDialog } from "@/components/access/common";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect } from "@/components/common/pickers";
import { RecordActions } from "@/components/common/record-actions";
import { StackedDate } from "@/components/medical/common";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { fromLocalInput } from "@/components/emergency/common";
import { DateFilter } from "@/components/training/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useJourneyPlan, useJourneyPlans, useSiteVehicles, useSvRefresh } from "@/lib/api/site-vehicles";
import { useDebounced } from "@/lib/use-debounced";
import { formatDateTime } from "@/lib/datetime";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { DriverText, JOURNEY_STATUSES, JourneyStatusBadge, PrototypeBadge, SvGate, SvSubNav, VehicleRefText, useSvCaps, useSvLabels } from "./common";

type S = Schemas;
type Plan = S["SiteVehJourneyRead"];
const PAGE_SIZE = 50;

/* ═════════════ list: Planned / Arrived / Cancelled, Overdue flag only (§4.3, JM-1) ═════════════ */

export function JourneyPlansPage() {
  return <SvGate>{(p) => <Register project={p} />}</SvGate>;
}

function Register({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.journey");
  const tc = useTranslations("common");
  const l = useSvLabels();
  const caps = useSvCaps(project.id);
  const { prefs } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["SiteVehJourneyStatus"] | "";
  const overdue = s.get("overdue") ?? "";
  const from = s.get("date_from") ?? "";
  const to = s.get("date_to") ?? "";
  const q = useJourneyPlans(
    project.id,
    { status: status ? [status] : null, overdue: overdue ? overdue === "true" : null, date_from: from || null, date_to: to || null, page, page_size: PAGE_SIZE },
    { enabled: !caps.aggregatesOnly },
  );
  const [arrive, setArrive] = useState<Plan | null>(null);
  const arrow = useLocale() === "ar" ? "←" : "→";
  if (caps.aggregatesOnly) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        badge={<PrototypeBadge />}
        description={t("subtitle")}
        actions={
          caps.record ? (
            <Button asChild>
              <Link href="/site-vehicles/journeys/new" data-testid="sv-new-journey">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <SvSubNav projectId={project.id} />
      <Alert tone="info" className="mb-4">
        {t("prototypeNote")}
      </Alert>
      <ListToolbar>
        <SelectFilter id="jp-status" label={t("status")} value={status} onChange={(v) => s.set({ status: v })} options={JOURNEY_STATUSES.map((x) => ({ value: x, label: l.journeyStatus(x) }))} />
        <SelectFilter id="jp-overdue" label={t("overdue")} value={overdue} onChange={(v) => s.set({ overdue: v })} options={[{ value: "true", label: t("overdueOnly") }]} />
        <DateFilter id="jp-from" label={t("dateFrom")} value={from} onChange={(v) => s.set({ date_from: v })} />
        <DateFilter id="jp-to" label={t("dateTo")} value={to} onChange={(v) => s.set({ date_to: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table compact data-testid="sv-journeys">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("route")}</TH>
                <TH>{t("vehicle")}</TH>
                <TH>{t("depart")}</TH>
                <TH>{t("arrive")}</TH>
                <TH>{t("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((j) => (
                <TR key={j.id} data-testid="sv-journey-row" data-no={j.plan_no} data-status={j.status} data-overdue={j.overdue}>
                  <TD label={t("no")}>
                    <Link href={`/site-vehicles/journeys/${j.id}`} className="ltr font-medium whitespace-nowrap text-primary hover:underline">
                      {j.plan_no}
                    </Link>
                  </TD>
                  <TD label={t("route")} data-full="" className="max-md:order-2 md:min-w-40">
                    <span dir="auto">{j.origin}</span> {arrow} <span dir="auto">{j.destination}</span>
                    <span className="block text-xs text-muted-foreground">
                      <bdi className="ltr">{t("km", { n: j.distance_km })}</bdi>
                      {j.passengers ? ` · ${t("pax", { n: j.passengers })}` : ""}
                    </span>
                  </TD>
                  <TD label={t("vehicle")} data-full="" className="max-md:order-3 md:min-w-44">
                    <VehicleRefText v={j.vehicle} />
                    <span className="block">
                      <DriverText w={j.driver} />
                    </span>
                  </TD>
                  <TD label={t("depart")} data-keep-label="" className="max-md:order-4 max-md:text-xs">
                    <StackedDate v={j.planned_depart} time projectId={project.id} className="max-md:inline-flex max-md:flex-row max-md:gap-1" />
                  </TD>
                  <TD label={t("arrive")} data-keep-label="" className="max-md:order-4 max-md:text-xs">
                    <StackedDate v={j.planned_arrive} time projectId={project.id} className="max-md:inline-flex max-md:flex-row max-md:gap-1" />
                    {j.arrived_at ? <span className="block text-xs whitespace-nowrap text-muted-foreground">{t("arrivedAt", { at: formatDateTime(j.arrived_at, { ...prefs, showHijri: false }) })}</span> : null}
                  </TD>
                  <TD label={t("status")} className="max-md:order-1 max-md:ms-auto">
                    <span className="flex flex-col items-start gap-1.5">
                      <JourneyStatusBadge status={j.status} overdue={j.overdue} />
                      {/* the one everyday step sits with the status: no extra column (7b design pass) */}
                      {caps.record && j.status === "planned" ? (
                        <Button size="sm" variant="outline" className="max-md:min-h-11" onClick={() => setArrive(j)} data-testid="jp-arrive">
                          <MapPinCheck aria-hidden />
                          {t("markArrived")}
                        </Button>
                      ) : null}
                    </span>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {arrive ? <ArriveDialog plan={arrive} onClose={() => setArrive(null)} /> : null}
    </div>
  );
}

/* ═════════════ minimal form with the distance / night hint (§3.4, JM-1, JM-2) ═════════════ */

export function JourneyPlanNewPage() {
  return <SvGate>{(p, settings) => <PlanForm project={p} settings={settings} />}</SvGate>;
}

function PlanForm({ project, settings }: { project: S["ProjectRead"]; settings: S["SiteVehSettingsRead"] }) {
  const t = useTranslations("sv.journey");
  const tn = useTranslations("sv.nav");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const l = useSvLabels();
  const router = useRouter();
  const refresh = useSvRefresh();
  const warn = useWarningToasts();
  const caps = useSvCaps(project.id);
  const sp = useSearchParams();
  const vehicles = useSiteVehicles(project.id, { page_size: 200 });
  const [vehicleId, setVehicleId] = useState(sp.get("vehicle") ?? "");
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [f, setF] = useState({ passengers: "0", origin: project.code ? `${project.code} site` : "", destination: "", distance_km: "", depart: "", arrive: "", contact: "", notes: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const vehicle = (vehicles.data?.items ?? []).find((v) => v.id === vehicleId);
  const hint = useJourneyHint(project.id, f.distance_km, f.depart, f.arrive);

  async function save() {
    const e: Record<string, string> = {};
    if (!vehicleId) e.vehicle = tv("required");
    if (!dep) e.driver = tv("required");
    if (f.origin.trim().length < 2) e.origin = tv("required");
    if (f.destination.trim().length < 2) e.destination = tv("required");
    const km = Number(f.distance_km);
    if (!(km >= 1 && km <= 1000)) e.distance_km = t("kmRange");
    if (!f.depart) e.depart = tv("required");
    if (!f.arrive) e.arrive = tv("required");
    if (!f.contact) e.contact = tv("required");
    setErrors(e);
    if (Object.keys(e).length || !dep) return;
    setBusy(true);
    setError(null);
    const body: S["SiteVehJourneyCreate"] = {
      vehicle_id: vehicleId,
      driver_worker_id: dep.worker_id,
      passengers: Number(f.passengers || 0),
      origin: f.origin.trim(),
      destination: f.destination.trim(),
      distance_km: km,
      planned_depart: fromLocalInput(f.depart) ?? f.depart,
      planned_arrive: fromLocalInput(f.arrive) ?? f.arrive,
      contact_user_id: f.contact,
      notes: f.notes.trim() || null,
    };
    try {
      const j = await unwrap(api.POST("/api/v1/projects/{project_id}/journey-plans", { params: { path: { project_id: project.id } }, body }));
      await refresh();
      warn(j.warnings?.filter((w) => w.code !== "JOURNEY_PLAN_RECOMMENDED"));
      toast.success(t("saved", { no: j.plan_no }));
      router.push(`/site-vehicles/journeys/${j.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  if (!caps.record) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      data-testid="sv-journey-form"
    >
      <div>
        <Breadcrumbs items={[{ label: tn("journeys"), href: "/site-vehicles/journeys" }, { label: t("new") }]} />
        <PageHeader title={t("new")} badge={<PrototypeBadge />} description={t("intro", { km: settings.journey_hint_km, from: settings.journey_hint_night_from, to: settings.journey_hint_night_to })} />
      </div>
      <MutationError error={error} />
      <FormSection title={t("trip")}>
        <FormField id="jp-origin" label={t("origin")} required error={errors.origin}>
          <Input maxLength={120} value={f.origin} onChange={set("origin")} data-testid="jp-origin" />
        </FormField>
        <FormField id="jp-dest" label={t("destination")} required error={errors.destination}>
          <Input maxLength={120} value={f.destination} onChange={set("destination")} data-testid="jp-dest" />
        </FormField>
        <FormField id="jp-km" label={t("distance")} required error={errors.distance_km}>
          <Input type="number" inputMode="numeric" min={1} max={1000} className="ltr" value={f.distance_km} onChange={set("distance_km")} data-testid="jp-km" />
        </FormField>
        <FormField id="jp-pax" label={t("passengers")} hint={vehicle?.seats ? t("paxHint", { max: vehicle.seats - 1 }) : undefined}>
          <Input type="number" inputMode="numeric" min={0} max={59} className="ltr" value={f.passengers} onChange={set("passengers")} data-testid="jp-pax" />
        </FormField>
        <FormField id="jp-depart" label={t("depart")} required error={errors.depart}>
          <Input type="datetime-local" className="ltr" value={f.depart} onChange={set("depart")} data-testid="jp-depart" />
        </FormField>
        <FormField id="jp-arrive" label={t("arrive")} required error={errors.arrive}>
          <Input type="datetime-local" className="ltr" value={f.arrive} onChange={set("arrive")} data-testid="jp-arrive-at" />
        </FormField>
        <div className="sm:col-span-2" aria-live="polite">
          {hint ? (
            hint.recommended ? (
              /* advice, not a hazard: info tone (the platform never requires a plan, JM-1) */
              <Alert tone="info" data-testid="jp-hint" data-reasons={hint.reasons.join(",")}>
                <p className="font-medium">{t("hint")}</p>
                <ul className="mt-1 list-disc ps-5">
                  {hint.reasons.map((r) => (
                    <li key={r} className="first-letter:uppercase">
                      {t(`hintReason.${r === "night" ? "night" : "distance"}`, { km: settings.journey_hint_km, from: settings.journey_hint_night_from, to: settings.journey_hint_night_to })}
                    </li>
                  ))}
                </ul>
              </Alert>
            ) : (
              <p className="text-xs text-muted-foreground" data-testid="jp-no-hint">
                {t("noHint")}
              </p>
            )
          ) : null}
        </div>
      </FormSection>
      <FormSection title={t("people")}>
        <FormField id="jp-vehicle" label={t("vehicle")} required error={errors.vehicle}>
          <Select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} data-testid="jp-vehicle">
            <option value="">{tc("select")}</option>
            {(vehicles.data?.items ?? [])
              .filter((v) => v.status !== "withdrawn")
              .map((v) => (
                <option key={v.id} value={v.id}>
                  {v.vehicle_no} · {v.fleet_no} · {l.useClass(v.use_class)}
                  {v.readiness !== "ready" ? ` (${l.readiness(v.readiness)})` : ""}
                </option>
              ))}
          </Select>
        </FormField>
        <div className="sm:col-span-2">
          <DeploymentPicker id="jp-driver" projectId={project.id} value={dep} onChange={setDep} status={["mobilised"]} label={t("driver")} required error={errors.driver} />
        </div>
        <FormField id="jp-contact" label={t("contact")} required error={errors.contact} hint={t("contactHint")}>
          <UserSelect projectId={project.id} value={f.contact} onChange={set("contact")} data-testid="jp-contact" />
        </FormField>
        <FormField id="jp-notes" label={t("notes")} className="sm:col-span-2" hint={t("notesHint")}>
          <Textarea maxLength={500} value={f.notes} onChange={set("notes")} data-testid="jp-notes" />
        </FormField>
      </FormSection>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy} data-testid="jp-save">
          {busy ? tc("saving") : t("save")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.push("/site-vehicles/journeys")}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

/** JM-1: the server decides whether a plan is recommended (distance or night window); the form only shows it. */
function useJourneyHint(projectId: string, km: string, depart: string, arrive: string) {
  const input = useDebounced({ km, depart, arrive }, 300);
  const n = Number(input.km);
  const d = fromLocalInput(input.depart);
  const a = fromLocalInput(input.arrive);
  const ok = n >= 1 && n <= 1000 && Boolean(d) && Boolean(a) && (a as string) > (d as string);
  const q = useQuery({
    queryKey: ["sv-journey-hint", projectId, n, d, a],
    queryFn: () => unwrap(api.POST("/api/v1/projects/{project_id}/journey-plans/hint", { params: { path: { project_id: projectId } }, body: { distance_km: n, planned_depart: d as string, planned_arrive: a as string } })),
    enabled: ok,
    retry: false,
    staleTime: 60_000,
  });
  return ok ? q.data : undefined;
}

/* ═════════════ one plan: arrive / cancel ═════════════ */

export function JourneyPlanDetailPage({ id }: { id: string }) {
  return <SvGate>{(p) => <Detail project={p} id={id} />}</SvGate>;
}

function Detail({ project, id }: { project: S["ProjectRead"]; id: string }) {
  const t = useTranslations("sv.journey");
  const tn = useTranslations("sv.nav");
  const caps = useSvCaps(project.id);
  const q = useJourneyPlan(id);
  const { dateTime } = useFormatters(project.id);
  const [act, setAct] = useState<"arrive" | "cancel" | null>(null);
  const ar = useLocale() === "ar";
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const j = q.data;
  const planned = j.status === "planned";
  const arrow = ar ? "←" : "→";
  return (
    <div className="flex flex-col gap-6" data-testid="sv-journey-detail" data-status={j.status} data-overdue={j.overdue}>
      <div>
        <Breadcrumbs items={[{ label: tn("journeys"), href: "/site-vehicles/journeys" }, { label: j.plan_no }]} />
        <PageHeader
          title={<bdi className="ltr">{j.plan_no}</bdi>}
          badge={
            <>
              <JourneyStatusBadge status={j.status} overdue={j.overdue} />
              <PrototypeBadge />
            </>
          }
          description={`\u2068${j.origin}\u2069 ${arrow} \u2068${j.destination}\u2069`}
          actions={
            caps.record && planned ? (
              <Button onClick={() => setAct("arrive")} data-testid="jp-arrive">
                <MapPinCheck aria-hidden />
                {t("markArrived")}
              </Button>
            ) : null
          }
        />
      </div>
      {j.overdue ? (
        <Alert tone="warning" data-testid="jp-overdue-note">
          {t("overdueHint")}
        </Alert>
      ) : null}
      {j.hint_recommended ? (
        <p className="text-sm text-muted-foreground" data-testid="jp-was-recommended">
          {t("wasRecommended")}
        </p>
      ) : null}
      <ApiWarnings warnings={j.warnings?.filter((w) => w.code !== "JOURNEY_PLAN_RECOMMENDED")} />
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("vehicle")}>
              <Link href={`/site-vehicles/${j.vehicle.id}`} className="text-primary hover:underline">
                <VehicleRefText v={j.vehicle} />
              </Link>
            </FieldItem>
            <FieldItem label={t("driver")}>
              <DriverText w={j.driver} />
              {!j.driver_authorised ? <span className="block text-xs font-medium text-warning">{t("driverNotAuthorised")}</span> : null}
            </FieldItem>
            <FieldItem label={t("passengers")}>{j.passengers}</FieldItem>
            <FieldItem label={t("distance")}>
              <bdi className="ltr">{t("km", { n: j.distance_km })}</bdi>
            </FieldItem>
            <FieldItem label={t("depart")}>{dateTime(j.planned_depart)}</FieldItem>
            <FieldItem label={t("arrive")}>{dateTime(j.planned_arrive)}</FieldItem>
            <FieldItem label={t("contact")}>{j.contact?.full_name_en ?? "—"}</FieldItem>
            {j.arrived_at ? <FieldItem label={t("arrivedAtLabel")}>{dateTime(j.arrived_at)}</FieldItem> : null}
            {j.cancelled_reason ? (
              <FieldItem label={t("cancelReason")} wide>
                <span dir="auto">{j.cancelled_reason}</span>
              </FieldItem>
            ) : null}
            <FieldItem label={t("notes")} wide>
              {j.notes ? <span dir="auto">{j.notes}</span> : "—"}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <HistoryPanel entityType="journey_plan" entityId={j.id} />
      {caps.record && planned ? (
        <RecordActions testId="jp-record-actions">
          <Button variant="destructive-outline" onClick={() => setAct("cancel")} data-testid="jp-cancel">
            <XCircle aria-hidden />
            {t("cancel")}
          </Button>
        </RecordActions>
      ) : null}
      {act === "arrive" ? <ArriveDialog plan={j} onClose={() => setAct(null)} /> : null}
      {act === "cancel" ? <CancelDialog plan={j} onClose={() => setAct(null)} /> : null}
    </div>
  );
}

function ArriveDialog({ plan, onClose }: { plan: Plan; onClose: () => void }) {
  const t = useTranslations("sv.journey");
  const refresh = useSvRefresh();
  const [at, setAt] = useState("");
  return (
    <StepDialog
      title={t("markArrived")}
      description={t("arriveHint", { no: plan.plan_no })}
      confirmLabel={t("markArrived")}
      testId="jp-arrive-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/journey-plans/{plan_id}/arrive", { params: { path: { plan_id: plan.id } }, body: { arrived_at: at ? fromLocalInput(at) : null } }));
        await refresh();
        toast.success(t("arrived", { no: plan.plan_no }));
      }}
      onClose={onClose}
    >
      <FormField id="jp-arrived-at" label={t("arrivedAtLabel")} hint={t("arrivedAtHint")}>
        <Input type="datetime-local" className="ltr" value={at} onChange={(e) => setAt(e.target.value)} data-testid="jp-arrived-at" />
      </FormField>
    </StepDialog>
  );
}

function CancelDialog({ plan, onClose }: { plan: Plan; onClose: () => void }) {
  const t = useTranslations("sv.journey");
  const tf = useTranslations("fu.common");
  const refresh = useSvRefresh();
  const [reason, setReason] = useState("");
  const n = reason.trim().length;
  return (
    <StepDialog
      title={t("cancel")}
      description={t("cancelHint", { no: plan.plan_no })}
      confirmLabel={t("cancelConfirm")}
      dismissLabel={t("keep")}
      destructive
      testId="jp-cancel-confirm"
      disabled={n < 5}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/journey-plans/{plan_id}/cancel", { params: { path: { plan_id: plan.id } }, body: { reason: reason.trim() } }));
        await refresh();
        toast.success(t("cancelled", { no: plan.plan_no }));
      }}
      onClose={onClose}
    >
      <FormField id="jp-cancel-reason" label={tf("reason")} required hint={tf("reasonMin", { min: 5, n })}>
        <Textarea maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="jp-cancel-reason" />
      </FormField>
    </StepDialog>
  );
}
