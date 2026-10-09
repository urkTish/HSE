"use client";
import { Plus, Siren, Trash2, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { Tick, UserName } from "@/components/cert/common";
import { FreeText, StackedDate } from "@/components/medical/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useEmergencyEvent, useEmergencyEvents, useEmergencyRefresh } from "@/lib/api/emergency";
import { useIncidents } from "@/lib/api/hse";
import { EVENT_STATUSES, INCIDENT_EVENT_TYPES } from "@/lib/emergency-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { EmReasonDialog, EventStatusBadge, fromLocalInput, Minutes, NoNamesHint, nowLocal, toLocalInput, useEmCaps, useEmRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Ev = S["EventRead"];
type Agency = S["app__core__emergency_enums__Agency"];

/* ═════════════ real emergency events (§3.7, EV-1…EV-7) ═════════════ */

export function EmergencyEventsPage() {
  return <ProjectGate>{(p) => <Events project={p} />}</ProjectGate>;
}

function Events({ project }: { project: Project }) {
  const t = useTranslations("emergency.events");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const { label, items: refItems } = useEmRef();
  const s = useSearchState();
  const type = (s.get("type") ?? "") as S["EventType"] | "";
  const status = (s.get("status") ?? "") as S["EventStatus"] | "";
  const page = Number(s.get("page") ?? 1);
  const q = useEmergencyEvents(project.id, { event_type: type ? [type] : null, status: status ? [status] : null, page, page_size: 50 }, { enabled: caps.view });
  const declare = s.get("declare") === "1" && caps.declare;
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.declare ? (
            <Button variant="destructive" onClick={() => s.set({ declare: "1" })} data-testid="event-declare">
              <Siren aria-hidden />
              {t("declare")}
            </Button>
          ) : null
        }
      />
      <ListToolbar>
        <SelectFilter id="ev-type" label={t("type")} value={type} onChange={(v) => s.set({ type: v, page: null })} options={refItems("event_types").map((x) => ({ value: x.code as S["EventType"], label: label("event_types", x.code) }))} />
        <SelectFilter id="ev-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={EVENT_STATUSES.map((x) => ({ value: x, label: te(`emEventStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="events-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("type")}</TH>
                <TH>{t("where")}</TH>
                <TH>{t("raised")}</TH>
                <TH>{t("times")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((e) => (
                <TR key={e.id} data-testid="event-row" data-no={e.event_no} data-status={e.status} data-type={e.event_type}>
                  <TD label={t("no")}>
                    <Link href={`/emergency-events/${e.id}`} className="font-medium text-primary hover:underline">
                      <Code>{e.event_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("type")}>
                    {label("event_types", e.event_type)}
                    <span className="block text-xs text-muted-foreground">{label("response_types", e.response_type)}</span>
                  </TD>
                  <TD label={t("where")}>
                    <Code>{e.site_code}</Code>
                    {e.zone_codes.length ? <span className="block text-xs text-muted-foreground">{e.zone_codes.join(", ")}</span> : null}
                  </TD>
                  <TD label={t("raised")}>
                    <StackedDate v={e.raised_at} projectId={project.id} time />
                    {e.late_entry ? (
                      <Badge tone="warning" className="mt-1">
                        {t("lateEntry")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={t("times")}>
                    <span className="flex flex-col text-sm">
                      <span>
                        {t("firstResponse")}: <Minutes v={e.times.first_response_min} />
                      </span>
                      <span>
                        {t("total")}: <Minutes v={e.times.total_min} />
                      </span>
                    </span>
                  </TD>
                  <TD label={tc("status")}>
                    <EventStatusBadge status={e.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: String(p) })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {declare ? <DeclareDialog project={project} onClose={() => s.set({ declare: null })} /> : null}
    </div>
  );
}

function DeclareDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("emergency.events");
  const router = useRouter();
  const refresh = useEmergencyRefresh();
  const opts = useProjectOptions(project.id);
  const { items, label } = useEmRef();
  // StepDialog closes after a successful confirm: open the new event instead of clearing the ?declare URL.
  const goTo = useRef<string | null>(null);
  const [type, setType] = useState<S["EventType"] | "">("");
  const [site, setSite] = useState("");
  const [zones, setZones] = useState<string[]>([]);
  const [response, setResponse] = useState<S["ResponseType"] | "">("");
  const [location, setLocation] = useState("");
  const [casualties, setCasualties] = useState("0");
  const [late, setLate] = useState(false);
  const [raised, setRaised] = useState(nowLocal());
  const [notes, setNotes] = useState("");
  const evac = response === "zone_evacuation" || response === "site_evacuation" || response === "shelter_in_place";
  return (
    <StepDialog
      wide
      destructive
      title={t("declareTitle")}
      description={t("declareHint")}
      warning={evac && !late ? t("declareEvacWarning") : undefined}
      confirmLabel={t("declare")}
      testId="declare-confirm"
      disabled={!type || !site || !response || !zones.length}
      onConfirm={async () => {
        const e = await unwrap(
          api.POST("/api/v1/projects/{project_id}/emergency-events", {
            params: { path: { project_id: project.id } },
            body: {
              event_type: type as S["EventType"],
              site_id: site,
              zone_ids: zones,
              response_type: response as S["ResponseType"],
              location_en: location.trim() || null,
              casualties_count: Number(casualties) || 0,
              raised_at: late ? fromLocalInput(raised) : null,
              notes: notes.trim() || null,
            },
          }),
        );
        await refresh();
        toast.success(t("declared", { no: e.event_no }));
        goTo.current = `/emergency-events/${e.id}`;
      }}
      onClose={() => (goTo.current ? router.push(goTo.current) : onClose())}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ed-type" label={t("type")} required>
          <Select id="ed-type" className="min-h-11" value={type} onChange={(e) => setType(e.target.value as S["EventType"])} data-testid="ed-type">
            <option value="" />
            {items("event_types").map((x) => (
              <option key={x.code} value={x.code}>
                {label("event_types", x.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ed-response" label={t("response")} required>
          <Select id="ed-response" className="min-h-11" value={response} onChange={(e) => setResponse(e.target.value as S["ResponseType"])} data-testid="ed-response">
            <option value="" />
            {items("response_types").map((x) => (
              <option key={x.code} value={x.code}>
                {label("response_types", x.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ed-site" label={t("site")} required>
          <Select id="ed-site" className="min-h-11" value={site} onChange={(e) => (setSite(e.target.value), setZones([]))} data-testid="ed-site">
            <option value="" />
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <MultiSelect id="ed-zones" label={`${t("zones")} *`} options={opts.zones.filter((z) => z.siteId === site)} value={zones} onChange={setZones} allLabel={t("chooseZones")} testId="ed-zones" />
        <FormField id="ed-location" label={t("location")} hint={<NoNamesHint />}>
          <Input id="ed-location" value={location} onChange={(e) => setLocation(e.target.value)} maxLength={200} data-testid="ed-location" />
        </FormField>
        <FormField id="ed-casualties" label={t("casualties")} hint={t("casualtiesHint")}>
          <Input id="ed-casualties" className="min-h-11" type="number" inputMode="numeric" min={0} value={casualties} onChange={(e) => setCasualties(e.target.value)} data-testid="ed-casualties" />
        </FormField>
      </div>
      <div className="mt-3">
        <Tick id="ed-late" label={t("lateToggle")} checked={late} onChange={setLate} />
        {late ? (
          <FormField id="ed-raised" label={t("raisedAt")} hint={t("lateHint")} className="mt-2">
            <Input id="ed-raised" type="datetime-local" value={raised} max={nowLocal()} onChange={(e) => setRaised(e.target.value)} data-testid="ed-raised" />
          </FormField>
        ) : null}
      </div>
      <FormField id="ed-notes" label={t("notes")} hint={<NoNamesHint />} className="mt-3">
        <Textarea id="ed-notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} data-testid="ed-notes" />
      </FormField>
    </StepDialog>
  );
}

/* ═════════════ event detail: response → all clear → review ═════════════ */

export function EmergencyEventDetailPage({ id }: { id: string }) {
  const q = useEmergencyEvent(id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  const e = q.data;
  return <ProjectById id={e.project_id}>{(p) => <EventDetail project={p} e={e} />}</ProjectById>;
}

function EventDetail({ project, e }: { project: Project; e: Ev }) {
  const t = useTranslations("emergency.event");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const { label } = useEmRef();
  const { dateTime } = useFormatters(project.id);
  const [act, setAct] = useState<"all_clear" | "void" | null>(null);
  const path = { params: { path: { event_id: e.id } } };
  const review = (e.review ?? null) as { what_worked?: string; issues?: string; erp_update_needed?: boolean; ca_ids?: string[]; reviewed_at?: string } | null;
  const needsIncident = INCIDENT_EVENT_TYPES.includes(e.event_type);
  const editable = (e.status === "active" || e.status === "all_clear") && (caps.declare || caps.allClear);
  return (
    <div>
      <Breadcrumbs items={[{ href: "/emergency-events", label: t("events") }, { label: e.event_no }]} />
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <Code>{e.event_no}</Code>
            <EventStatusBadge status={e.status} />
            {e.late_entry ? <Badge tone="warning">{t("lateEntry")}</Badge> : null}
          </span>
        }
        description={`${label("event_types", e.event_type)} · ${label("response_types", e.response_type)}`}
        actions={
          <div className="flex flex-wrap gap-2" data-testid="event-actions">
            {e.status === "active" && caps.allClear ? (
              <Button onClick={() => setAct("all_clear")} data-testid="event-all-clear">
                {t("allClear")}
              </Button>
            ) : null}
            {e.status !== "voided" && caps.void ? (
              <Button variant="destructive-outline" onClick={() => setAct("void")} data-testid="event-void">
                {t("void")}
              </Button>
            ) : null}
          </div>
        }
      />
      <ApiWarnings warnings={e.warnings} />
      {e.muster_id ? (
        <Alert tone={e.status === "active" ? "warning" : "info"} className="mb-3" data-testid="event-muster">
          <span className="flex flex-wrap items-center gap-2">
            <Users aria-hidden className="size-4" />
            {t("muster")} <Code>{e.muster_no}</Code>
            <Button size="sm" asChild>
              <Link href={`/musters/${e.muster_id}`} data-testid="event-muster-open">
                {t("openMuster")}
              </Link>
            </Button>
          </span>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="p-4">
            <FieldList>
              <FieldItem label={t("where")}>
                <Code>{e.site_code}</Code>
                {e.zone_codes.length ? <> · {e.zone_codes.join(", ")}</> : null}
                {e.location_en ? (
                  <span dir="auto" className="block text-sm text-muted-foreground">
                    {e.location_en}
                  </span>
                ) : null}
              </FieldItem>
              <FieldItem label={t("raised")}>{dateTime(e.raised_at)}</FieldItem>
              <FieldItem label={t("declaredBy")}>
                <UserName u={e.declared_by} />
              </FieldItem>
              <FieldItem label={t("casualties")}>
                <bdi className="ltr tabular-nums" data-testid="event-casualties">
                  {e.casualties_count}
                </bdi>
              </FieldItem>
              <FieldItem label={t("incident")}>
                {e.incident_id ? (
                  <Link href={`/incidents/${e.incident_id}`} className="text-primary hover:underline" data-testid="event-incident">
                    <Code>{e.incident_ref}</Code>
                  </Link>
                ) : needsIncident ? (
                  <span className="text-warning" data-testid="event-incident-needed">
                    {t("incidentNeeded")}
                  </span>
                ) : (
                  "—"
                )}
              </FieldItem>
              {e.all_clear_at ? (
                <FieldItem label={t("allClearAt")}>
                  {dateTime(e.all_clear_at)} · <UserName u={e.all_clear_by} />
                </FieldItem>
              ) : null}
              {e.status_reason ? (
                <FieldItem label={t("statusReason")} wide>
                  <FreeText>{e.status_reason}</FreeText>
                </FieldItem>
              ) : null}
            </FieldList>
          </CardContent>
        </Card>
        <Card data-testid="event-times">
          <CardHeader>
            <CardTitle>{t("times")}</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 p-4 pt-0 sm:grid-cols-4">
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">{t("firstResponse")}</p>
              <Minutes v={e.times.first_response_min} testId="time-first" />
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">{t("total")}</p>
              <Minutes v={e.times.total_min} testId="time-total" />
            </div>
            {Object.entries(e.times.external_arrival_min).map(([a, v]) => (
              <div key={a} className="rounded-md border p-3" data-testid="time-agency" data-agency={a}>
                <p className="text-xs text-muted-foreground">{t("arrival", { agency: label("agencies", a) })}</p>
                <Minutes v={v} />
              </div>
            ))}
          </CardContent>
        </Card>
        {editable ? <ResponseForm project={project} e={e} /> : null}
        {review ? (
          <Card data-testid="event-review">
            <CardHeader>
              <CardTitle>{t("review")}</CardTitle>
              {review.reviewed_at ? <p className="text-xs text-muted-foreground">{dateTime(review.reviewed_at)}</p> : null}
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <FieldList>
                <FieldItem label={t("whatWorked")} wide>
                  <FreeText>{review.what_worked ?? ""}</FreeText>
                </FieldItem>
                <FieldItem label={t("issues")} wide>
                  <FreeText>{review.issues ?? ""}</FreeText>
                </FieldItem>
                <FieldItem label={t("erpUpdate")}>{review.erp_update_needed ? tc("yes") : tc("no")}</FieldItem>
                <FieldItem label={t("cas")}>
                  {review.ca_ids?.length
                    ? review.ca_ids.map((id) => (
                        <Link key={id} href={`/actions/${id}`} className="me-2 text-primary hover:underline" data-testid="review-ca">
                          {t("openCa")}
                        </Link>
                      ))
                    : "—"}
                </FieldItem>
              </FieldList>
            </CardContent>
          </Card>
        ) : e.status === "all_clear" && caps.review ? (
          <ReviewForm e={e} needsIncident={needsIncident} />
        ) : e.status === "all_clear" ? (
          <Alert tone="info" data-testid="review-waiting">
            {t("reviewWaiting")}
          </Alert>
        ) : null}
      </div>
      {act === "all_clear" ? (
        <AllClearDialog e={e} onClose={() => setAct(null)} />
      ) : act === "void" ? (
        <EmReasonDialog
          title={t("voidTitle", { no: e.event_no })}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/emergency-events/{event_id}/transitions", { ...path, body: { action: "void", reason } }))}
          onClose={() => setAct(null)}
        />
      ) : null}
    </div>
  );
}

function AllClearDialog({ e, onClose }: { e: Ev; onClose: () => void }) {
  const t = useTranslations("emergency.event");
  const refresh = useEmergencyRefresh();
  const [at, setAt] = useState(nowLocal());
  // Untouched → the server stamps "now" (a minute-precision local value could fall before raised_at).
  const [edited, setEdited] = useState(false);
  return (
    <StepDialog
      title={t("allClearTitle")}
      description={e.muster_id ? t("allClearHintMuster") : t("allClearHint")}
      confirmLabel={t("allClear")}
      testId="all-clear-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/emergency-events/{event_id}/transitions", { params: { path: { event_id: e.id } }, body: { action: "all_clear", at: edited ? fromLocalInput(at) : null } }));
        await refresh();
        toast.success(t("allClearDone"));
      }}
      onClose={onClose}
    >
      <FormField id="ac-at" label={t("allClearAt")}>
        <Input id="ac-at" type="datetime-local" value={at} max={nowLocal()} onChange={(x) => (setAt(x.target.value), setEdited(true))} data-testid="ac-at" />
      </FormField>
    </StepDialog>
  );
}

type Ext = { agency: Agency; called_at: string; arrived_at: string; reference: string };

function ResponseForm({ project, e }: { project: Project; e: Ev }) {
  const t = useTranslations("emergency.event");
  const { items, label } = useEmRef();
  const refresh = useEmergencyRefresh();
  const incidents = useIncidents(project.id, { site_id: [e.site_id], page_size: 50 });
  const [first, setFirst] = useState(toLocalInput(e.first_responder_at));
  const [ext, setExt] = useState<Ext[]>(() =>
    (e.external_services as { agency: Agency; called_at?: string | null; arrived_at?: string | null; reference?: string | null }[]).map((x) => ({
      agency: x.agency,
      called_at: toLocalInput(x.called_at),
      arrived_at: toLocalInput(x.arrived_at),
      reference: x.reference ?? "",
    })),
  );
  const [casualties, setCasualties] = useState(String(e.casualties_count));
  const [incident, setIncident] = useState(e.incident_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const setX = (i: number, p: Partial<Ext>) => setExt(ext.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PATCH("/api/v1/emergency-events/{event_id}", {
          params: { path: { event_id: e.id } },
          body: {
            first_responder_at: fromLocalInput(first),
            external_services: ext.map((x) => ({ agency: x.agency, called_at: fromLocalInput(x.called_at), arrived_at: fromLocalInput(x.arrived_at), reference: x.reference.trim() || null })),
            casualties_count: Number(casualties) || 0,
            incident_id: incident || null,
          },
        }),
      );
      await refresh();
      toast.success(t("saved"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card data-testid="event-response">
      <CardHeader>
        <CardTitle>{t("response")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-4 pt-0">
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField id="er-first" label={t("firstResponderAt")}>
            <Input id="er-first" type="datetime-local" step={1} value={first} onChange={(x) => setFirst(x.target.value)} data-testid="er-first" />
          </FormField>
          <FormField id="er-casualties" label={t("casualties")} hint={t("casualtiesHint")}>
            <Input id="er-casualties" type="number" inputMode="numeric" min={0} value={casualties} onChange={(x) => setCasualties(x.target.value)} data-testid="er-casualties" />
          </FormField>
          <FormField id="er-incident" label={t("incident")}>
            <Select id="er-incident" value={incident} onChange={(x) => setIncident(x.target.value)} data-testid="er-incident">
              <option value="" />
              {e.incident_id && !(incidents.data?.items ?? []).some((i) => i.id === e.incident_id) ? <option value={e.incident_id}>{e.incident_ref}</option> : null}
              {(incidents.data?.items ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.ref}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">{t("external")}</p>
          <ul className="flex flex-col gap-2">
            {ext.map((x, i) => (
              <li key={i} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[1fr_1fr_1fr_1fr_auto]" data-testid="es-row">
                <Select aria-label={t("agency")} value={x.agency} onChange={(v) => setX(i, { agency: v.target.value as Agency })} data-testid="es-agency">
                  {items("agencies").map((a) => (
                    <option key={a.code} value={a.code}>
                      {label("agencies", a.code)}
                    </option>
                  ))}
                </Select>
                <FormField id={`es-called-${i}`} label={t("calledAt")}>
                  <Input id={`es-called-${i}`} type="datetime-local" value={x.called_at} onChange={(v) => setX(i, { called_at: v.target.value })} data-testid="es-called" />
                </FormField>
                <FormField id={`es-arrived-${i}`} label={t("arrivedAt")}>
                  <Input id={`es-arrived-${i}`} type="datetime-local" value={x.arrived_at} onChange={(v) => setX(i, { arrived_at: v.target.value })} data-testid="es-arrived" />
                </FormField>
                <FormField id={`es-ref-${i}`} label={t("reference")}>
                  <Input id={`es-ref-${i}`} className="ltr" value={x.reference} onChange={(v) => setX(i, { reference: v.target.value })} maxLength={40} />
                </FormField>
                <Button variant="ghost" size="sm" aria-label={t("remove")} onClick={() => setExt(ext.filter((_, j) => j !== i))}>
                  <Trash2 aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
          <Button variant="outline" size="sm" className="mt-2" onClick={() => setExt([...ext, { agency: "civil_defense", called_at: "", arrived_at: "", reference: "" }])} data-testid="es-add">
            <Plus aria-hidden />
            {t("addAgency")}
          </Button>
        </div>
        <MutationError error={error} />
        <Button className="w-fit" onClick={() => void save()} disabled={busy} data-testid="er-save">
          {t("save")}
        </Button>
      </CardContent>
    </Card>
  );
}

function ReviewForm({ e, needsIncident }: { e: Ev; needsIncident: boolean }) {
  const t = useTranslations("emergency.event");
  const refresh = useEmergencyRefresh();
  const [worked, setWorked] = useState("");
  const [issues, setIssues] = useState("");
  const [erp, setErp] = useState(false);
  const [ca, setCa] = useState(false);
  const [caTitle, setCaTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.POST("/api/v1/emergency-events/{event_id}/review", {
          params: { path: { event_id: e.id } },
          body: { what_worked: worked.trim(), issues: issues.trim(), erp_update_needed: erp, create_ca: ca, ca_title: ca ? caTitle.trim() || null : null },
        }),
      );
      await refresh();
      toast.success(t("reviewed"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card data-testid="review-form">
      <CardHeader>
        <CardTitle>{t("review")}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("reviewHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-4 pt-0">
        {needsIncident && !e.incident_id ? (
          <Alert tone="warning" data-testid="review-incident-note">
            {t("incidentNeeded")}
          </Alert>
        ) : null}
        <FormField id="rv-worked" label={t("whatWorked")} required hint={<NoNamesHint />}>
          <Textarea id="rv-worked" value={worked} onChange={(x) => setWorked(x.target.value)} maxLength={2000} data-testid="rv-worked" />
        </FormField>
        <FormField id="rv-issues" label={t("issues")} required hint={<NoNamesHint />}>
          <Textarea id="rv-issues" value={issues} onChange={(x) => setIssues(x.target.value)} maxLength={2000} data-testid="rv-issues" />
        </FormField>
        <Tick id="rv-erp" label={t("erpUpdate")} checked={erp} onChange={setErp} />
        <Tick id="rv-ca" label={t("createCa")} checked={ca} onChange={setCa} />
        {ca ? (
          <FormField id="rv-ca-title" label={t("caTitle")}>
            <Input id="rv-ca-title" value={caTitle} onChange={(x) => setCaTitle(x.target.value)} maxLength={200} data-testid="rv-ca-title" />
          </FormField>
        ) : null}
        <MutationError error={error} />
        <Button className="w-fit" onClick={() => void submit()} disabled={busy || worked.trim().length < 5 || issues.trim().length < 5} data-testid="rv-submit">
          {t("submitReview")}
        </Button>
      </CardContent>
    </Card>
  );
}
