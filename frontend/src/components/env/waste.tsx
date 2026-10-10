"use client";
import { Ban, CheckCircle2, ClipboardCheck, Eraser, Hourglass, Lock, Plus, Scale, Truck, TriangleAlert, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { RecordActions } from "@/components/common/record-actions";
import { EmptyState, ErrorState, LoadingState, MutationError, NotFoundState } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { AnswerButtons, PrivacyNote, fromLocalInput, nowLocal } from "@/components/emergency/common";
import { StackedDate } from "@/components/medical/common";
import { DecimalInput } from "@/components/ptw/common";
import { DateFilter } from "@/components/training/common";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, api, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { useConsignment, useConsignments, useEnvProviders, useEnvRefresh, useEnvSettings, useWasteArea, useWasteAreas, useWasteStreams } from "@/lib/api/env";
import { todayInZone } from "@/lib/datetime";
import { CONSIGNMENT_STATUSES, HAZARDOUS_STORES, QUANTITY_UNITS, WASTE_ROUTES } from "@/lib/env-enums";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Check, EnvReasonDialog, EnvStatusBadge, EnvWasteSubNav, Measure, useEnvCaps, useEnvRef } from "./common";
import { PermitStatusBadge } from "./register";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

function useStreamLabel(project: Project) {
  const streams = useWasteStreams(project.id);
  const { label } = useEnvRef();
  return (code: string) => {
    const s = streams.data?.items.find((x) => x.stream_code === code);
    return s ? label("streams", code) : code;
  };
}

/* ═════════════ waste streams (§3.4, WST-1) ═════════════ */

export function WasteStreamsPage() {
  return <ProjectGate>{(p) => <Streams project={p} />}</ProjectGate>;
}

function Streams({ project }: { project: Project }) {
  const t = useTranslations("env.streams");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const q = useWasteStreams(project.id, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EnvWasteSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <Table data-testid="streams-table">
          <THead>
            <TR>
              <TH>{t("stream")}</TH>
              <TH>{t("class")}</TH>
              <TH>{t("route")}</TH>
              <TH>{t("density")}</TH>
              <TH>{t("active")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {(q.data?.items ?? []).map((s) => (
              <StreamRow key={`${s.stream_code}-${s.default_route}-${s.density}-${s.active}`} project={project} s={s} editable={caps.areas} classLabel={ref.label("waste_classes", s.waste_class)} />
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

function StreamRow({ project, s, editable, classLabel }: { project: Project; s: S["StreamRead"]; editable: boolean; classLabel: string }) {
  const t = useTranslations("env.streams");
  const tc = useTranslations("common");
  const ref = useEnvRef();
  const refresh = useEnvRefresh();
  const [route, setRoute] = useState(s.default_route);
  const [density, setDensity] = useState(s.density);
  const [active, setActive] = useState(s.active);
  const [error, setError] = useState<unknown>(null);
  const dirty = route !== s.default_route || density !== s.density || active !== s.active;
  async function save() {
    setError(null);
    try {
      await unwrap(api.PUT("/api/v1/projects/{project_id}/waste-streams/{stream_code}", { params: { path: { project_id: project.id, stream_code: s.stream_code } }, body: { default_route: route, density, active } }));
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    }
  }
  return (
    <TR data-testid="stream-row" data-code={s.stream_code} data-active={s.active}>
      <TD label={t("stream")}>
        {ref.label("streams", s.stream_code)}
        <span className="block text-xs text-muted-foreground">
          <Code>{s.stream_code}</Code>
          {s.wildlife_attractant ? ` · ${t("wildlife")}` : ""}
          {s.excluded_from_tonnage ? ` · ${t("m3Only")}` : ""}
        </span>
      </TD>
      <TD label={t("class")}>
        <Badge tone={s.waste_class === "hazardous" ? "danger" : "neutral"}>
          {s.waste_class === "hazardous" ? <TriangleAlert aria-hidden /> : null}
          {classLabel}
        </Badge>
      </TD>
      <TD label={t("route")}>
        {editable ? (
          <Select aria-label={t("route")} value={route} onChange={(e) => setRoute(e.target.value as S["WasteRoute"])}>
            {WASTE_ROUTES.map((r) => (
              <option key={r} value={r}>
                {ref.label("routes", r)}
              </option>
            ))}
          </Select>
        ) : (
          ref.label("routes", s.default_route)
        )}
      </TD>
      <TD label={t("density")}>
        {editable ? (
          <span className="flex items-center gap-1">
            <DecimalInput value={density} onChange={setDensity} className="w-24" />
            <bdi className="ltr text-xs text-muted-foreground">{s.density_unit}</bdi>
          </span>
        ) : (
          <Measure v={s.density} unit={s.density_unit} />
        )}
      </TD>
      <TD label={t("active")}>
        {editable ? (
          <Check id={`st-${s.stream_code}`} label={t("active")} checked={active} onChange={setActive} testId="stream-active" />
        ) : (
          <YesNo value={s.active} yes={tc("yes")} no={tc("no")} />
        )}
      </TD>
      <TD>
        {editable && dirty ? (
          <Button size="sm" onClick={() => void save()} data-testid="stream-save">
            {tc("save")}
          </Button>
        ) : null}
        <MutationError error={error} />
      </TD>
    </TR>
  );
}

/* ═════════════ storage areas (§3.5, WST-2…WST-5, AIR-2) ═════════════ */

export function WasteAreasPage() {
  return <ProjectGate>{(p) => <Areas project={p} />}</ProjectGate>;
}

function Areas({ project }: { project: Project }) {
  const t = useTranslations("env.areas");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const streamLabel = useStreamLabel(project);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const site = s.get("site") ?? "";
  const q = useWasteAreas(project.id, { site_id: site || null }, { enabled: caps.view });
  const [creating, setCreating] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.areas ? (
            <Button onClick={() => setCreating(true)} data-testid="area-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EnvWasteSubNav />
      <ListToolbar>
        <SelectFilter id="ar-site" label={t("site")} value={site} onChange={(v) => s.set({ site: v })} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="areas-list">
          {items.map((a) => (
            <Link key={a.id} href={`/waste-areas/${a.id}`} className="flex flex-col gap-2 rounded-md border p-4 hover:bg-muted/50" data-testid="area-card" data-code={a.area_code}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <Code className="font-semibold">{a.area_code}</Code>
                <EnvStatusBadge group="envAreaStatus" status={a.status} />
              </span>
              <span className="text-sm">
                {ref.label("storage_area_types", a.type)} · <Code>{a.zone_code ?? opts.sites.find((x) => x.value === a.site_id)?.code ?? ""}</Code>
              </span>
              <span className="text-xs text-muted-foreground">{a.accepted_streams.map(streamLabel).join(" · ")}</span>
              {a.haz_deadlines.map((d) => (
                <HazDeadlineChip key={d.stream_code} d={d} streamLabel={streamLabel} />
              ))}
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState message={site ? undefined : t("empty")} />
      )}
      {creating ? <AreaForm project={project} onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

/** Hazardous storage deadline (WST-5, §6.6): overdue red, ≤ 14 days amber, with words and icon. */
function HazDeadlineChip({ d, streamLabel, testId = "haz-deadline" }: { d: S["HazDeadline"]; streamLabel: (c: string) => string; testId?: string }) {
  const t = useTranslations("env.areas");
  const soon = !d.overdue && d.days_left <= 14;
  return (
    <span
      className={cn("inline-flex w-fit flex-wrap items-center gap-1 rounded px-2 py-1 text-xs font-medium", d.overdue ? "bg-danger-bg text-danger" : soon ? "bg-warning-bg text-warning" : "bg-muted text-muted-foreground")}
      data-testid={testId}
      data-overdue={d.overdue}
    >
      {d.overdue ? <TriangleAlert aria-hidden className="size-3.5" /> : <Hourglass aria-hidden className="size-3.5" />}
      {streamLabel(d.stream_code)}: {d.overdue ? t("overdue", { days: -d.days_left }) : t("daysLeft", { days: d.days_left })}
    </span>
  );
}

function AreaForm({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("env.areas");
  const tc = useTranslations("common");
  const ref = useEnvRef();
  const opts = useProjectOptions(project.id);
  const streams = useWasteStreams(project.id);
  const refresh = useEnvRefresh();
  const [v, setV] = useState({ area_code: "", site_id: "", zone_id: "", type: "skip" as S["StorageAreaType"], capacity_m3: "", containment: "", covered: false, lidded_secured: false, signage_bilingual: false });
  const [accepted, setAccepted] = useState<string[]>([]);
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  const haz = HAZARDOUS_STORES.includes(v.type);
  return (
    <StepDialog
      wide
      title={t("new")}
      confirmLabel={tc("save")}
      testId="area-save"
      disabled={!v.area_code || !v.site_id || !v.capacity_m3 || !accepted.length}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/projects/{project_id}/waste-storage-areas", {
            params: { path: { project_id: project.id } },
            body: {
              area_code: v.area_code,
              site_id: v.site_id,
              zone_id: v.zone_id || null,
              type: v.type,
              accepted_streams: accepted,
              capacity_m3: v.capacity_m3,
              secondary_containment_pct: v.containment ? Number(v.containment) : null,
              covered: v.covered,
              lidded_secured: v.lidded_secured,
              signage_bilingual: v.signage_bilingual,
            },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ar-code" label={t("code")} required>
          <Input className="ltr" maxLength={16} value={v.area_code} onChange={(e) => set({ area_code: e.target.value.toUpperCase() })} data-testid="ar-code" />
        </FormField>
        <FormField id="ar-type" label={t("type")} required>
          <Select value={v.type} onChange={(e) => set({ type: e.target.value as S["StorageAreaType"] })} data-testid="ar-type">
            {ref.options("storage_area_types").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ar-site-f" label={t("site")} required>
          <Select value={v.site_id} onChange={(e) => set({ site_id: e.target.value, zone_id: "" })} data-testid="ar-site">
            <option value="">{tc("select")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ar-zone" label={t("zone")}>
          <Select value={v.zone_id} onChange={(e) => set({ zone_id: e.target.value })} data-testid="ar-zone">
            <option value="">—</option>
            {opts.zones
              .filter((z) => z.siteId === v.site_id)
              .map((z) => (
                <option key={z.value} value={z.value}>
                  {z.label}
                </option>
              ))}
          </Select>
        </FormField>
        <MultiSelect
          id="ar-streams"
          label={t("streams")}
          options={(streams.data?.items ?? []).filter((x) => x.active).map((x) => ({ value: x.stream_code, label: ref.label("streams", x.stream_code) }))}
          value={accepted}
          onChange={setAccepted}
          allLabel={tc("select")}
          testId="ar-streams"
        />
        <FormField id="ar-cap" label={t("capacity")} required>
          <DecimalInput value={v.capacity_m3} onChange={(x) => set({ capacity_m3: x })} data-testid="ar-capacity" />
        </FormField>
        {haz ? (
          <FormField id="ar-cont" label={t("containment")} required hint={t("containmentHint")}>
            <Input type="number" min={0} max={300} value={v.containment} onChange={(e) => set({ containment: e.target.value })} data-testid="ar-containment" />
          </FormField>
        ) : null}
        <Check id="ar-covered" label={t("covered")} checked={v.covered} onChange={(c) => set({ covered: c })} />
        <Check id="ar-lidded" label={t("lidded")} checked={v.lidded_secured} onChange={(c) => set({ lidded_secured: c })} testId="ar-lidded" />
        <Check id="ar-signage" label={t("signage")} checked={v.signage_bilingual} onChange={(c) => set({ signage_bilingual: c })} />
      </div>
      <p className="text-xs text-muted-foreground">{t("airsideHint")}</p>
    </StepDialog>
  );
}

export function WasteAreaPage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <AreaDetail project={p} id={id} />}</ProjectGate>;
}

/** Storage area page, phone-first: the walk-round check (AIR-2 flags, WST-5 start dates) on top, evidence below (WST-4). */
function AreaDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.areas");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const streamLabel = useStreamLabel(project);
  const streams = useWasteStreams(project.id, { enabled: caps.view });
  const opts = useProjectOptions(project.id);
  const q = useWasteArea(id, { enabled: caps.view });
  const [closing, setClosing] = useState(false);
  const refresh = useEnvRefresh();
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const a = q.data;
  if (!a) return <NotFoundState />;
  const hazStreams = a.accepted_streams.filter((c) => streams.data?.items.find((x) => x.stream_code === c)?.waste_class === "hazardous");
  const answers = (a.inspection_answers ?? []).slice().sort((x, y) => Number(x.compliant) - Number(y.compliant));
  return (
    <div className="mx-auto max-w-3xl">
      <Breadcrumbs items={[{ label: t("title"), href: "/waste-areas" }, { label: a.area_code }]} />
      <PageHeader
        title={<Code>{a.area_code}</Code>}
        description={`${ref.label("storage_area_types", a.type)} · ${a.zone_code ?? opts.sites.find((x) => x.value === a.site_id)?.code ?? ""}`}
        badge={<EnvStatusBadge group="envAreaStatus" status={a.status} />}
      />
      <div className="flex flex-col gap-4">
        {a.haz_deadlines.length ? (
          <div className="flex flex-col gap-2" data-testid="haz-deadlines">
            {a.haz_deadlines.map((d) => (
              <HazDeadlineChip key={d.stream_code} d={d} streamLabel={streamLabel} />
            ))}
          </div>
        ) : null}
        {caps.areas && a.status === "active" ? <AreaCheck key={JSON.stringify([a.covered, a.lidded_secured, a.signage_bilingual, a.accumulation])} a={a} hazStreams={hazStreams} streamLabel={streamLabel} /> : null}
        <div className="grid gap-2 sm:flex sm:flex-wrap">
          <Button asChild variant="outline" className="min-h-12 sm:min-h-control">
            <Link href="/field-inspections/new" data-testid="area-run-wsa">
              <ClipboardCheck aria-hidden />
              {t("runWsa")}
            </Link>
          </Button>
          {caps.consign && a.status === "active" ? (
            <Button asChild variant="outline" className="min-h-12 sm:min-h-control">
              <Link href={`/waste-consignments/new?area=${a.id}`} data-testid="area-dispatch">
                <Truck aria-hidden />
                {t("dispatch")}
              </Link>
            </Button>
          ) : null}
        </div>
        <Card>
          <CardContent className="pt-4 sm:pt-5 sm:pt-5">
            <FieldList>
              <FieldItem label={t("streams")} wide>
                {a.accepted_streams.map(streamLabel).join(" · ")}
              </FieldItem>
              <FieldItem label={t("capacity")}>
                <Measure v={a.capacity_m3} unit="m³" />
              </FieldItem>
              <FieldItem label={t("containment")}>{a.secondary_containment_pct !== null ? <Measure v={String(a.secondary_containment_pct)} unit="%" /> : "—"}</FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("answers")}</CardTitle>
            <p className="text-xs text-muted-foreground">{t("answersHint")}</p>
          </CardHeader>
          <CardContent>
            {answers.length ? (
              <ul className="flex flex-col divide-y" data-testid="area-answers">
                {answers.map((x, i) => (
                  <li key={`${x.item_code}-${i}`} className="flex flex-wrap items-center gap-2 py-2 text-sm" data-testid="area-answer" data-compliant={x.compliant}>
                    <Badge tone={x.compliant ? "success" : "danger"}>
                      {x.compliant ? <CheckCircle2 aria-hidden /> : <TriangleAlert aria-hidden />}
                      {x.compliant ? t("compliant") : t("notCompliant")}
                    </Badge>
                    <Code>{x.item_code}</Code>
                    <Code>{x.template_code}</Code>
                    <StackedDate v={x.completed_date} projectId={project.id} />
                    {x.inspection_id ? (
                      <Link href={`/inspections/${x.inspection_id}`} className="text-primary hover:underline">
                        {t("openInspection")}
                      </Link>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message={t("noAnswers")} />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("lastConsignments")}</CardTitle>
          </CardHeader>
          <CardContent>
            {a.last_consignments?.length ? (
              <ul className="flex flex-wrap gap-2" data-testid="area-consignments">
                {a.last_consignments.map((n) => (
                  <li key={n}>
                    <Code>{n}</Code>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message={t("noConsignments")} />
            )}
          </CardContent>
        </Card>
      </div>
      {caps.areas && a.status === "active" ? (
        <RecordActions>
          <Button variant="destructive-outline" onClick={() => setClosing(true)} data-testid="area-close">
            {t("close")}
          </Button>
        </RecordActions>
      ) : null}
      {closing ? (
        <StepDialog
          title={t("closeTitle", { code: a.area_code })}
          confirmLabel={t("close")}
          destructive
          onConfirm={async () => {
            await unwrap(api.PATCH("/api/v1/waste-storage-areas/{area_id}", { params: { path: { area_id: a.id } }, body: { status: "closed" } }));
            await refresh();
          }}
          onClose={() => setClosing(false)}
        />
      ) : null}
    </div>
  );
}

/** The phone walk-round: large yes / no answers and the hazardous accumulation start dates (WST-5). */
function AreaCheck({ a, hazStreams, streamLabel }: { a: S["AreaRead"]; hazStreams: string[]; streamLabel: (c: string) => string }) {
  const t = useTranslations("env.areas");
  const td = useTranslations("envDesign");
  const tc = useTranslations("common");
  const refresh = useEnvRefresh();
  const [v0] = useState({ covered: a.covered, lidded_secured: a.lidded_secured, signage_bilingual: a.signage_bilingual });
  const [acc0] = useState<Record<string, string>>(() => Object.fromEntries(hazStreams.map((c) => [c, a.accumulation.find((x) => x.stream_code === c)?.started_on ?? ""])));
  const [v, setV] = useState(v0);
  const [acc, setAcc] = useState<Record<string, string>>(acc0);
  const [saved, setSaved] = useState(false);
  const dirty = !saved && (JSON.stringify(v) !== JSON.stringify(v0) || hazStreams.some((c) => (acc[c] ?? "") !== (acc0[c] ?? "")));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const yn = [
    { value: "yes" as const, label: tc("yes") },
    { value: "no" as const, label: tc("no") },
  ];
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PATCH("/api/v1/waste-storage-areas/{area_id}", {
          params: { path: { area_id: a.id } },
          body: { ...v, accumulation: hazStreams.length ? hazStreams.map((c) => ({ stream_code: c, started_on: acc[c] || null })) : undefined },
        }),
      );
      await refresh();
      setSaved(true);
      toast.success(t("checkSaved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const rows = [
    { k: "covered" as const, label: t("covered") },
    { k: "lidded_secured" as const, label: t("lidded") },
    { k: "signage_bilingual" as const, label: t("signage") },
  ];
  return (
    <Card data-testid="area-check">
      <CardHeader>
        <CardTitle className="text-base">{t("check")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("checkHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {rows.map((r) => (
          <div key={r.k} className={cn("flex flex-col gap-2 rounded-md border p-3", !v[r.k] && "border-s-4 border-s-warning")}>
            <span className="text-base font-medium">{r.label}</span>
            <div className="[&>div]:grid-cols-2 [&_button]:min-h-12 [&_button]:text-base">
              <AnswerButtons
                value={v[r.k] ? "yes" : "no"}
                options={yn}
                danger={["no"]}
                onChange={(x) => {
                  setSaved(false);
                  setV({ ...v, [r.k]: x === "yes" });
                }}
                testId={`check-${r.k}`}
              />
            </div>
          </div>
        ))}
        {hazStreams.length ? (
          <fieldset className="flex flex-col gap-3 rounded-md border p-3" data-testid="acc-fields">
            <legend className="px-1 text-base font-medium">{td("hazTitle")}</legend>
            <p className="-mt-1 text-xs text-muted-foreground">{t("accumulationHint")}</p>
            {hazStreams.map((c) => {
              const setAt = (x: string) => {
                setSaved(false);
                setAcc({ ...acc, [c]: x });
              };
              const d = a.haz_deadlines.find((x) => x.stream_code === c);
              return (
                <div key={c} className="flex flex-col gap-2 border-t pt-3 first-of-type:border-t-0 first-of-type:pt-0">
                  <label htmlFor={`acc-${c}`} className="text-sm font-medium" aria-label={t("accumulation", { stream: streamLabel(c) })}>
                    {streamLabel(c)}
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <Input id={`acc-${c}`} type="date" className="h-12 w-auto text-base sm:h-control sm:text-sm" value={acc[c] ?? ""} onChange={(e) => setAt(e.target.value)} data-testid={`acc-${c}`} />
                    <Button type="button" variant="outline" className="min-h-12 sm:min-h-control" onClick={() => setAt(todayInZone())}>
                      {t("today")}
                    </Button>
                    {acc[c] ? (
                      <Button type="button" variant="outline" className="min-h-12 sm:min-h-control" onClick={() => setAt("")} data-testid={`acc-clear-${c}`}>
                        <Eraser aria-hidden />
                        {td("emptiedClear")}
                      </Button>
                    ) : null}
                  </div>
                  {!acc[c] ? (
                    <span className="text-xs text-muted-foreground">{td("notStarted")}</span>
                  ) : d && acc[c] === acc0[c] ? (
                    <HazDeadlineChip d={d} streamLabel={streamLabel} testId="acc-deadline" />
                  ) : null}
                </div>
              );
            })}
          </fieldset>
        ) : null}
        <MutationError error={error} />
        {dirty ? (
          <p className="flex items-center gap-1 text-sm font-medium text-warning" data-testid="check-unsaved">
            <Hourglass aria-hidden className="size-4" />
            {td("unsaved")}
          </p>
        ) : null}
        <Button className="min-h-12 text-base sm:min-h-control sm:text-sm" disabled={busy} onClick={() => void save()} data-testid="check-save">
          {busy ? tc("saving") : t("saveCheck")}
        </Button>
      </CardContent>
    </Card>
  );
}

/* ═════════════ consignments (§3.6, §4.3, CON-1…CON-9) ═════════════ */

export function ConsignmentsPage() {
  return <ProjectGate>{(p) => <Consignments project={p} />}</ProjectGate>;
}

function Consignments({ project }: { project: Project }) {
  const t = useTranslations("env.consignments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const streamLabel = useStreamLabel(project);
  const providers = useEnvProviders({}, { enabled: caps.view });
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["ConsignmentStatus"] | "";
  const stream = s.get("stream") ?? "";
  const provider = s.get("provider") ?? "";
  const overdue = s.get("overdue") ?? "";
  const from = s.get("from") ?? "";
  const to = s.get("to") ?? "";
  const streams = useWasteStreams(project.id, { enabled: caps.view });
  const q = useConsignments(
    project.id,
    { status: status ? [status] : null, stream_code: stream || null, provider_id: provider || null, overdue: overdue ? true : null, date_from: from || null, date_to: to || null, page, page_size: PAGE_SIZE },
    { enabled: caps.view },
  );
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.consign ? (
            <Button asChild>
              <Link href="/waste-consignments/new" data-testid="consignment-new">
                <Truck aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <EnvWasteSubNav />
      <ListToolbar>
        <SelectFilter id="cn-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={CONSIGNMENT_STATUSES.map((x) => ({ value: x, label: te(`envConsignmentStatus.${x}`) }))} />
        <SelectFilter id="cn-stream" label={t("stream")} value={stream} onChange={(v) => s.set({ stream: v })} options={(streams.data?.items ?? []).filter((x) => x.active).map((x) => ({ value: x.stream_code, label: streamLabel(x.stream_code) }))} />
        <SelectFilter id="cn-provider" label={t("provider")} value={provider} onChange={(v) => s.set({ provider: v })} options={(providers.data?.items ?? []).map((p) => ({ value: p.id, label: p.provider_code }))} />
        <SelectFilter id="cn-overdue" label={t("overdue")} value={overdue} onChange={(v) => s.set({ overdue: v })} options={[{ value: "1", label: t("overdueOnly") }]} />
        <DateFilter id="cn-from" label={t("from")} value={from} onChange={(v) => s.set({ from: v })} />
        <DateFilter id="cn-to" label={t("to")} value={to} onChange={(v) => s.set({ to: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="consignments-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("stream")}</TH>
                <TH className="text-end">{t("tonnes")}</TH>
                <TH>{t("route")}</TH>
                <TH>{t("dispatched")}</TH>
                <TH>{t("dueOn")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="consignment-row" data-no={c.consignment_no} data-status={c.status}>
                  <TD label={t("no")}>
                    <Link href={`/waste-consignments/${c.id}`} className="font-medium text-primary hover:underline">
                      <Code>{c.consignment_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{c.generator_code ?? "—"}</Code>
                    </span>
                  </TD>
                  <TD label={t("stream")}>
                    {streamLabel(c.stream_code)}
                    <span className="block text-xs text-muted-foreground">
                      <Code>{c.transporter_code}</Code> → <Code>{c.facility_code ?? c.facility_provider_code}</Code>
                    </span>
                  </TD>
                  <TD label={t("tonnes")} className="text-end">
                    <Tonnes c={c} />
                  </TD>
                  <TD label={t("route")}>
                    <RouteLabel route={c.route} />
                  </TD>
                  <TD label={t("dispatched")}>
                    <StackedDate v={c.dispatched_at} time projectId={project.id} />
                  </TD>
                  <TD label={t("dueOn")}>
                    <StackedDate v={c.due_on} projectId={project.id} />
                    {c.overdue ? (
                      <Badge tone="danger" data-testid="consignment-overdue">
                        <TriangleAlert aria-hidden />
                        {t("overdue")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={tc("status")}>
                    <EnvStatusBadge group="envConsignmentStatus" status={c.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={status || stream || provider || overdue || from || to ? undefined : t("empty")} />
      )}
    </div>
  );
}

function RouteLabel({ route }: { route: S["WasteRoute"] }) {
  const { label } = useEnvRef();
  const t = useTranslations("env.consignments");
  const diverted = route === "reuse" || route === "recycle" || route === "recovery";
  return (
    <span>
      {label("routes", route)}
      {diverted ? <span className="block text-xs text-success">{t("diverted")}</span> : null}
    </span>
  );
}

/** Tonnes per §6.3: the weighbridge figure, else the estimate marked "provisional". */
function Tonnes({ c }: { c: S["ConsignmentRead"] }) {
  const t = useTranslations("env.consignments");
  if (c.waste_class === "liquid_sewage") return <Measure v={c.quantity} unit={c.unit === "m3" ? "m³" : c.unit} />;
  return (
    <span className="inline-flex flex-col items-end">
      <Measure v={c.tonnes ?? c.estimated_t} unit="t" className="font-semibold" />
      {c.provisional ? (
        <Badge tone="warning" data-testid="provisional">
          <Hourglass aria-hidden />
          {t("provisional")}
        </Badge>
      ) : null}
    </span>
  );
}

/** Facility licence activity needed per route (6e list TR). */
const ROUTE_ACTIVITY: Record<S["WasteRoute"], S["LicenceActivity"][]> = {
  reuse: ["recycling"],
  recycle: ["recycling"],
  recovery: ["recycling", "treatment"],
  treatment: ["treatment"],
  disposal_landfill: ["disposal"],
};

type LicenceFit = "ok" | "none" | "class" | "activity" | "unknown";

/**
 * CON-2 preview from the licence scopes the page already has: a licence in force covering the waste class and
 * one of the activities. Only a hint ("will be refused"); the server decides and there is no override.
 */
function licenceFit(p: S["EnvProviderRead"] | undefined, cls: S["WasteClass"] | undefined, activities: S["LicenceActivity"][]): LicenceFit {
  if (!p || !cls) return "unknown";
  const inForce = (p.licences ?? []).filter((l) => ["valid", "expiring"].includes(l.status));
  if (!inForce.length) return "none";
  const coversClass = (l: S["EnvPermitRead"]) => !l.scope.waste_classes?.length || l.scope.waste_classes.includes(cls);
  const coversActivity = (l: S["EnvPermitRead"]) => !activities.length || !l.scope.activities?.length || l.scope.activities.some((a) => activities.includes(a));
  if (inForce.some((l) => coversClass(l) && coversActivity(l))) return "ok";
  return inForce.some(coversClass) ? "activity" : "class";
}

/** Licence state of a provider for the dispatch form (CON-2, PRV-1): shown before submitting; the server decides. */
function ProviderLicenceLine({ p, fit, clsLabel }: { p: S["EnvProviderRead"] | undefined; fit: LicenceFit; clsLabel: string }) {
  const t = useTranslations("env.consignments");
  const td = useTranslations("envDesign");
  if (!p) return null;
  const lic = (p.licences ?? []).filter((l) => ["valid", "expiring"].includes(l.status));
  return (
    <span className="flex flex-col gap-1 text-xs" data-testid="provider-licence" data-ok={p.status === "approved" && lic.length > 0} data-fit={fit}>
      <span className="flex flex-wrap items-center gap-2">
        {p.status !== "approved" ? <EnvStatusBadge group="envProviderStatus" status={p.status} /> : null}
        {lic.length ? (
          lic.map((l) => <PermitStatusBadge key={l.id} p={l} />)
        ) : (
          <Badge tone="danger">
            <XCircle aria-hidden />
            {t("noValidLicence")}
          </Badge>
        )}
      </span>
      {fit === "ok" ? (
        <span className="inline-flex items-center gap-1 text-success" data-testid="licence-fit">
          <CheckCircle2 aria-hidden className="size-3.5 shrink-0" />
          {td("licenceCovers", { cls: clsLabel })}
        </span>
      ) : fit === "class" || fit === "activity" ? (
        <span className="inline-flex items-start gap-1 font-medium text-danger" data-testid="licence-fit">
          <XCircle aria-hidden className="mt-px size-3.5 shrink-0" />
          {fit === "class" ? td("licenceNotCovers", { cls: clsLabel }) : td("licenceActivityMissing")}
        </span>
      ) : null}
    </span>
  );
}

const REFUSAL_CODES = ["PROVIDER_LICENCE_INVALID", "LICENCE_SCOPE_MISMATCH", "PROVIDER_NOT_APPROVED", "PRODUCER_REGISTRATION_INVALID"];

export function NewConsignmentPage() {
  return <ProjectGate>{(p) => <NewConsignment project={p} />}</ProjectGate>;
}

function NewConsignment({ project }: { project: Project }) {
  const t = useTranslations("env.consignments");
  const td = useTranslations("envDesign");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const areaParam = s.get("area") ?? "";
  const streams = useWasteStreams(project.id, { enabled: caps.consign });
  const areas = useWasteAreas(project.id, {}, { enabled: caps.consign });
  const providers = useEnvProviders({}, { enabled: caps.consign });
  const settings = useEnvSettings(project.id, { enabled: caps.consign });
  const rejected = useConsignments(project.id, { status: ["rejected"], page_size: 50 }, { enabled: caps.consign });
  const refresh = useEnvRefresh();
  const router = useRouter();
  const area0 = (areas.data?.items ?? []).find((a) => a.id === areaParam);
  const [v, setV] = useState({
    stream_code: "",
    storage_area_id: areaParam,
    site_id: "",
    generator_engagement_id: "",
    quantity: "",
    unit: "t" as S["QuantityUnit"],
    route: "",
    transporter_id: "",
    facility_provider_id: "",
    facility_code: "",
    vehicle_plate: "",
    driver_name: "",
    driver_mobile: "",
    mwan_manifest_ref: "",
    dispatched_at: nowLocal(),
    redispatch_of_id: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<S["ConsignmentRead"] | null>(null);
  if (!caps.consign) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  const active = (streams.data?.items ?? []).filter((x) => x.active);
  const stream = active.find((x) => x.stream_code === v.stream_code);
  const areaList = (areas.data?.items ?? []).filter((a) => a.status === "active" && (!v.stream_code || a.accepted_streams.includes(v.stream_code)));
  const area = (areas.data?.items ?? []).find((a) => a.id === v.storage_area_id) ?? area0;
  const all = providers.data?.items ?? [];
  const sewage = stream?.waste_class === "liquid_sewage";
  const transporters = all.filter((p) => p.kinds.includes(sewage ? "sewage_tanker" : "transporter"));
  const facilities = all.filter((p) => p.kinds.some((k) => k === "recycler" || k === "treatment_facility" || k === "landfill"));
  const facility = all.find((p) => p.id === v.facility_provider_id);
  const transporter = all.find((p) => p.id === v.transporter_id);
  const route = (v.route || stream?.default_route || "") as S["WasteRoute"] | "";
  const cls = stream?.waste_class;
  const clsLabel = cls ? ref.label("waste_classes", cls) : "";
  const trFit = licenceFit(transporter, cls, ["collection_transport"]);
  const facFit = licenceFit(facility, cls, route && !sewage ? ROUTE_ACTIVITY[route] : []);
  const blocked = [trFit, facFit].some((f) => f === "none" || f === "class" || f === "activity") || [transporter, facility].some((p) => p && p.status !== "approved");
  const refused = error instanceof ApiError && REFUSAL_CODES.includes(error.code);
  const manifestNeeded = Boolean(stream && settings.data?.mwan_manifest_required_for.includes(stream.waste_class));
  const ready = Boolean(v.stream_code && (v.storage_area_id || v.site_id) && v.generator_engagement_id && v.quantity && v.transporter_id && v.facility_provider_id && v.vehicle_plate.trim().length >= 3 && v.dispatched_at);
  const big = "h-12 text-base sm:h-control sm:text-sm";

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/waste-consignments", {
          params: { path: { project_id: project.id } },
          body: {
            stream_code: v.stream_code,
            storage_area_id: v.storage_area_id || null,
            site_id: v.storage_area_id ? null : v.site_id || null,
            generator_engagement_id: v.generator_engagement_id,
            quantity: v.quantity,
            unit: v.unit,
            route: (v.route || stream?.default_route || null) as S["WasteRoute"] | null,
            transporter_id: v.transporter_id,
            facility_provider_id: v.facility_provider_id,
            facility_code: v.facility_code || null,
            vehicle_plate: v.vehicle_plate.trim(),
            driver_name: v.driver_name || null,
            driver_mobile: v.driver_mobile || null,
            mwan_manifest_ref: v.mwan_manifest_ref || null,
            dispatched_at: fromLocalInput(v.dispatched_at) ?? new Date().toISOString(),
            redispatch_of_id: v.redispatch_of_id || null,
          },
        }),
      );
      await refresh();
      if (r.warnings?.length) setDone(r);
      else router.push(`/waste-consignments/${r.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="mx-auto flex max-w-xl flex-col gap-4">
        <PageHeader title={t("savedTitle")} />
        <Alert tone="success" data-testid="consignment-saved">
          <Code>{done.consignment_no}</Code>
        </Alert>
        <ApiWarnings warnings={done.warnings} />
        <Button asChild className="min-h-12 sm:min-h-control">
          <Link href={`/waste-consignments/${done.id}`}>{t("open")}</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <PageHeader title={t("newTitle")} description={t("newSubtitle")} />
      <EnvWasteSubNav />
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="cn-stream-f" label={t("stream")} required>
          <Select className={big} value={v.stream_code} onChange={(e) => set({ stream_code: e.target.value, route: "", storage_area_id: area && area.accepted_streams.includes(e.target.value) ? v.storage_area_id : "" })} data-testid="cn-stream">
            <option value="">{tc("select")}</option>
            {active.map((x) => (
              <option key={x.stream_code} value={x.stream_code}>
                {ref.label("streams", x.stream_code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="cn-area" label={t("area")} hint={t("areaHint")}>
          <Select className={big} value={v.storage_area_id} onChange={(e) => set({ storage_area_id: e.target.value })} data-testid="cn-area">
            <option value="">{t("noArea")}</option>
            {areaList.map((a) => (
              <option key={a.id} value={a.id}>
                {a.area_code}
              </option>
            ))}
          </Select>
        </FormField>
        {!v.storage_area_id ? (
          <FormField id="cn-site" label={t("site")} required>
            <Select className={big} value={v.site_id} onChange={(e) => set({ site_id: e.target.value })} data-testid="cn-site">
              <option value="">{tc("select")}</option>
              {opts.sites.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="cn-gen" label={t("generator")} required>
          <Select className={big} value={v.generator_engagement_id} onChange={(e) => set({ generator_engagement_id: e.target.value })} data-testid="cn-generator">
            <option value="">{tc("select")}</option>
            {opts.engagements.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="grid grid-cols-[1fr_6rem] gap-2">
          <FormField id="cn-qty" label={t("quantity")} required>
            <DecimalInput id="cn-qty" value={v.quantity} onChange={(x) => set({ quantity: x })} className={big} data-testid="cn-quantity" />
          </FormField>
          <FormField id="cn-unit" label={t("unit")} required>
            <Select className={big} value={v.unit} onChange={(e) => set({ unit: e.target.value as S["QuantityUnit"] })} data-testid="cn-unit">
              {QUANTITY_UNITS.map((u) => (
                <option key={u} value={u}>
                  {u === "m3" ? "m³" : u}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
        <FormField id="cn-route" label={t("route")} hint={stream ? t("routeDefault", { route: ref.label("routes", stream.default_route) }) : undefined}>
          <Select className={big} value={v.route || stream?.default_route || ""} onChange={(e) => set({ route: e.target.value })} data-testid="cn-route">
            <option value="">—</option>
            {WASTE_ROUTES.map((r) => (
              <option key={r} value={r}>
                {ref.label("routes", r)}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="flex flex-col gap-1">
          <FormField id="cn-tr" label={t("transporter")} required>
            <Select className={big} value={v.transporter_id} onChange={(e) => set({ transporter_id: e.target.value })} data-testid="cn-transporter">
              <option value="">{tc("select")}</option>
              {transporters.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.provider_code}
                </option>
              ))}
            </Select>
          </FormField>
          <ProviderLicenceLine p={transporter} fit={trFit} clsLabel={clsLabel} />
        </div>
        <div className="flex flex-col gap-1">
          <FormField id="cn-fac" label={t("facility")} required>
            <Select className={big} value={v.facility_provider_id} onChange={(e) => set({ facility_provider_id: e.target.value, facility_code: "" })} data-testid="cn-facility">
              <option value="">{tc("select")}</option>
              {facilities.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.provider_code}
                </option>
              ))}
            </Select>
          </FormField>
          <ProviderLicenceLine p={facility} fit={facFit} clsLabel={clsLabel} />
        </div>
        {facility && facility.facilities.length > 1 ? (
          <FormField id="cn-fcode" label={t("facilitySite")}>
            <Select className={big} value={v.facility_code} onChange={(e) => set({ facility_code: e.target.value })}>
              <option value="">—</option>
              {facility.facilities.map((f) => (
                <option key={f.facility_code} value={f.facility_code}>
                  {f.facility_code}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="cn-at" label={t("dispatchedAt")} required hint={t("dispatchedHint")}>
          <Input id="cn-at" type="datetime-local" dir="ltr" className={big} value={v.dispatched_at} onChange={(e) => set({ dispatched_at: e.target.value })} data-testid="cn-at" />
        </FormField>
      </div>
      <fieldset className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
        <legend className="px-1 text-sm font-medium">{t("vehicle")}</legend>
        <p className="text-xs text-muted-foreground sm:col-span-2">
          <Lock aria-hidden className="me-1 inline size-3.5" />
          {t("vehicleHint")}
        </p>
        <FormField id="cn-plate" label={t("plate")} required>
          <Input id="cn-plate" dir="ltr" maxLength={12} className={big} value={v.vehicle_plate} onChange={(e) => set({ vehicle_plate: e.target.value })} data-testid="cn-plate" />
        </FormField>
        <FormField id="cn-manifest" label={t("manifest")} required={manifestNeeded} hint={manifestNeeded ? t("manifestNeeded") : t("manifestOptional")}>
          <Input id="cn-manifest" dir="ltr" maxLength={40} className={big} value={v.mwan_manifest_ref} onChange={(e) => set({ mwan_manifest_ref: e.target.value })} data-testid="cn-manifest" />
        </FormField>
        <FormField id="cn-driver" label={t("driver")} hint={t("driverHint")}>
          <Input id="cn-driver" maxLength={120} className={big} value={v.driver_name} onChange={(e) => set({ driver_name: e.target.value })} data-testid="cn-driver" />
        </FormField>
        <FormField id="cn-mobile" label={t("mobile")}>
          <Input id="cn-mobile" dir="ltr" inputMode="tel" maxLength={15} className={big} value={v.driver_mobile} onChange={(e) => set({ driver_mobile: e.target.value })} />
        </FormField>
      </fieldset>
      {(rejected.data?.items ?? []).length ? (
        <FormField id="cn-redispatch" label={t("redispatchOf")}>
          <Select className={big} value={v.redispatch_of_id} onChange={(e) => set({ redispatch_of_id: e.target.value })}>
            <option value="">—</option>
            {(rejected.data?.items ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.consignment_no}
              </option>
            ))}
          </Select>
        </FormField>
      ) : null}
      <p className="text-xs text-muted-foreground">{t("noOverride")}</p>
      {blocked && !refused ? (
        <Alert tone="danger" data-testid="cn-precheck">
          <span className="flex items-start gap-2">
            <Ban aria-hidden className="mt-0.5 size-4 shrink-0" />
            <span className="flex flex-col gap-1">
              <span className="font-semibold">{td("precheckTitle")}</span>
              <span>{td("refusedFix")}</span>
            </span>
          </span>
        </Alert>
      ) : null}
      {refused ? (
        <div className="flex items-start gap-2 text-sm font-semibold text-danger" data-testid="cn-refused">
          <Ban aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span className="flex flex-col gap-1">
            {td("refusedTitle")}
            <span className="font-normal text-foreground">{td("refusedFix")}</span>
          </span>
        </div>
      ) : null}
      <MutationError error={error} />
      <Button className="min-h-12 text-base sm:min-h-control sm:text-sm" disabled={!ready || busy} onClick={() => void save()} data-testid="cn-save">
        <Truck aria-hidden />
        {busy ? tc("saving") : t("dispatchSave")}
      </Button>
    </div>
  );
}

export function ConsignmentPage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <ConsignmentDetail project={p} id={id} />}</ProjectGate>;
}

function ConsignmentDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.consignments");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const streamLabel = useStreamLabel(project);
  const settings = useEnvSettings(project.id, { enabled: caps.view });
  const refresh = useEnvRefresh();
  const q = useConsignment(id, { enabled: caps.view });
  const [dialog, setDialog] = useState<"" | "receipt" | "close" | "reject" | "void" | "edit">("");
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data;
  if (!c) return <NotFoundState />;
  const voidable = c.status !== "closed" && c.status !== "voided";
  const transition = async (action: S["ConsignmentAction"], p: { reason?: string; discrepancy_reason?: string } = {}) => {
    await unwrap(api.POST("/api/v1/waste-consignments/{consignment_id}/transitions", { params: { path: { consignment_id: c.id } }, body: { action, reason: p.reason ?? null, discrepancy_reason: p.discrepancy_reason ?? null } }));
    await refresh();
  };
  const limit = Number(settings.data?.weight_discrepancy_pct ?? "10");
  const bigGap = c.discrepancy_pct !== null && Number(c.discrepancy_pct) > limit;
  const hidden = c.vehicle_plate === null && c.driver_name === null;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/waste-consignments" }, { label: c.consignment_no }]} />
      <PageHeader
        title={<Code>{c.consignment_no}</Code>}
        description={`${streamLabel(c.stream_code)} · ${ref.label("waste_classes", c.waste_class)}`}
        badge={<EnvStatusBadge group="envConsignmentStatus" status={c.status} />}
        actions={
          <>
            {c.status === "dispatched" && (caps.consign || caps.close) ? (
              <Button onClick={() => setDialog("receipt")} data-testid="consignment-receipt">
                <Scale aria-hidden />
                {t("recordReceipt")}
              </Button>
            ) : null}
            {c.status === "received" && caps.close ? (
              <Button onClick={() => setDialog("close")} data-testid="consignment-close">
                {t("close")}
              </Button>
            ) : null}
            {(c.status === "dispatched" || c.status === "received") && caps.consign ? (
              <Button variant="outline" onClick={() => setDialog("edit")} data-testid="consignment-edit">
                {tc("edit")}
              </Button>
            ) : null}
          </>
        }
      />
      {c.overdue ? (
        <Alert tone="danger" className="mb-4" data-testid="consignment-overdue">
          {t("overdueHint")}
        </Alert>
      ) : null}
      <ApiWarnings warnings={c.warnings} className="mb-4" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dispatch")}</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldList className="lg:grid-cols-2">
              <FieldItem label={t("generator")}>
                <Code>{c.generator_code ?? "—"}</Code>
              </FieldItem>
              <FieldItem label={t("quantity")}>
                <Measure v={c.quantity} unit={c.unit === "m3" ? "m³" : c.unit} />
              </FieldItem>
              <FieldItem label={t("estimated")}>
                <Measure v={c.estimated_t} unit="t" />
              </FieldItem>
              <FieldItem label={t("route")}>
                <RouteLabel route={c.route} />
              </FieldItem>
              <FieldItem label={t("transporter")}>
                <Code>{c.transporter_code}</Code>
              </FieldItem>
              <FieldItem label={t("facility")}>
                <Code>{c.facility_code ?? c.facility_provider_code}</Code>
              </FieldItem>
              <FieldItem label={t("dispatchedAt")}>
                <StackedDate v={c.dispatched_at} time projectId={project.id} />
              </FieldItem>
              <FieldItem label={t("dueOn")}>
                <StackedDate v={c.due_on} projectId={project.id} />
              </FieldItem>
              <FieldItem label={t("manifest")}>{c.mwan_manifest_ref ? <Code>{c.mwan_manifest_ref}</Code> : "—"}</FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("receipt")}</CardTitle>
          </CardHeader>
          <CardContent>
            {c.received_at ? (
              <FieldList className="lg:grid-cols-2">
                <FieldItem label={t("receivedAt")}>
                  <StackedDate v={c.received_at} time projectId={project.id} />
                </FieldItem>
                <FieldItem label={t("netT")}>
                  <span data-testid="received-net">
                    <Measure v={c.received_net_t} unit="t" className="font-semibold" />
                  </span>
                </FieldItem>
                <FieldItem label={t("ticket")}>{c.ticket_ref ? <Code>{c.ticket_ref}</Code> : "—"}</FieldItem>
                <FieldItem label={t("discrepancy")}>
                  <span data-testid="discrepancy" className={cn(bigGap && "font-semibold text-danger")}>
                    <Measure v={c.discrepancy_pct} unit="%" />
                  </span>
                  {bigGap ? <span className="block text-xs text-danger">{t("discrepancyOver", { pct: String(limit) })}</span> : null}
                </FieldItem>
                <FieldItem label={t("recordedAt")}>
                  <StackedDate v={c.receipt_recorded_at} time projectId={project.id} />
                </FieldItem>
                {c.discrepancy_reason ? (
                  <FieldItem label={t("discrepancyReason")} wide>
                    <span dir="auto">{c.discrepancy_reason}</span>
                  </FieldItem>
                ) : null}
              </FieldList>
            ) : (
              <p className="text-sm text-muted-foreground">
                {t("noReceipt")} <Tonnes c={c} />
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("vehicle")}</CardTitle>
          </CardHeader>
          <CardContent>
            {hidden ? (
              <PrivacyNote testId="driver-hidden">{t("vehicleHidden")}</PrivacyNote>
            ) : (
              <FieldList className="lg:grid-cols-2">
                <FieldItem label={t("plate")}>{c.vehicle_plate ? <bdi className="ltr">{c.vehicle_plate}</bdi> : "—"}</FieldItem>
                <FieldItem label={t("driver")}>{c.driver_name ?? "—"}</FieldItem>
                <FieldItem label={t("mobile")}>{c.driver_mobile ? <bdi className="ltr">{c.driver_mobile}</bdi> : "—"}</FieldItem>
              </FieldList>
            )}
          </CardContent>
        </Card>
        {c.rejection_reason || c.status_reason || c.ca_id ? (
          <Card>
            <CardContent className="pt-4 sm:pt-5 sm:pt-5">
              <FieldList className="lg:grid-cols-2">
                {c.rejection_reason ? (
                  <FieldItem label={t("rejectionReason")} wide>
                    <span dir="auto">{c.rejection_reason}</span>
                  </FieldItem>
                ) : null}
                {c.status_reason ? (
                  <FieldItem label={t("reason")} wide>
                    <span dir="auto">{c.status_reason}</span>
                  </FieldItem>
                ) : null}
                {c.ca_id ? (
                  <FieldItem label={t("ca")}>
                    <Link href={`/actions/${c.ca_id}`} className="text-primary hover:underline">
                      {t("openCa")}
                    </Link>
                  </FieldItem>
                ) : null}
              </FieldList>
            </CardContent>
          </Card>
        ) : null}
      </div>
      {(c.status === "dispatched" && caps.close) || (voidable && caps.void) ? (
        <RecordActions>
          {c.status === "dispatched" && caps.close ? (
            <Button variant="destructive-outline" onClick={() => setDialog("reject")} data-testid="consignment-reject">
              {t("reject")}
            </Button>
          ) : null}
          {voidable && caps.void ? (
            <Button variant="destructive-outline" onClick={() => setDialog("void")} data-testid="consignment-void">
              {t("void")}
            </Button>
          ) : null}
        </RecordActions>
      ) : null}
      {dialog === "receipt" ? <ReceiptDialog c={c} onClose={() => setDialog("")} /> : null}
      {dialog === "close" ? <CloseDialog c={c} needReason={bigGap} onConfirm={(r) => transition("close", { discrepancy_reason: r || undefined })} onClose={() => setDialog("")} /> : null}
      {dialog === "reject" ? <EnvReasonDialog title={t("rejectTitle", { no: c.consignment_no })} description={t("rejectHint")} confirmLabel={t("reject")} onConfirm={(r) => transition("reject", { reason: r })} onClose={() => setDialog("")} /> : null}
      {dialog === "void" ? <EnvReasonDialog title={t("voidTitle", { no: c.consignment_no })} description={t("voidHint")} confirmLabel={t("void")} onConfirm={(r) => transition("void", { reason: r })} onClose={() => setDialog("")} /> : null}
      {dialog === "edit" ? <EditVehicle c={c} onClose={() => setDialog("")} /> : null}
    </div>
  );
}

/** Weighbridge receipt (CON-6): date, net tonnes, ticket number and the ticket photo / PDF. */
function ReceiptDialog({ c, onClose }: { c: S["ConsignmentRead"]; onClose: () => void }) {
  const t = useTranslations("env.consignments");
  const refresh = useEnvRefresh();
  const [at, setAt] = useState(nowLocal());
  const [net, setNet] = useState("");
  const [ticket, setTicket] = useState("");
  const [file, setFile] = useState<File | null>(null);
  return (
    <StepDialog
      title={t("receiptTitle", { no: c.consignment_no })}
      description={t("receiptHint")}
      confirmLabel={t("recordReceipt")}
      disabled={!at || !net || !ticket || !file}
      testId="receipt-save"
      onConfirm={async () => {
        const form = new FormData();
        form.set("owner_type", "consignment_ticket");
        form.set("owner_id", c.id);
        form.set("file", file as File);
        const att = await postForm<S["AttachmentRead"]>("/api/v1/attachments", form);
        await unwrap(
          api.POST("/api/v1/waste-consignments/{consignment_id}/receipt", {
            params: { path: { consignment_id: c.id } },
            body: { received_at: fromLocalInput(at) ?? new Date().toISOString(), received_net_t: net, ticket_ref: ticket, ticket_file_id: att.id },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="rc-at" label={t("receivedAt")} required>
        <Input id="rc-at" type="datetime-local" dir="ltr" value={at} onChange={(e) => setAt(e.target.value)} data-testid="rc-at" />
      </FormField>
      <FormField id="rc-net" label={t("netT")} required hint={t("estimatedWas", { t: c.estimated_t })}>
        <DecimalInput id="rc-net" value={net} onChange={setNet} data-testid="rc-net" />
      </FormField>
      <FormField id="rc-ticket" label={t("ticket")} required>
        <Input id="rc-ticket" dir="ltr" maxLength={40} value={ticket} onChange={(e) => setTicket(e.target.value)} data-testid="rc-ticket" />
      </FormField>
      <FormField id="rc-file" label={t("ticketFile")} required hint={t("ticketFileHint")}>
        <Input id="rc-file" type="file" accept="image/*,application/pdf" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="rc-file" />
      </FormField>
    </StepDialog>
  );
}

function CloseDialog({ c, needReason, onConfirm, onClose }: { c: S["ConsignmentRead"]; needReason: boolean; onConfirm: (r: string) => Promise<unknown>; onClose: () => void }) {
  const t = useTranslations("env.consignments");
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("closeTitle", { no: c.consignment_no })}
      description={needReason ? t("closeReasonHint") : t("closeHint")}
      confirmLabel={t("close")}
      testId="close-confirm"
      disabled={needReason && reason.trim().length < 20}
      onConfirm={() => onConfirm(reason.trim())}
      onClose={onClose}
    >
      <FormField id="cl-reason" label={t("discrepancyReason")} required={needReason} hint={needReason ? t("reasonMin", { n: reason.trim().length }) : undefined}>
        <Input id="cl-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="cl-reason" />
      </FormField>
    </StepDialog>
  );
}

function EditVehicle({ c, onClose }: { c: S["ConsignmentRead"]; onClose: () => void }) {
  const t = useTranslations("env.consignments");
  const tc = useTranslations("common");
  const refresh = useEnvRefresh();
  const [v, setV] = useState({ vehicle_plate: c.vehicle_plate ?? "", driver_name: c.driver_name ?? "", driver_mobile: c.driver_mobile ?? "", mwan_manifest_ref: c.mwan_manifest_ref ?? "" });
  return (
    <StepDialog
      title={t("editTitle", { no: c.consignment_no })}
      confirmLabel={tc("save")}
      onConfirm={async () => {
        await unwrap(
          api.PATCH("/api/v1/waste-consignments/{consignment_id}", {
            params: { path: { consignment_id: c.id } },
            body: { vehicle_plate: v.vehicle_plate || null, driver_name: v.driver_name || null, driver_mobile: v.driver_mobile || null, mwan_manifest_ref: v.mwan_manifest_ref || null },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="ev-plate" label={t("plate")}>
        <Input dir="ltr" value={v.vehicle_plate} onChange={(e) => setV({ ...v, vehicle_plate: e.target.value })} />
      </FormField>
      <FormField id="ev-driver" label={t("driver")}>
        <Input value={v.driver_name} onChange={(e) => setV({ ...v, driver_name: e.target.value })} />
      </FormField>
      <FormField id="ev-mobile" label={t("mobile")}>
        <Input dir="ltr" value={v.driver_mobile} onChange={(e) => setV({ ...v, driver_mobile: e.target.value })} />
      </FormField>
      <FormField id="ev-manifest" label={t("manifest")}>
        <Input dir="ltr" value={v.mwan_manifest_ref} onChange={(e) => setV({ ...v, mwan_manifest_ref: e.target.value })} />
      </FormField>
    </StepDialog>
  );
}
