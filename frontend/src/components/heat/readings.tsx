"use client";
import { CheckCircle2, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiWarnings } from "@/components/common/api-warnings";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { DecimalInput } from "@/components/ptw/common";
import { DateFilter } from "@/components/training/common";
import { StackedDate } from "@/components/medical/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useHeatInstruments, useHeatRefresh, useMonitoringPoints, useWbgtReadings } from "@/lib/api/heat";
import { riyadhDayBoundary, zonedInputToUtc } from "@/lib/datetime";
import { useSearchState } from "@/lib/url-state";
import { CellsTable } from "./board";
import { HeatFieldSubNav, HeatReasonDialog, RecordStatusBadge, RegimeBadge, Wbgt, nowLocalInput, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

/** regime_cells map {"acclimatised.heavy": "R2", …} → cells for the regime table. */
export function cellsOf(m: Record<string, S["Regime"]>): S["RegimeCell"][] {
  return Object.entries(m).map(([k, regime]) => {
    const [basis, workload] = k.split(".") as [S["AcclimatisationBasis"], S["Workload"]];
    return { basis, workload, regime, rest_minutes_per_hour: null };
  });
}

/* ═════════════ readings register (§3.3, WB-1…WB-5) ═════════════ */

export function WbgtReadingsPage() {
  return <ProjectGate>{(p) => <Readings project={p} />}</ProjectGate>;
}

function Readings({ project }: { project: Project }) {
  const t = useTranslations("heat.readings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const point = s.get("point") ?? "";
  const status = (s.get("status") ?? "") as S["app__core__heat_enums__RecordStatus"] | "";
  const day = s.get("day") ?? "";
  const points = useMonitoringPoints(project.id, { page_size: 200 }, { enabled: caps.view });
  const q = useWbgtReadings(
    project.id,
    { point_id: point || null, status: status || null, from_at: day ? riyadhDayBoundary(day, false) : null, to_at: day ? riyadhDayBoundary(day, true) : null, page, page_size: PAGE_SIZE },
    { enabled: caps.view },
  );
  const [voiding, setVoiding] = useState<S["ReadingRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.record ? (
            <Button asChild>
              <Link href="/wbgt-readings/new" data-testid="new-reading">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <HeatFieldSubNav />
      <ListToolbar>
        <SelectFilter id="rd-point" label={t("point")} value={point} onChange={(v) => s.set({ point: v })} options={(points.data?.items ?? []).map((p) => ({ value: p.id, label: p.point_code }))} />
        <DateFilter id="rd-day" label={t("day")} value={day} onChange={(v) => s.set({ day: v })} />
        <SelectFilter id="rd-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={(["valid", "voided"] as const).map((x) => ({ value: x, label: te(`heatRecordStatus.${x}`) }))} />
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
                <TH>{t("measuredAt")}</TH>
                <TH>{t("source")}</TH>
                <TH className="text-end">{t("wbgt")}</TH>
                <TH>{t("headline")}</TH>
                <TH>{t("recordedBy")}</TH>
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="reading-row" data-no={r.reading_no} data-status={r.status}>
                  <TD label={t("no")}>
                    <Code className="font-medium">{r.reading_no}</Code>
                  </TD>
                  <TD label={t("point")}>
                    <Code>{r.point_code}</Code>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{r.instrument_no}</Code>
                    </span>
                  </TD>
                  <TD label={t("measuredAt")}>
                    <StackedDate v={r.measured_at} time projectId={project.id} />
                    {r.late_entry ? (
                      <Badge tone="neutral" className="ms-1 align-top" data-testid="late-entry">
                        {t("late")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={t("source")}>{te(`readingSource.${r.source}`)}</TD>
                  <TD label={t("wbgt")} className="text-end font-semibold">
                    <Wbgt v={r.wbgt_c} />
                    {r.tnwb_c || r.tg_c ? (
                      <span className="block text-xs font-normal text-muted-foreground">
                        <bdi className="ltr">
                          Tnwb {r.tnwb_c ?? "—"} · Tg {r.tg_c ?? "—"} · Ta {r.ta_c ?? "—"}
                        </bdi>
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("headline")}>
                    <RegimeBadge regime={r.regime_cells["acclimatised.heavy"]} short />
                  </TD>
                  <TD label={t("recordedBy")}>{r.recorded_by ? <UserName u={r.recorded_by} /> : <span className="text-muted-foreground">{t("device")}</span>}</TD>
                  <TD label={tc("status")}>
                    <RecordStatusBadge status={r.status} />
                    {r.void_reason ? (
                      <span dir="auto" className="block text-xs text-muted-foreground">
                        {r.void_reason}
                      </span>
                    ) : null}
                  </TD>
                  <TD>
                    {caps.void && r.status === "valid" ? (
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
        <EmptyState message={point || status || day ? undefined : t("empty")} />
      )}
      {voiding ? (
        <HeatReasonDialog
          title={t("voidTitle", { no: voiding.reading_no })}
          description={t("voidHint")}
          confirmLabel={t("void")}
          onConfirm={async (reason) => {
            await unwrap(api.POST("/api/v1/wbgt-readings/{reading_id}/void", { params: { path: { reading_id: voiding.id } }, body: { reason } }));
          }}
          onClose={() => setVoiding(null)}
        />
      ) : null}
    </div>
  );
}

const LAST_KEY = "hse.heat.lastReading";
function readLastReading(): { point: string; meter: string } | null {
  try {
    const v = JSON.parse(window.localStorage.getItem(LAST_KEY) ?? "null") as { point?: unknown; meter?: unknown } | null;
    return v && typeof v.point === "string" && typeof v.meter === "string" ? { point: v.point, meter: v.meter } : null;
  } catch {
    return null;
  }
}
function writeLastReading(v: { point: string; meter: string }) {
  try {
    window.localStorage.setItem(LAST_KEY, JSON.stringify(v));
  } catch {
    /* storage blocked: no default next time */
  }
}

/* ═════════════ manual reading entry (phone-first; WB-1…WB-4, §6.1) ═════════════ */

export function NewReadingPage() {
  return <ProjectGate>{(p) => <NewReading project={p} />}</ProjectGate>;
}

function NewReading({ project }: { project: Project }) {
  const t = useTranslations("heat.entry");
  const td = useTranslations("heatDesign");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const refresh = useHeatRefresh();
  const s = useSearchState();
  const zoneParam = s.get("zone") ?? "";
  const points = useMonitoringPoints(project.id, { page_size: 200 }, { enabled: caps.record });
  const instruments = useHeatInstruments(project.id, { page_size: 200 }, { enabled: caps.record });
  const activePoints = (points.data?.items ?? []).filter((p) => p.active);
  const meters = (instruments.data?.items ?? []).filter((i) => i.status === "active" && i.kind === "handheld_meter");
  const fromZone = zoneParam ? activePoints.find((p) => p.zone_ids.includes(zoneParam)) : undefined;
  // Field default: a supervisor usually reads the same point with the same meter; the last pair used on this device is
  // pre-selected when no zone was given and it is still active (per-viewer convenience only).
  const [last] = useState(readLastReading);
  const lastPoint = !zoneParam && last ? activePoints.find((p) => p.id === last.point)?.id : undefined;
  const lastMeter = last ? meters.find((i) => i.id === last.meter)?.id : undefined;
  const [pointSel, setPoint] = useState("");
  const pointId = pointSel || fromZone?.id || lastPoint || "";
  const point = activePoints.find((p) => p.id === pointId);
  const [instSel, setInstrument] = useState("");
  const instrumentId = instSel || (point?.source_kind === "manual" ? point.instrument_id ?? "" : "") || (meters.length === 1 ? meters[0]!.id : "") || lastMeter || "";
  const [at, setAt] = useState(nowLocalInput());
  const [wbgt, setWbgt] = useState("");
  const [tnwb, setTnwb] = useState("");
  const [tg, setTg] = useState("");
  const [ta, setTa] = useState("");
  const [rh, setRh] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<S["ReadingRead"] | null>(null);
  if (!caps.record) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const components = Boolean(tnwb && tg && (ta || !point?.solar_load));
  const ready = Boolean(pointId && instrumentId && at && (wbgt || components));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/wbgt-readings", {
          params: { path: { project_id: project.id } },
          body: {
            point_id: pointId,
            instrument_id: instrumentId,
            measured_at: zonedInputToUtc(at),
            wbgt_entered_c: wbgt || null,
            tnwb_c: tnwb || null,
            tg_c: tg || null,
            ta_c: ta || null,
            rh_pct: rh ? Number(rh) : null,
          },
        }),
      );
      setDone(r);
      writeLastReading({ point: pointId, meter: instrumentId });
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
        <Card data-testid="reading-saved" data-no={done.reading_no} data-wbgt={done.wbgt_c}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckCircle2 aria-hidden className="size-5 text-success" />
              <Code>{done.reading_no}</Code>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <span className="text-3xl font-bold" data-testid="saved-wbgt">
              <Wbgt v={done.wbgt_c} />
            </span>
            {done.late_entry ? <Alert tone="info">{t("lateEntry")}</Alert> : null}
            <ApiWarnings warnings={done.warnings} />
            <CellsTable cells={cellsOf(done.regime_cells)} />
          </CardContent>
        </Card>
        <div className="grid gap-2 sm:flex">
          <Button
            className="min-h-12 sm:min-h-control"
            onClick={() => {
              setDone(null);
              setWbgt("");
              setTnwb("");
              setTg("");
              setTa("");
              setRh("");
              setAt(nowLocalInput());
            }}
            data-testid="reading-another"
          >
            <Plus aria-hidden />
            {t("another")}
          </Button>
          <Button asChild variant="outline" className="min-h-12 sm:min-h-control">
            <Link href="/heat-board">{t("toBoard")}</Link>
          </Button>
        </div>
      </div>
    );
  }

  const big = "h-12 text-lg sm:h-control sm:text-sm";
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FormField id="rd-point" label={t("point")} required>
        <Select id="rd-point" className={big} value={pointId} onChange={(e) => setPoint(e.target.value)} data-testid="rd-point">
          <option value="">{tc("select")}</option>
          {activePoints.map((p) => (
            <option key={p.id} value={p.id}>
              {p.point_code} — {p.zone_codes.join(", ")}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="rd-instrument" label={t("instrument")} required hint={t("instrumentHint")}>
        <Select id="rd-instrument" className={big} value={instrumentId} onChange={(e) => setInstrument(e.target.value)} data-testid="rd-instrument">
          <option value="">{tc("select")}</option>
          {meters.map((i) => (
            <option key={i.id} value={i.id}>
              {i.instrument_no} · {i.serial_no}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="rd-at" label={t("measuredAt")} required hint={t("measuredAtHint")}>
        <Input id="rd-at" type="datetime-local" dir="ltr" className={big} value={at} onChange={(e) => setAt(e.target.value)} data-testid="rd-at" />
      </FormField>
      <FormField id="rd-wbgt" label={t("wbgt")} hint={t("wbgtHint")}>
        <DecimalInput id="rd-wbgt" value={wbgt} onChange={setWbgt} placeholder="30.2" className={big} data-testid="rd-wbgt" />
      </FormField>
      <fieldset className="flex flex-col gap-3 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">{t("components")}</legend>
        <p className="text-xs text-muted-foreground">{point?.solar_load === false ? t("formulaIndoor") : t("formulaSolar")}</p>
        <div className="grid grid-cols-2 items-end gap-3">
          <FormField id="rd-tnwb" label={t("tnwb")}>
            <DecimalInput id="rd-tnwb" value={tnwb} onChange={setTnwb} className={big} data-testid="rd-tnwb" />
          </FormField>
          <FormField id="rd-tg" label={t("tg")}>
            <DecimalInput id="rd-tg" value={tg} onChange={setTg} className={big} data-testid="rd-tg" />
          </FormField>
          <FormField id="rd-ta" label={t("ta")}>
            <DecimalInput id="rd-ta" value={ta} onChange={setTa} className={big} data-testid="rd-ta" />
          </FormField>
          <FormField id="rd-rh" label={t("rh")}>
            <Input id="rd-rh" inputMode="numeric" dir="ltr" className={big} value={rh} onChange={(e) => setRh(e.target.value.replace(/[^0-9]/g, ""))} data-testid="rd-rh" />
          </FormField>
        </div>
      </fieldset>
      <p className="text-xs text-muted-foreground">{t("dryBulbOnly")}</p>
      <MutationError error={error} />
      {!ready ? (
        <p className="text-sm text-muted-foreground" data-testid="rd-missing">
          {td("readingMissing")}
        </p>
      ) : null}
      <Button className="min-h-12 text-base sm:min-h-control sm:text-sm" disabled={!ready || busy} onClick={() => void save()} data-testid="rd-save">
        {busy ? tc("saving") : t("save")}
      </Button>
    </div>
  );
}
