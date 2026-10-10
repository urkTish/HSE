"use client";
import { CheckCircle2, CloudFog, Plane, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
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
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { RecordActions } from "@/components/common/record-actions";
import { EmptyState, ErrorState, LoadingState, MutationError, NotFoundState } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { fromLocalInput, nowLocal, toLocalInput } from "@/components/emergency/common";
import { PhotoPicker } from "@/components/field/common";
import { ChoiceMark } from "@/components/heat/common";
import { StackedDate } from "@/components/medical/common";
import { DecimalInput } from "@/components/ptw/common";
import { DateFilter } from "@/components/training/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import {
  useBackgrounds,
  useDischargeDays,
  useEnvInstruments,
  useEnvPermits,
  useEnvPoint,
  useEnvPoints,
  useEnvProviders,
  useEnvReadings,
  useEnvRefresh,
  useExceedance,
  useExceedances,
  useWaterEntries,
} from "@/lib/api/env";
import { EXCEEDANCE_STATUSES } from "@/lib/env-enums";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { BackgroundBadge, Check, EnvMonitorSubNav, EnvReasonDialog, EnvStatusBadge, LimitBar, Measure, NoNamesHint, ResultBadge, StillNeeded, useBi, useEnvCaps, useEnvRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

/* ═════════════ readings register (§3.10) ═════════════ */

export function EnvReadingsPage() {
  return <ProjectGate>{(p) => <Readings project={p} />}</ProjectGate>;
}

function Readings({ project }: { project: Project }) {
  const t = useTranslations("env.readings");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const point = s.get("point") ?? "";
  const parameter = (s.get("parameter") ?? "") as S["Parameter"] | "";
  const day = s.get("day") ?? "";
  const points = useEnvPoints(project.id, { enabled: caps.view });
  const q = useEnvReadings(
    project.id,
    { point_id: point || null, parameter: parameter || null, date_from: day || null, date_to: day || null, page, page_size: PAGE_SIZE },
    { enabled: caps.view },
  );
  const [voiding, setVoiding] = useState<S["EnvReadingRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.reading ? (
            <Button asChild className="min-h-12 sm:min-h-control">
              <Link href="/env-readings/new" data-testid="reading-new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <EnvMonitorSubNav />
      <ListToolbar>
        <SelectFilter id="rd-point" label={t("point")} value={point} onChange={(v) => s.set({ point: v })} options={(points.data?.items ?? []).map((p) => ({ value: p.id, label: p.point_code }))} />
        <SelectFilter id="rd-param" label={t("parameter")} value={parameter} onChange={(v) => s.set({ parameter: v })} options={ref.options("parameters")} />
        <DateFilter id="rd-day" label={t("day")} value={day} onChange={(v) => s.set({ day: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="readings-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("point")}</TH>
                <TH>{t("window")}</TH>
                <TH>{t("source")}</TH>
                <TH className="text-end">{t("value")}</TH>
                <TH>{t("result")}</TH>
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="reading-row" data-no={r.reading_no} data-result={r.result}>
                  <TD label={t("no")}>
                    <Code className="text-xs">{r.reading_no}</Code>
                  </TD>
                  <TD label={t("point")}>
                    <Code>{r.point_code}</Code>
                    <span className="block text-xs text-muted-foreground">
                      {ref.label("parameters", r.parameter)} · {ref.label("averaging", r.averaging)}
                      {r.period !== "any" ? ` · ${ref.label("period", r.period)}` : ""}
                    </span>
                  </TD>
                  <TD label={t("window")}>
                    <StackedDate v={r.window_end} time projectId={project.id} />
                    {r.late_entry ? <Badge tone="neutral">{t("late")}</Badge> : null}
                  </TD>
                  <TD label={t("source")}>{t(`src.${r.source}`)}</TD>
                  <TD label={t("value")} className="text-end font-semibold">
                    <bdi className="ltr tabular-nums">{r.display}</bdi>
                    {r.limit_value ? (
                      <span className="block text-xs font-normal text-muted-foreground">
                        {t("limit")} <bdi className="ltr">{r.limit_value}</bdi>
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("result")}>
                    <ResultBadge result={r.result} background={r.background} />
                    {r.exceedance_id ? (
                      <Link href={`/env-exceedances/${r.exceedance_id}`} className="block text-xs text-primary hover:underline">
                        {t("openExceedance")}
                      </Link>
                    ) : null}
                  </TD>
                  <TD label={tc("status")}>
                    <EnvStatusBadge group="envRecordState" status={r.status} />
                  </TD>
                  <TD>
                    {caps.void && r.status === "valid" && r.source !== "derived" ? (
                      <Button size="sm" variant="destructive-outline" onClick={() => setVoiding(r)} data-testid="reading-void">
                        {t("void")}
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={point || parameter || day ? undefined : t("empty")} />
      )}
      {voiding ? (
        <EnvReasonDialog
          title={t("voidTitle", { no: voiding.reading_no })}
          description={t("voidHint")}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/env-readings/{reading_id}/void", { params: { path: { reading_id: voiding.id } }, body: { reason } }))}
          onClose={() => setVoiding(null)}
        />
      ) : null}
    </div>
  );
}

/* ═════════════ phone reading entry (MON-3, §6.2) ═════════════ */

const LAST_KEY = "hse.env.lastPoint";
function readLast(): string {
  try {
    return window.localStorage.getItem(LAST_KEY) ?? "";
  } catch {
    return "";
  }
}
function writeLast(v: string) {
  try {
    window.localStorage.setItem(LAST_KEY, v);
  } catch {
    /* storage blocked: no default next time */
  }
}

/** Default window for an averaging: 1 h, 24 h, 15 min for a measurement, 1 min for a spot check. */
function windowStart(endLocal: string, averaging: S["Averaging"]): string {
  const end = fromLocalInput(endLocal);
  if (!end) return "";
  const ms = { "15min": 15, "1h": 60, "24h": 1440, measurement: 15, spot: 1 }[averaging] * 60_000;
  return toLocalInput(new Date(Date.parse(end) - ms).toISOString());
}

export function NewEnvReadingPage() {
  return <ProjectGate>{(p) => <NewReading project={p} />}</ProjectGate>;
}

function NewReading({ project }: { project: Project }) {
  const t = useTranslations("env.entry");
  const td = useTranslations("envDesign");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const refresh = useEnvRefresh();
  const s = useSearchState();
  const points = useEnvPoints(project.id, { enabled: caps.reading });
  const instruments = useEnvInstruments(project.id, { enabled: caps.reading });
  const labs = useEnvProviders({ kind: "environmental_lab" }, { enabled: caps.reading });
  const active = (points.data?.items ?? []).filter((p) => p.active && p.source_kind !== "station");
  const [last] = useState(readLast);
  const [pointSel, setPoint] = useState("");
  const pointId = pointSel || s.get("point") || (active.some((p) => p.id === last) ? last : "");
  const point = active.find((p) => p.id === pointId);
  // One choice per parameter × averaging (day / night rows share one reading; the server picks the period).
  const reqs = (point?.requirements ?? []).filter((r, i, a) => r.averaging !== "15min" && a.findIndex((x) => x.parameter === r.parameter && x.averaging === r.averaging) === i);
  const [reqSel, setReq] = useState("");
  const req = reqs.find((r) => `${r.parameter}|${r.averaging}` === reqSel) ?? (reqs.length === 1 ? reqs[0] : undefined);
  const [lab, setLab] = useState(false);
  const [end, setEnd] = useState(nowLocal());
  const [startSel, setStart] = useState("");
  const start = startSel || (req ? windowStart(end, req.averaging) : "");
  const [value, setValue] = useState("");
  const [instSel, setInstrument] = useState("");
  const usable = (instruments.data?.items ?? []).filter((i) => i.status === "active");
  const instrumentId = instSel || point?.instrument_id || (usable.length === 1 ? usable[0]!.id : "");
  const [labId, setLabId] = useState("");
  const [labRef, setLabRef] = useState("");
  const [fieldCal, setFieldCal] = useState(false);
  const [photos, setPhotos] = useState<S["PhotoInput"][]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<S["EnvReadingRead"] | null>(null);
  if (!caps.reading) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const visual = req?.parameter === "visual_dust";
  const laeq = req?.parameter === "laeq";
  const unit = ref.unit(req?.parameter);
  const ready = Boolean(point && req && start && end && value !== "" && (visual || lab ? true : instrumentId) && (!lab || (labId && labRef)) && (!laeq || lab || fieldCal));
  // The same conditions as `ready`, in words, so the field user sees why Save is greyed out.
  const missing = !point
    ? [td("need.point")]
    : !req
      ? [td("need.what")]
      : [
          value === "" ? td(visual ? "need.score" : "need.value") : "",
          !start || !end ? td("need.window") : "",
          !visual && !lab && !instrumentId ? td("need.instrument") : "",
          lab && !(labId && labRef) ? td("need.lab") : "",
          laeq && !lab && !fieldCal ? td("need.fieldCal") : "",
        ].filter(Boolean);

  async function save() {
    if (!point || !req) return;
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/env-readings", {
          params: { path: { project_id: project.id } },
          body: {
            point_id: point.id,
            parameter: req.parameter,
            averaging: req.averaging,
            window_start: fromLocalInput(start) ?? "",
            window_end: fromLocalInput(end) ?? "",
            value,
            instrument_id: visual || lab ? null : instrumentId || null,
            lab_provider_id: lab ? labId : null,
            lab_report_ref: lab ? labRef : null,
            field_calibration_checked: laeq && !lab ? fieldCal : null,
            photos,
          },
        }),
      );
      writeLast(point.id);
      setDone(r);
      await refresh();
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
        <Card data-testid="reading-saved" data-result={done.result} data-background={done.background}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckCircle2 aria-hidden className="size-5 text-success" />
              <Code>{done.reading_no}</Code>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <span className="text-3xl font-bold" data-testid="saved-value">
              <bdi className="ltr tabular-nums">{done.display}</bdi>
            </span>
            <ResultBadge result={done.result} background={done.background} />
            {done.limit_value ? (
              <span className="text-sm text-muted-foreground">
                {t("limitWas")} <Measure v={done.limit_value} unit={unit} />
              </span>
            ) : null}
            {done.result === "exceedance" && !done.background ? <Alert tone="danger">{t("exceedanceRaised")}</Alert> : null}
            {done.background ? (
              <Alert tone="info" data-testid="background-note">
                {t("backgroundNote", { ref: done.background_ref ?? "" })}
              </Alert>
            ) : null}
            {done.late_entry ? <Alert tone="info">{t("lateEntry")}</Alert> : null}
            <ApiWarnings warnings={done.warnings} />
            {done.exceedance_id ? (
              <Link href={`/env-exceedances/${done.exceedance_id}`} className="text-primary hover:underline" data-testid="saved-exceedance">
                {t("openExceedance")}
              </Link>
            ) : null}
          </CardContent>
        </Card>
        <div className="grid gap-2 sm:flex">
          <Button
            className="min-h-12 sm:min-h-control"
            onClick={() => {
              setDone(null);
              setValue("");
              setPhotos([]);
              setFieldCal(false);
              setEnd(nowLocal());
              setStart("");
            }}
            data-testid="reading-another"
          >
            <Plus aria-hidden />
            {t("another")}
          </Button>
          <Button asChild variant="outline" className="min-h-12 sm:min-h-control">
            <Link href="/env-readings">{t("toRegister")}</Link>
          </Button>
        </div>
      </div>
    );
  }

  const big = "h-12 text-lg sm:h-control sm:text-sm";
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">
          {t("point")} <span className="text-danger">*</span>
        </legend>
        <div role="radiogroup" aria-label={t("point")} className="grid gap-2 sm:grid-cols-2" data-testid="rd-points">
          {active.map((p) => {
            const on = p.id === pointId;
            return (
              <Button
                key={p.id}
                type="button"
                role="radio"
                aria-checked={on}
                variant={on ? "default" : "outline"}
                className="h-auto min-h-12 justify-start gap-2 py-2 text-start"
                onClick={() => {
                  setPoint(p.id);
                  setReq("");
                  setStart("");
                }}
                data-testid={`rd-point-${p.point_code}`}
              >
                <ChoiceMark on={on} />
                <span className="flex min-w-0 flex-col">
                  <span className="flex items-center gap-1 font-semibold">
                    <bdi className="ltr">{p.point_code}</bdi>
                    {p.airside ? <Plane aria-label={t("airside")} className="size-4" /> : null}
                  </span>
                  <span className="text-xs font-normal opacity-80">
                    {ref.label("point_kinds", p.kind)}
                    {p.zone_code ? ` · ${p.zone_code}` : ""}
                  </span>
                </span>
              </Button>
            );
          })}
        </div>
      </fieldset>
      {point && reqs.length > 1 ? (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">{t("what")}</legend>
          <div role="radiogroup" aria-label={t("what")} className="grid gap-2 sm:grid-cols-2">
            {reqs.map((r) => {
              const k = `${r.parameter}|${r.averaging}`;
              const on = req === r;
              return (
                <Button
                  key={k}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  variant={on ? "default" : "outline"}
                  className="min-h-12 justify-start gap-2"
                  onClick={() => {
                    setReq(k);
                    setStart("");
                  }}
                  data-testid={`rd-req-${r.parameter}-${r.averaging}`}
                >
                  <ChoiceMark on={on} />
                  {ref.label("parameters", r.parameter)} · {ref.label("averaging", r.averaging)}
                </Button>
              );
            })}
          </div>
        </fieldset>
      ) : null}
      {req ? (
        <>
          <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1 rounded-md border bg-muted/30 px-3 py-2" data-testid="rd-limit">
            <span className="text-sm text-muted-foreground">
              {ref.label("parameters", req.parameter)} · {ref.label("averaging", req.averaging)}
            </span>
            {req.effective_limit ? (
              <span className="flex flex-wrap items-baseline gap-x-3 text-sm">
                {req.alert_value ? (
                  <span className="text-muted-foreground">
                    {td("alertAt")} <Measure v={req.alert_value} unit={unit} />
                  </span>
                ) : null}
                <span>
                  {td("limitInForce")} <Measure v={req.effective_limit} unit={unit} className="text-lg font-semibold" />
                </span>
              </span>
            ) : null}
          </div>
          {!visual ? <Check id="rd-lab" label={t("labResult")} checked={lab} onChange={setLab} testId="rd-lab" /> : null}
          {visual ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium">
                {t("visualScore")} <span className="text-danger">*</span>
              </legend>
              <div role="radiogroup" aria-label={t("visualScore")} className="grid gap-2" data-testid="rd-visual">
                {(["0", "1", "2", "3"] as const).map((sc) => {
                  const on = value === sc;
                  return (
                    <Button
                      key={sc}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      variant={on ? (sc === "3" ? "destructive" : "default") : "outline"}
                      className={cn("h-auto min-h-12 justify-start gap-2 py-2 text-start", sc === "3" && !on && "border-danger/50")}
                      onClick={() => setValue(sc)}
                      data-testid={`rd-visual-${sc}`}
                    >
                      <ChoiceMark on={on} />
                      <span className="text-lg font-semibold tabular-nums">{sc}</span>
                      <span className="text-sm font-normal">{td(`visual.${sc}`)}</span>
                    </Button>
                  );
                })}
              </div>
            </fieldset>
          ) : (
            <FormField id="rd-value" label={unit ? `${t("value")} (${unit})` : t("value")} required>
              <DecimalInput id="rd-value" value={value} onChange={setValue} className={big} data-testid="rd-value" />
            </FormField>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="rd-start" label={lab ? t("sampleStart") : t("start")} required>
              <Input id="rd-start" type="datetime-local" dir="ltr" className={big} value={start} onChange={(e) => setStart(e.target.value)} data-testid="rd-start" />
            </FormField>
            <FormField id="rd-end" label={lab ? t("sampleEnd") : t("end")} required hint={lab ? t("labHint") : laeq ? t("endHint") : undefined}>
              <Input id="rd-end" type="datetime-local" dir="ltr" className={big} value={end} onChange={(e) => setEnd(e.target.value)} data-testid="rd-end" />
            </FormField>
          </div>
          {lab ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField id="rd-labp" label={t("lab")} required>
                <Select id="rd-labp" className={big} value={labId} onChange={(e) => setLabId(e.target.value)} data-testid="rd-lab-provider">
                  <option value="">{tc("select")}</option>
                  {(labs.data?.items ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.provider_code}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="rd-labref" label={t("labRef")} required>
                <Input id="rd-labref" dir="ltr" maxLength={40} className={big} value={labRef} onChange={(e) => setLabRef(e.target.value)} data-testid="rd-lab-ref" />
              </FormField>
            </div>
          ) : !visual ? (
            <FormField id="rd-inst" label={t("instrument")} required hint={t("instrumentHint")}>
              <Select id="rd-inst" className={big} value={instrumentId} onChange={(e) => setInstrument(e.target.value)} data-testid="rd-instrument">
                <option value="">{tc("select")}</option>
                {usable.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.instrument_no} · {ref.label("instrument_kinds", i.kind)}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          {laeq && !lab ? (
            <div className="rounded-md border p-2">
              <Check id="rd-cal" label={t("fieldCal")} checked={fieldCal} onChange={setFieldCal} testId="rd-field-cal" />
            </div>
          ) : null}
          {visual ? (
            <FormField id="rd-photos" label={t("photos")} hint={t("photoHint")}>
              <PhotoPicker value={photos} onChange={setPhotos} max={3} testId="rd-photos" />
            </FormField>
          ) : null}
        </>
      ) : null}
      <StillNeeded items={missing} testId="rd-missing" />
      <MutationError error={error} />
      <Button className="min-h-12 text-base sm:min-h-control sm:text-sm" disabled={!ready || busy} onClick={() => void save()} data-testid="rd-save">
        {busy ? tc("saving") : t("save")}
      </Button>
    </div>
  );
}

/* ═════════════ exceedances (§3.12, §4.5, EXD-1…EXD-6) ═════════════ */

export function ExceedancesPage() {
  return <ProjectGate>{(p) => <Exceedances project={p} />}</ProjectGate>;
}

function Exceedances({ project }: { project: Project }) {
  const t = useTranslations("env.exceedances");
  const td = useTranslations("envDesign");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["ExceedanceStatus"] | "";
  const point = s.get("point") ?? "";
  const points = useEnvPoints(project.id, { enabled: caps.view });
  const q = useExceedances(project.id, { status: status ? [status] : null, point_id: point || null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EnvMonitorSubNav />
      <ListToolbar>
        <SelectFilter id="ex-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={EXCEEDANCE_STATUSES.map((x) => ({ value: x, label: te(`envExceedanceStatus.${x}`) }))} />
        <SelectFilter id="ex-point" label={t("point")} value={point} onChange={(v) => s.set({ point: v })} options={(points.data?.items ?? []).map((p) => ({ value: p.id, label: p.point_code }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="exceedances-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("point")}</TH>
                <TH>{t("day")}</TH>
                <TH className="text-end">{t("peakLimit")}</TH>
                <TH>{t("cause")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="exceedance-row" data-no={x.exceedance_no} data-status={x.status} data-project-caused={x.project_caused}>
                  <TD label={t("no")}>
                    <Link href={`/env-exceedances/${x.id}`} className="font-medium text-primary hover:underline">
                      <Code>{x.exceedance_no}</Code>
                    </Link>
                    {x.late_result ? (
                      <Badge tone="info" className="ms-1">
                        {t("lateResult")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={t("point")}>
                    <span className="inline-flex items-center gap-1">
                      {x.airside ? <Plane aria-label={t("airside")} className="size-4 text-danger" /> : null}
                      <Code>{x.point_code}</Code>
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {ref.label("parameters", x.parameter)} · {ref.label("averaging", x.averaging)}
                      {x.period !== "any" ? ` · ${ref.label("period", x.period)}` : ""}
                    </span>
                  </TD>
                  <TD label={t("day")}>
                    <StackedDate v={x.day} projectId={project.id} />
                  </TD>
                  <TD label={t("peakLimit")} className="text-end">
                    <span className="inline-flex flex-wrap items-baseline justify-end gap-x-1">
                      <Measure v={x.peak_value} className="font-semibold" />
                      <span className="text-muted-foreground">/</span>
                      <Measure v={x.limit_value} unit={ref.unit(x.parameter)} />
                    </span>
                    <span className="block text-xs text-danger">{td("overBy", { v: `${x.margin_pct} %` })}</span>
                  </TD>
                  <TD label={t("cause")}>
                    <CauseCell x={x} />
                  </TD>
                  <TD label={tc("status")}>
                    <EnvStatusBadge group="envExceedanceStatus" status={x.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={status || point ? undefined : t("empty")} />
      )}
    </div>
  );
}

/** Cause, or the suggested one while unreviewed; background exceedances say so in words (EXD-3, EXD-4). */
function CauseCell({ x }: { x: S["ExceedanceRead"] }) {
  const t = useTranslations("env.exceedances");
  const ref = useEnvRef();
  const cause = x.cause ?? x.suggested_cause;
  return (
    <span className="flex flex-col items-start gap-1">
      {cause === "background_natural" ? <BackgroundBadge refText={x.background_ref} explain /> : cause ? <span>{ref.label("exceedance_causes", cause)}</span> : <span className="text-muted-foreground">{t("toReview")}</span>}
      {!x.cause && x.suggested_cause ? <span className="text-xs text-muted-foreground">{t("suggested")}</span> : null}
      {x.project_caused ? <span className="text-xs font-medium">{t("projectCaused")}</span> : null}
    </span>
  );
}

export function ExceedancePage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <ExceedanceDetail project={p} id={id} />}</ProjectGate>;
}

function ExceedanceDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.exceedances");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const bi = useBi();
  const opts = useProjectOptions(project.id);
  const q = useExceedance(id, { enabled: caps.view });
  const [dialog, setDialog] = useState<"" | "review" | "void">("");
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const x = q.data;
  if (!x) return <NotFoundState />;
  const unit = ref.unit(x.parameter);
  const reviewable = caps.review && (x.status === "open" || (x.status === "reviewed" && x.cause === "background_natural") || (x.status === "closed" && x.cause === "background_natural"));
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/env-exceedances" }, { label: x.exceedance_no }]} />
      <PageHeader
        title={<Code>{x.exceedance_no}</Code>}
        description={`${x.point_code} · ${ref.label("parameters", x.parameter)} · ${ref.label("averaging", x.averaging)}`}
        badge={<EnvStatusBadge group="envExceedanceStatus" status={x.status} />}
        actions={
          reviewable ? (
            <Button onClick={() => setDialog("review")} data-testid="exceedance-review">
              {x.status === "open" ? t("review") : t("reclassify")}
            </Button>
          ) : null
        }
      />
      {x.airside && x.status === "open" ? (
        <Alert tone="danger" className="mb-4" data-testid="airside-alert">
          <Plane aria-hidden className="me-1 inline size-4" />
          {t("airsideHint")}{" "}
          <Link href="/ops-events" className="font-medium underline">
            {t("opsEvents")}
          </Link>
        </Alert>
      ) : null}
      {x.background_ref ? (
        <Alert tone="info" className="mb-4" data-testid="background-note">
          <CloudFog aria-hidden className="me-1 inline size-4" />
          {t("backgroundHint", { ref: x.background_ref })}
        </Alert>
      ) : null}
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-4 pt-4 sm:pt-5">
          <LimitBar value={x.peak_value} limit={x.limit_value} unit={unit} testId="exceedance-bar" />
          <FieldList>
            <FieldItem label={t("peak")}>
              <span data-testid="exceedance-peak">
                <Measure v={x.peak_value} unit={unit} className="text-lg font-semibold" />
              </span>
            </FieldItem>
            <FieldItem label={t("limit")}>
              <Measure v={x.limit_value} unit={unit} />
            </FieldItem>
            <FieldItem label={t("margin")}>
              <span data-testid="exceedance-margin">
                <Measure v={x.margin_pct} unit="%" />
              </span>
            </FieldItem>
            <FieldItem label={t("started")}>
              <StackedDate v={x.started_at} time projectId={project.id} />
            </FieldItem>
            <FieldItem label={t("ended")}>{x.ended_at ? <StackedDate v={x.ended_at} time projectId={project.id} /> : t("ongoing")}</FieldItem>
            <FieldItem label={t("readings")}>{x.reading_ids.length}</FieldItem>
            <FieldItem label={t("cause")}>
              <CauseCell x={x} />
            </FieldItem>
            <FieldItem label={t("reviewDue")}>
              <StackedDate v={x.review_due_on} projectId={project.id} />
            </FieldItem>
            <FieldItem label={t("responsible")}>{x.responsible_engagement_id ? (opts.engagements.find((e) => e.value === x.responsible_engagement_id)?.code ?? "—") : "—"}</FieldItem>
            {x.activity_en || x.activity_ar ? (
              <FieldItem label={t("activity")} wide>
                <span dir="auto">{bi(x.activity_en, x.activity_ar)}</span>
              </FieldItem>
            ) : null}
            {x.immediate_action_en || x.immediate_action_ar ? (
              <FieldItem label={t("immediateAction")} wide>
                <span dir="auto">{bi(x.immediate_action_en, x.immediate_action_ar)}</span>
              </FieldItem>
            ) : null}
            {x.ca_id ? (
              <FieldItem label={t("ca")}>
                <Link href={`/actions/${x.ca_id}`} className="text-primary hover:underline" data-testid="exceedance-ca">
                  <Code>{x.ca_ref ?? "CA"}</Code>
                </Link>
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      {caps.void && x.status !== "voided" ? (
        <RecordActions>
          <Button variant="destructive-outline" onClick={() => setDialog("void")} data-testid="exceedance-void">
            {t("void")}
          </Button>
        </RecordActions>
      ) : null}
      {dialog === "review" ? <ReviewDialog project={project} x={x} onClose={() => setDialog("")} /> : null}
      {dialog === "void" ? (
        <EnvReasonDialog
          title={t("voidTitle", { no: x.exceedance_no })}
          description={t("voidHint")}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/env-exceedances/{exceedance_id}/void", { params: { path: { exceedance_id: x.id } }, body: { reason } }))}
          onClose={() => setDialog("")}
        />
      ) : null}
    </div>
  );
}

function ReviewDialog({ project, x, onClose }: { project: Project; x: S["ExceedanceRead"]; onClose: () => void }) {
  const t = useTranslations("env.exceedances");
  const tc = useTranslations("common");
  const ref = useEnvRef();
  const opts = useProjectOptions(project.id);
  const refresh = useEnvRefresh();
  const [cause, setCause] = useState<S["ExceedanceCause"] | "">(x.status === "open" ? (x.suggested_cause ?? "") : "project_activity");
  const [eng, setEng] = useState(x.responsible_engagement_id ?? "");
  const [activity, setActivity] = useState(x.activity_en ?? "");
  const [action, setAction] = useState(x.immediate_action_en ?? "");
  const [ca, setCa] = useState(false);
  return (
    <StepDialog
      wide
      title={t("reviewTitle", { no: x.exceedance_no })}
      description={t("reviewHint")}
      confirmLabel={t("review")}
      testId="review-confirm"
      disabled={!cause || !action.trim()}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/env-exceedances/{exceedance_id}/review", {
            params: { path: { exceedance_id: x.id } },
            body: { cause: cause as S["ExceedanceCause"], responsible_engagement_id: eng || null, activity_en: activity || null, immediate_action_en: action, create_ca: ca },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="rv-cause" label={t("cause")} required>
        <Select value={cause} onChange={(e) => setCause(e.target.value as S["ExceedanceCause"])} data-testid="rv-cause">
          <option value="">{tc("select")}</option>
          {ref.options("exceedance_causes").map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </FormField>
      {cause === "project_activity" ? <p className="text-xs text-muted-foreground">{t("caWillBeCreated")}</p> : null}
      {cause === "instrument_fault" ? <p className="text-xs text-muted-foreground">{t("instrumentFaultHint")}</p> : null}
      <FormField id="rv-eng" label={t("responsible")} required={cause === "project_activity"}>
        <Select value={eng} onChange={(e) => setEng(e.target.value)} data-testid="rv-engagement">
          <option value="">—</option>
          {opts.engagements.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="rv-activity" label={t("activity")}>
        <Input value={activity} maxLength={300} onChange={(e) => setActivity(e.target.value)} data-testid="rv-activity" />
      </FormField>
      <FormField id="rv-action" label={t("immediateAction")} required hint={<NoNamesHint />}>
        <Textarea value={action} maxLength={1000} onChange={(e) => setAction(e.target.value)} data-testid="rv-action" />
      </FormField>
      {cause === "third_party" || cause === "unknown" ? <Check id="rv-ca" label={t("createCa")} checked={ca} onChange={setCa} testId="rv-create-ca" /> : null}
    </StepDialog>
  );
}

/* ═════════════ points, instruments and background declarations (§3.7–§3.9, §3.11; 208) ═════════════ */

export function EnvPointsPage() {
  return <ProjectGate>{(p) => <Points project={p} />}</ProjectGate>;
}

function Points({ project }: { project: Project }) {
  const t = useTranslations("env.points");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const opts = useProjectOptions(project.id);
  const q = useEnvPoints(project.id, { enabled: caps.view });
  const [creating, setCreating] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.monitoring ? (
            <Button onClick={() => setCreating(true)} data-testid="point-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EnvMonitorSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="points-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("kind")}</TH>
              <TH>{t("where")}</TH>
              <TH>{t("source")}</TH>
              <TH>{t("requirements")}</TH>
              <TH>{t("active")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((p) => (
              <TR key={p.id} data-testid="point-row" data-code={p.point_code}>
                <TD label={t("code")}>
                  <Link href={`/env-points/${p.id}`} className="font-medium text-primary hover:underline">
                    <Code>{p.point_code}</Code>
                  </Link>
                </TD>
                <TD label={t("kind")}>
                  <span className="inline-flex items-center gap-1">
                    {p.airside ? <Plane aria-label={t("airside")} className="size-4" /> : null}
                    {ref.label("point_kinds", p.kind)}
                  </span>
                  {p.noise_area_category ? <span className="block text-xs text-muted-foreground">{ref.label("noise_areas", p.noise_area_category)}</span> : null}
                </TD>
                <TD label={t("where")}>
                  <Code>{p.zone_code ?? opts.sites.find((x) => x.value === p.site_id)?.code ?? "—"}</Code>
                </TD>
                <TD label={t("source")}>{ref.label("point_source", p.source_kind)}</TD>
                <TD label={t("requirements")}>
                  <ul className="text-xs">
                    {p.requirements.map((r, i) => (
                      <li key={i}>
                        {ref.label("parameters", r.parameter)} · {ref.label("averaging", r.averaging)}
                        {r.period && r.period !== "any" ? ` · ${ref.label("period", r.period)}` : ""} · {ref.label("schedule", r.schedule)}
                      </li>
                    ))}
                  </ul>
                </TD>
                <TD label={t("active")}>
                  <EnvStatusBadge group="envAreaStatus" status={p.active ? "active" : "closed"} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      <Instruments project={project} />
      <Backgrounds project={project} />
      {creating ? <PointForm project={project} onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function PointForm({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("env.points");
  const tc = useTranslations("common");
  const ref = useEnvRef();
  const opts = useProjectOptions(project.id);
  const instruments = useEnvInstruments(project.id);
  const permits = useEnvPermits(project.id, { page_size: 100 });
  const refresh = useEnvRefresh();
  const [v, setV] = useState({ point_code: "", site_id: "", zone_id: "", kind: "boundary" as S["PointKind"], noise: "" as S["NoiseArea"] | "", source_kind: "manual" as S["PointSource"], instrument_id: "", permit_id: "" });
  const [reqs, setReqs] = useState<S["Requirement"][]>([]);
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  /** Prefill from the limit library (LIM-1; list NA for noise). */
  const prefill = (r: S["Requirement"]): S["Requirement"] => {
    const lib = ref.library.find((l) => l.parameter === r.parameter && l.averaging === (r.averaging === "measurement" ? "1h" : r.averaging) && (r.parameter !== "laeq" || (l.period === r.period && l.noise_area_category === (v.noise || null))));
    return lib ? { ...r, alert_value: lib.alert_value, limit_value: lib.limit_value, limit_min: lib.limit_min ?? null, limit_max: lib.limit_max ?? null, limit_source: lib.source } : r;
  };
  const up = (i: number, p: Partial<S["Requirement"]>) => setReqs(reqs.map((x, j) => (j === i ? prefill({ ...x, ...p }) : x)));
  return (
    <StepDialog
      wide
      title={t("new")}
      confirmLabel={tc("save")}
      testId="point-save"
      disabled={!v.point_code || !v.site_id || !reqs.length}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/projects/{project_id}/env-points", {
            params: { path: { project_id: project.id } },
            body: {
              point_code: v.point_code,
              site_id: v.site_id,
              zone_id: v.zone_id || null,
              kind: v.kind,
              noise_area_category: v.noise || null,
              source_kind: v.source_kind,
              instrument_id: v.instrument_id || null,
              permit_id: v.permit_id || null,
              requirements: reqs,
              active: true,
            },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="pt-code" label={t("code")} required>
          <Input className="ltr" maxLength={16} value={v.point_code} onChange={(e) => set({ point_code: e.target.value.toUpperCase() })} data-testid="pt-code" />
        </FormField>
        <FormField id="pt-kind" label={t("kind")} required>
          <Select value={v.kind} onChange={(e) => set({ kind: e.target.value as S["PointKind"] })}>
            {ref.options("point_kinds").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="pt-site" label={t("site")} required>
          <Select value={v.site_id} onChange={(e) => set({ site_id: e.target.value, zone_id: "" })} data-testid="pt-site">
            <option value="">{tc("select")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="pt-zone" label={t("zone")}>
          <Select value={v.zone_id} onChange={(e) => set({ zone_id: e.target.value })}>
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
        <FormField id="pt-source" label={t("source")} required>
          <Select value={v.source_kind} onChange={(e) => set({ source_kind: e.target.value as S["PointSource"] })}>
            {ref.options("point_source").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        {v.source_kind !== "visual" ? (
          <FormField id="pt-inst" label={t("instrument")}>
            <Select value={v.instrument_id} onChange={(e) => set({ instrument_id: e.target.value })}>
              <option value="">—</option>
              {(instruments.data?.items ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.instrument_no}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="pt-noise" label={t("noiseArea")} hint={t("noiseHint")}>
          <Select value={v.noise} onChange={(e) => set({ noise: e.target.value as S["NoiseArea"] | "" })}>
            <option value="">—</option>
            {ref.options("noise_areas").map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        {v.kind === "discharge" ? (
          <FormField id="pt-permit" label={t("permit")}>
            <Select value={v.permit_id} onChange={(e) => set({ permit_id: e.target.value })}>
              <option value="">—</option>
              {(permits.data?.items ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.record_no}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
      </div>
      <fieldset className="flex flex-col gap-2 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">{t("requirements")}</legend>
        <p className="text-xs text-muted-foreground">{t("requirementsHint")}</p>
        {reqs.map((r, i) => (
          <div key={i} className="grid gap-2 rounded-md border p-2 sm:grid-cols-4">
            <Select aria-label={t("parameter")} value={r.parameter} onChange={(e) => up(i, { parameter: e.target.value as S["Parameter"] })}>
              {ref.options("parameters").map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
            <Select aria-label={t("averaging")} value={r.averaging} onChange={(e) => up(i, { averaging: e.target.value as S["Averaging"] })}>
              {ref.options("averaging").map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
            <Select aria-label={t("schedule")} value={r.schedule} onChange={(e) => up(i, { schedule: e.target.value as S["Schedule"] })}>
              {ref.options("schedule").map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
            <Select aria-label={t("period")} value={r.period ?? "any"} onChange={(e) => up(i, { period: e.target.value as S["NoisePeriod"] })}>
              {ref.options("period").map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
            <span className="flex items-center gap-1 text-xs text-muted-foreground sm:col-span-3">
              {t("alertLimit")}: <bdi className="ltr">{String(r.alert_value ?? "—")} / {String(r.limit_value ?? (r.limit_min !== null && r.limit_min !== undefined ? `${String(r.limit_min)}–${String(r.limit_max)}` : "—"))}</bdi>
              {r.limit_source ? ` · ${ref.label("limit_source", r.limit_source)}` : ""}
            </span>
            <Button type="button" variant="ghost" className="min-h-touch justify-self-end" aria-label={t("remove")} onClick={() => setReqs(reqs.filter((_, j) => j !== i))}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" className="w-fit" onClick={() => setReqs([...reqs, prefill({ parameter: "pm10", averaging: "24h", schedule: "weekly", period: "any" })])} data-testid="pt-add-req">
          <Plus aria-hidden />
          {t("addRequirement")}
        </Button>
      </fieldset>
    </StepDialog>
  );
}

function Instruments({ project }: { project: Project }) {
  const t = useTranslations("env.instruments");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const q = useEnvInstruments(project.id, { enabled: caps.view });
  const refresh = useEnvRefresh();
  const [creating, setCreating] = useState(false);
  const [acting, setActing] = useState<{ i: S["EnvInstrumentRead"]; action: S["InstrumentAction"] } | null>(null);
  const items = q.data?.items ?? [];
  return (
    <Card className="mt-6">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("title")}</CardTitle>
        {caps.monitoring ? (
          <Button size="sm" variant="outline" onClick={() => setCreating(true)} data-testid="instrument-new">
            <Plus aria-hidden />
            {t("new")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {items.length ? (
          <Table data-testid="instruments-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("kind")}</TH>
                <TH>{t("serial")}</TH>
                <TH>{t("calibration")}</TH>
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((i) => (
                <TR key={i.id} data-testid="instrument-row" data-status={i.status}>
                  <TD label={t("no")}>
                    <Code>{i.instrument_no}</Code>
                  </TD>
                  <TD label={t("kind")}>
                    {ref.label("instrument_kinds", i.kind)}
                    {i.standard_class ? <span className="block text-xs text-muted-foreground">{t("class", { c: i.standard_class })}</span> : null}
                  </TD>
                  <TD label={t("serial")}>
                    <span className="text-xs">{i.make_model}</span>
                    <Code className="block text-xs">{i.serial_no}</Code>
                  </TD>
                  <TD label={t("calibration")}>
                    <StackedDate v={i.calibration_valid_until} projectId={project.id} />
                  </TD>
                  <TD label={tc("status")}>
                    <EnvStatusBadge group="envInstrumentStatus" status={i.status} />
                  </TD>
                  <TD>
                    {caps.monitoring && i.status !== "retired" ? (
                      <span className="flex flex-wrap gap-1">
                        {i.status === "quarantined" ? (
                          <Button size="sm" variant="outline" onClick={() => setActing({ i, action: "activate" })}>
                            {t("activate")}
                          </Button>
                        ) : (
                          <Button size="sm" variant="destructive-outline" onClick={() => setActing({ i, action: "quarantine" })}>
                            {t("quarantine")}
                          </Button>
                        )}
                        <Button size="sm" variant="destructive-outline" onClick={() => setActing({ i, action: "retire" })}>
                          {t("retire")}
                        </Button>
                      </span>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState message={t("empty")} />
        )}
      </CardContent>
      {creating ? <InstrumentForm project={project} onClose={() => setCreating(false)} /> : null}
      {acting ? (
        acting.action === "activate" ? (
          <StepDialog
            title={t("activate")}
            description={t("activateHint")}
            confirmLabel={t("activate")}
            onConfirm={async () => {
              await unwrap(api.POST("/api/v1/env-instruments/{instrument_id}/transitions", { params: { path: { instrument_id: acting.i.id } }, body: { action: "activate" } }));
              await refresh();
            }}
            onClose={() => setActing(null)}
          />
        ) : (
          <EnvReasonDialog
            title={t(acting.action, {})}
            min={acting.action === "quarantine" ? 5 : 20}
            confirmLabel={t(acting.action, {})}
            onConfirm={(reason) => unwrap(api.POST("/api/v1/env-instruments/{instrument_id}/transitions", { params: { path: { instrument_id: acting.i.id } }, body: { action: acting.action, reason } }))}
            onClose={() => setActing(null)}
          />
        )
      ) : null}
    </Card>
  );
}

function InstrumentForm({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("env.instruments");
  const tc = useTranslations("common");
  const ref = useEnvRef();
  const refresh = useEnvRefresh();
  const [v, setV] = useState({ kind: "pm_portable" as S["EnvInstrumentKind"], make_model: "", serial_no: "", standard_class: "", calibration_valid_until: "", calibration_cert_ref: "" });
  const set = (p: Partial<typeof v>) => setV({ ...v, ...p });
  return (
    <StepDialog
      title={t("new")}
      confirmLabel={tc("save")}
      testId="instrument-save"
      disabled={!v.make_model || !v.serial_no || !v.calibration_valid_until || !v.calibration_cert_ref}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/projects/{project_id}/env-instruments", { params: { path: { project_id: project.id } }, body: { ...v, standard_class: v.standard_class || null } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="in-kind" label={t("kind")} required>
        <Select value={v.kind} onChange={(e) => set({ kind: e.target.value as S["EnvInstrumentKind"] })}>
          {ref.options("instrument_kinds").map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="in-model" label={t("model")} required>
        <Input value={v.make_model} onChange={(e) => set({ make_model: e.target.value })} />
      </FormField>
      <FormField id="in-serial" label={t("serial")} required>
        <Input className="ltr" value={v.serial_no} onChange={(e) => set({ serial_no: e.target.value })} />
      </FormField>
      {v.kind === "sound_level_meter" || v.kind === "noise_station" ? (
        <FormField id="in-class" label={t("slmClass")} required>
          <Select value={v.standard_class} onChange={(e) => set({ standard_class: e.target.value })}>
            <option value="">{tc("select")}</option>
            <option value="1">1</option>
            <option value="2">2</option>
          </Select>
        </FormField>
      ) : null}
      <FormField id="in-cal" label={t("calibration")} required>
        <Input type="date" value={v.calibration_valid_until} onChange={(e) => set({ calibration_valid_until: e.target.value })} />
      </FormField>
      <FormField id="in-cert" label={t("certRef")} required>
        <Input className="ltr" value={v.calibration_cert_ref} onChange={(e) => set({ calibration_cert_ref: e.target.value })} />
      </FormField>
    </StepDialog>
  );
}

function Backgrounds({ project }: { project: Project }) {
  const t = useTranslations("env.background");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const opts = useProjectOptions(project.id);
  const q = useBackgrounds(project.id, { enabled: caps.view });
  const refresh = useEnvRefresh();
  const [creating, setCreating] = useState(false);
  const [v, setV] = useState({ site_ids: [] as string[], from: "", to: "", source: "ncm_warning" as S["BackgroundSource"], ref: "" });
  const items = q.data?.items ?? [];
  return (
    <Card className="mt-6">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle className="text-base">{t("title")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("subtitle")}</p>
        </div>
        {caps.monitoring ? (
          <Button size="sm" variant="outline" onClick={() => setCreating(true)} data-testid="background-new">
            <CloudFog aria-hidden />
            {t("new")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {items.length ? (
          <ul className="flex flex-col divide-y text-sm" data-testid="backgrounds">
            {items.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center gap-2 py-2">
                <Code>{b.declaration_no}</Code>
                <span>{ref.label("background_source", b.source)}</span>
                <Code>{b.source_ref}</Code>
                <span className="inline-flex flex-wrap items-center gap-1 text-muted-foreground">
                  <StackedDate v={b.from_at} time projectId={project.id} /> – <StackedDate v={b.to_at} time projectId={project.id} />
                </span>
                <Code>{b.site_ids.map((s) => opts.sites.find((x) => x.value === s)?.code ?? "").join(", ")}</Code>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState message={t("empty")} />
        )}
      </CardContent>
      {creating ? (
        <StepDialog
          title={t("new")}
          description={t("hint")}
          confirmLabel={tc("save")}
          disabled={!v.site_ids.length || !v.from || !v.to || !v.ref}
          onConfirm={async () => {
            await unwrap(
              api.POST("/api/v1/projects/{project_id}/background-declarations", {
                params: { path: { project_id: project.id } },
                body: { site_ids: v.site_ids, from_at: fromLocalInput(v.from) ?? "", to_at: fromLocalInput(v.to) ?? "", source: v.source, source_ref: v.ref },
              }),
            );
            await refresh();
          }}
          onClose={() => setCreating(false)}
        >
          <MultiSelect id="bg-sites" label={t("sites")} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} value={v.site_ids} onChange={(x) => setV({ ...v, site_ids: x })} allLabel={tc("select")} />
          <FormField id="bg-from" label={t("from")} required>
            <Input type="datetime-local" dir="ltr" value={v.from} onChange={(e) => setV({ ...v, from: e.target.value })} />
          </FormField>
          <FormField id="bg-to" label={t("to")} required hint={t("maxHours")}>
            <Input type="datetime-local" dir="ltr" value={v.to} onChange={(e) => setV({ ...v, to: e.target.value })} />
          </FormField>
          <FormField id="bg-source" label={t("source")} required>
            <Select value={v.source} onChange={(e) => setV({ ...v, source: e.target.value as S["BackgroundSource"] })}>
              {ref.options("background_source").map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="bg-ref" label={t("sourceRef")} required>
            <Input className="ltr" maxLength={40} value={v.ref} onChange={(e) => setV({ ...v, ref: e.target.value })} />
          </FormField>
        </StepDialog>
      ) : null}
    </Card>
  );
}

export function EnvPointPage({ id }: { id: string }) {
  return <ProjectGate>{(p) => <PointDetail project={p} id={id} />}</ProjectGate>;
}

/** Point page: requirements with the strictest limit in force (LIM-2, PRM-5), limit tightening, recent readings. */
function PointDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("env.points");
  const td = useTranslations("envDesign");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const q = useEnvPoint(id, { enabled: caps.view });
  const readings = useEnvReadings(project.id, { point_id: id, page_size: 20 }, { enabled: caps.view });
  const [editing, setEditing] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  if (!p) return <NotFoundState />;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/env-points" }, { label: p.point_code }]} />
      <PageHeader
        title={<Code>{p.point_code}</Code>}
        description={`${ref.label("point_kinds", p.kind)}${p.zone_code ? ` · ${p.zone_code}` : ""} · ${ref.label("point_source", p.source_kind)}`}
        badge={p.airside ? <Badge tone="warning"><Plane aria-hidden />{t("airside")}</Badge> : undefined}
        actions={
          <>
            {caps.reading && p.source_kind !== "station" ? (
              <Button asChild>
                <Link href={`/env-readings/new?point=${p.id}`} data-testid="point-reading">
                  {t("newReading")}
                </Link>
              </Button>
            ) : null}
            {caps.monitoring ? (
              <Button variant="outline" onClick={() => setEditing(true)} data-testid="limits-edit">
                {t("editLimits")}
              </Button>
            ) : null}
          </>
        }
      />
      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="text-base">{t("requirements")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("strictestHint")}</p>
        </CardHeader>
        <CardContent>
          <Table data-testid="requirements-table">
            <THead>
              <TR>
                <TH>{t("parameter")}</TH>
                <TH>{t("schedule")}</TH>
                <TH className="text-end">{t("alert")}</TH>
                <TH className="text-end">{t("limitInForce")}</TH>
                <TH>{t("limitSource")}</TH>
              </TR>
            </THead>
            <TBody>
              {p.requirements.map((r, i) => (
                <TR key={i} data-testid="requirement-row">
                  <TD label={t("parameter")}>
                    {ref.label("parameters", r.parameter)} · {ref.label("averaging", r.averaging)}
                    {r.period && r.period !== "any" ? ` · ${ref.label("period", r.period)}` : ""}
                  </TD>
                  <TD label={t("schedule")}>{ref.label("schedule", r.schedule)}</TD>
                  <TD label={t("alert")} className="text-end">
                    <Measure v={r.alert_value} unit={ref.unit(r.parameter)} />
                  </TD>
                  <TD label={t("limitInForce")} className="text-end font-semibold">
                    {r.effective_limit ? <Measure v={r.effective_limit} unit={ref.unit(r.parameter)} /> : r.limit_min ? <bdi className="ltr">{r.limit_min}–{r.limit_max}</bdi> : "—"}
                  </TD>
                  <TD label={t("limitSource")}>
                    {ref.label("limit_source", r.effective_source ?? r.limit_source)}
                    {r.condition_code ? (
                      <span className="block text-xs text-muted-foreground">
                        <Code>{r.condition_code}</Code>
                      </span>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("recent")}</CardTitle>
        </CardHeader>
        <CardContent>
          {(readings.data?.items ?? []).length ? (
            <ul className="flex flex-col divide-y text-sm" data-testid="point-readings">
              {(readings.data?.items ?? []).map((r) => (
                <li key={r.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 py-2 sm:grid-cols-[11rem_8rem_10rem_minmax(0,1fr)]">
                  <StackedDate v={r.window_end} time projectId={project.id} />
                  <span className="text-muted-foreground max-sm:text-end">
                    {ref.label("parameters", r.parameter)} · {ref.label("averaging", r.averaging)}
                  </span>
                  <span className="sm:text-end">
                    <bdi className="ltr font-semibold tabular-nums">{r.display}</bdi>
                    {r.limit_value ? (
                      <span className="block text-xs text-muted-foreground">
                        {td("limit")} <bdi className="ltr">{r.limit_value}</bdi>
                      </span>
                    ) : null}
                  </span>
                  <span className="max-sm:justify-self-end">
                    <ResultBadge result={r.result} background={r.background} />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message={t("noReadings")} />
          )}
        </CardContent>
      </Card>
      {editing ? <LimitsDialog p={p} onClose={() => setEditing(false)} /> : null}
    </div>
  );
}

/** Tighten-only limits (LIM-2): a looser value is refused by the server with LIMIT_LOOSENING. */
function LimitsDialog({ p, onClose }: { p: S["EnvPointRead"]; onClose: () => void }) {
  const t = useTranslations("env.points");
  const ref = useEnvRef();
  const refresh = useEnvRefresh();
  const [rows, setRows] = useState(p.requirements.map((r) => ({ ...r, alert_value: r.alert_value ?? "", limit_value: r.limit_value ?? "" })));
  return (
    <StepDialog
      wide
      title={t("editLimits")}
      description={t("tightenOnly")}
      confirmLabel={t("saveLimits")}
      testId="limits-save"
      onConfirm={async () => {
        await unwrap(
          api.PATCH("/api/v1/env-points/{point_id}", {
            params: { path: { point_id: p.id } },
            body: {
              requirements: rows.map((r) => ({
                parameter: r.parameter,
                averaging: r.averaging,
                schedule: r.schedule,
                period: r.period,
                alert_value: r.alert_value === "" ? null : r.alert_value,
                limit_value: r.limit_value === "" ? null : r.limit_value,
                limit_min: r.limit_min ?? null,
                limit_max: r.limit_max ?? null,
                limit_source: r.limit_source ?? null,
                library_ref: r.library_ref ?? null,
              })),
            },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      {rows.map((r, i) => (
        <div key={i} className="grid items-end gap-2 sm:grid-cols-3" data-testid="limit-row">
          <span className="text-sm">
            {ref.label("parameters", r.parameter)} · {ref.label("averaging", r.averaging)}
            {r.period && r.period !== "any" ? ` · ${ref.label("period", r.period)}` : ""}
          </span>
          <FormField id={`lm-a-${i}`} label={t("alert")}>
            <DecimalInput id={`lm-a-${i}`} value={String(r.alert_value)} onChange={(x) => setRows(rows.map((y, j) => (j === i ? { ...y, alert_value: x } : y)))} data-testid={`lm-alert-${i}`} />
          </FormField>
          <FormField id={`lm-l-${i}`} label={t("limit")}>
            <DecimalInput id={`lm-l-${i}`} value={String(r.limit_value)} onChange={(x) => setRows(rows.map((y, j) => (j === i ? { ...y, limit_value: x } : y)))} data-testid={`lm-limit-${i}`} />
          </FormField>
        </div>
      ))}
    </StepDialog>
  );
}

/* ═════════════ water use and dewatering discharge (§3.14, WAT-1…WAT-3) ═════════════ */

export function EnvWaterPage() {
  return <ProjectGate>{(p) => <Water project={p} />}</ProjectGate>;
}

function Water({ project }: { project: Project }) {
  const t = useTranslations("env.water");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const ref = useEnvRef();
  const locale = useLocale();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const month = s.get("month") ?? "";
  const q = useWaterEntries(project.id, { month: month || null }, { enabled: caps.view });
  const discharge = useDischargeDays(project.id, { enabled: caps.view });
  const points = useEnvPoints(project.id, { enabled: caps.view });
  const refresh = useEnvRefresh();
  const [adding, setAdding] = useState<"" | "water" | "discharge">("");
  const [voiding, setVoiding] = useState<S["WaterRead"] | null>(null);
  const [w, setW] = useState({ site_id: "", month: "", source: "network" as S["WaterSource"], volume: "" });
  const [d, setD] = useState({ point_id: "", day: "", volume: "" });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  const dischargePoints = (points.data?.items ?? []).filter((p) => p.kind === "discharge");
  const fmtMonth = (m: string) => new Intl.DateTimeFormat(locale === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${m}-01T00:00:00Z`));
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.reading ? (
            <>
              <Button onClick={() => setAdding("water")} data-testid="water-new">
                <Plus aria-hidden />
                {t("new")}
              </Button>
              {dischargePoints.length ? (
                <Button variant="outline" onClick={() => setAdding("discharge")} data-testid="discharge-new">
                  {t("newDischarge")}
                </Button>
              ) : null}
            </>
          ) : null
        }
      />
      <EnvMonitorSubNav />
      <ListToolbar>
        <FormField id="wt-month" label={t("month")}>
          <Input type="month" value={month} onChange={(e) => s.set({ month: e.target.value })} className="w-auto" />
        </FormField>
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="water-table">
          <THead>
            <TR>
              <TH>{t("month")}</TH>
              <TH>{t("site")}</TH>
              <TH>{t("source")}</TH>
              <TH className="text-end">{t("volume")}</TH>
              <TH>{tc("status")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {items.map((x) => (
              <TR key={x.id} data-testid="water-row" data-status={x.status}>
                <TD label={t("month")}>{fmtMonth(x.month)}</TD>
                <TD label={t("site")}>
                  <Code>{opts.sites.find((s2) => s2.value === x.site_id)?.code ?? "—"}</Code>
                </TD>
                <TD label={t("source")}>{ref.label("water_source", x.source)}</TD>
                <TD label={t("volume")} className="text-end">
                  <Measure v={x.volume_m3} unit="m³" />
                </TD>
                <TD label={tc("status")}>
                  <EnvStatusBadge group="envRecordState" status={x.status} />
                </TD>
                <TD>
                  {caps.void && x.status === "valid" ? (
                    <Button size="sm" variant="destructive-outline" onClick={() => setVoiding(x)}>
                      {t("void")}
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">{t("discharge")}</CardTitle>
        </CardHeader>
        <CardContent>
          {(discharge.data?.items ?? []).length ? (
            <ul className="flex flex-col divide-y text-sm" data-testid="discharge-days">
              {(discharge.data?.items ?? []).map((x) => (
                <li key={x.id} className="flex flex-wrap items-center gap-2 py-2">
                  <StackedDate v={x.day} projectId={project.id} />
                  <Code>{dischargePoints.find((p) => p.id === x.point_id)?.point_code ?? "—"}</Code>
                  <Measure v={x.volume_m3} unit="m³" />
                  {!x.permit_valid ? <Badge tone="danger">{t("permitNotValid")}</Badge> : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message={t("noDischarge")} />
          )}
        </CardContent>
      </Card>
      {adding === "water" ? (
        <StepDialog
          title={t("new")}
          description={t("editWindow")}
          confirmLabel={tc("save")}
          testId="water-save"
          disabled={!w.site_id || !w.month || !w.volume}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/projects/{project_id}/water-entries", { params: { path: { project_id: project.id } }, body: { site_id: w.site_id, month: w.month, source: w.source, volume_m3: w.volume } }));
            await refresh();
          }}
          onClose={() => setAdding("")}
        >
          <FormField id="wn-site" label={t("site")} required>
            <Select value={w.site_id} onChange={(e) => setW({ ...w, site_id: e.target.value })}>
              <option value="">{tc("select")}</option>
              {opts.sites.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="wn-month" label={t("month")} required>
            <Input type="month" value={w.month} onChange={(e) => setW({ ...w, month: e.target.value })} />
          </FormField>
          <FormField id="wn-source" label={t("source")} required>
            <Select value={w.source} onChange={(e) => setW({ ...w, source: e.target.value as S["WaterSource"] })}>
              {ref.options("water_source").map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="wn-volume" label={t("volume")} required>
            <DecimalInput value={w.volume} onChange={(x) => setW({ ...w, volume: x })} />
          </FormField>
        </StepDialog>
      ) : null}
      {adding === "discharge" ? (
        <StepDialog
          title={t("newDischarge")}
          confirmLabel={tc("save")}
          disabled={!d.point_id || !d.day || !d.volume}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/projects/{project_id}/discharge-days", { params: { path: { project_id: project.id } }, body: { point_id: d.point_id, day: d.day, volume_m3: d.volume } }));
            await refresh();
          }}
          onClose={() => setAdding("")}
        >
          <FormField id="dd-point" label={t("point")} required>
            <Select value={d.point_id} onChange={(e) => setD({ ...d, point_id: e.target.value })}>
              <option value="">{tc("select")}</option>
              {dischargePoints.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.point_code}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="dd-day" label={t("day")} required>
            <Input type="date" value={d.day} onChange={(e) => setD({ ...d, day: e.target.value })} />
          </FormField>
          <FormField id="dd-volume" label={t("volume")} required>
            <DecimalInput value={d.volume} onChange={(x) => setD({ ...d, volume: x })} />
          </FormField>
        </StepDialog>
      ) : null}
      {voiding ? (
        <EnvReasonDialog
          title={t("voidTitle")}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/water-entries/{entry_id}/void", { params: { path: { entry_id: voiding.id } }, body: { reason } }))}
          onClose={() => setVoiding(null)}
        />
      ) : null}
    </div>
  );
}
