"use client";
import { Plus, Radio } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { FormField } from "@/components/common/form-field";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { Tick } from "@/components/cert/common";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useHeatInstruments, useHeatRefresh, useMonitoringPoints, useRestStations } from "@/lib/api/heat";
import { COOLING, INSTRUMENT_KINDS, POINT_SOURCES, STATION_TYPES } from "@/lib/heat-enums";
import { useFormatters } from "@/lib/use-formatters";
import { Codes, HeatSetupSubNav, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ instruments (§3.1, §4.1, HS-2, HS-4) ═════════════ */

export function HeatInstrumentsPage() {
  return <ProjectGate>{(p) => <Instruments project={p} />}</ProjectGate>;
}

function Instruments({ project }: { project: Project }) {
  const t = useTranslations("heat.instruments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const q = useHeatInstruments(project.id, { page_size: 200 }, { enabled: caps.view });
  const [create, setCreate] = useState(false);
  const [move, setMove] = useState<{ i: S["InstrumentRead"]; action: S["InstrumentAction"] } | null>(null);
  const [device, setDevice] = useState<S["InstrumentRead"] | null>(null);
  const [revoke, setRevoke] = useState<{ i: S["InstrumentRead"]; d: S["StationDeviceRead"] } | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.manage ? (
            <Button onClick={() => setCreate(true)} data-testid="new-instrument">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <HeatSetupSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="instruments-table">
          <THead>
            <TR>
              <TH>{t("no")}</TH>
              <TH>{t("kind")}</TH>
              <TH>{t("model")}</TH>
              <TH>{t("calibration")}</TH>
              <TH>{t("points")}</TH>
              <TH>{t("devices")}</TH>
              <TH>{tc("status")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {items.map((i) => (
              <TR key={i.id} data-testid="instrument-row" data-no={i.instrument_no} data-status={i.status}>
                <TD label={t("no")}>
                  <Code className="font-medium">{i.instrument_no}</Code>
                </TD>
                <TD label={t("kind")}>{te(`instrumentKind.${i.kind}`)}</TD>
                <TD label={t("model")}>
                  {i.make_model}
                  <Code className="block text-xs text-muted-foreground">{i.serial_no}</Code>
                  {!i.iso7243_compliant ? <Badge tone="danger">{t("notIso")}</Badge> : null}
                </TD>
                <TD label={t("calibration")}>
                  <span className="whitespace-nowrap">{date(i.calibration_valid_until)}</span>
                  <Code className="block text-xs text-muted-foreground">{i.calibration_cert_ref}</Code>
                </TD>
                <TD label={t("points")}>
                  <Codes items={i.point_codes} />
                </TD>
                <TD label={t("devices")}>
                  {i.devices?.length ? (
                    <ul className="flex flex-col gap-1 text-xs">
                      {i.devices.map((d) => (
                        <li key={d.id} data-testid="station-device" data-revoked={d.revoked_at ? "yes" : "no"}>
                          <Code>{d.device_id}</Code> · {d.label}
                          {d.revoked_at ? (
                            <Badge tone="neutral" className="ms-1">
                              {t("revoked")}
                            </Badge>
                          ) : d.last_seen_at ? (
                            <span className="block text-muted-foreground">{t("lastSeen", { at: dateTime(d.last_seen_at) })}</span>
                          ) : null}
                          {caps.manage && !d.revoked_at ? (
                            <Button size="sm" variant="ghost" className="ms-1 h-7 px-2 text-danger" onClick={() => setRevoke({ i, d })} data-testid="device-revoke">
                              {t("revoke")}
                            </Button>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    "—"
                  )}
                </TD>
                <TD label={tc("status")}>
                  <StatusBadge status={i.status === "quarantined" ? "suspended" : i.status === "retired" ? "closed" : "active"} label={te(`instrumentStatus.${i.status}`)} />
                  {i.status_reason ? (
                    <span dir="auto" className="block text-xs text-muted-foreground">
                      {i.status_reason}
                    </span>
                  ) : null}
                </TD>
                <TD>
                  {caps.manage && i.status !== "retired" ? (
                    <span className="flex flex-wrap gap-1">
                      {i.status === "quarantined" ? (
                        <Button size="sm" variant="outline" onClick={() => setMove({ i, action: "activate" })} data-testid="instrument-activate">
                          {t("activate")}
                        </Button>
                      ) : (
                        <Button size="sm" variant="outline" onClick={() => setMove({ i, action: "quarantine" })} data-testid="instrument-quarantine">
                          {t("quarantine")}
                        </Button>
                      )}
                      {i.kind === "fixed_station" && i.status === "active" ? (
                        <Button size="sm" variant="outline" onClick={() => setDevice(i)} data-testid="device-register">
                          <Radio aria-hidden />
                          {t("registerDevice")}
                        </Button>
                      ) : null}
                      <Button size="sm" variant="destructive-outline" onClick={() => setMove({ i, action: "retire" })} data-testid="instrument-retire">
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
      {create ? <InstrumentDialog project={project} onClose={() => setCreate(false)} /> : null}
      {move ? <TransitionDialog i={move.i} action={move.action} onClose={() => setMove(null)} /> : null}
      {device ? <DeviceDialog i={device} onClose={() => setDevice(null)} /> : null}
      {revoke ? (
        <StepDialog
          title={t("revokeTitle", { device: revoke.d.device_id })}
          description={t("revokeHint")}
          confirmLabel={t("revoke")}
          destructive
          testId="device-revoke-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/heat-instruments/{instrument_id}/devices/{device_pk}/revoke", { params: { path: { instrument_id: revoke.i.id, device_pk: revoke.d.id } } }));
            await q.refetch();
          }}
          onClose={() => setRevoke(null)}
        />
      ) : null}
    </div>
  );
}

function InstrumentDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("heat.instruments");
  const te = useTranslations("enums");
  const refresh = useHeatRefresh();
  const [kind, setKind] = useState<S["InstrumentKind"]>("handheld_meter");
  const [model, setModel] = useState("");
  const [serial, setSerial] = useState("");
  const [iso, setIso] = useState(true);
  const [until, setUntil] = useState("");
  const [cert, setCert] = useState("");
  return (
    <StepDialog
      title={t("new")}
      description={t("newHint")}
      confirmLabel={t("register")}
      disabled={!model.trim() || !serial.trim() || !until || !cert.trim()}
      testId="instrument-confirm"
      onConfirm={async () => {
        const r = await unwrap(
          api.POST("/api/v1/projects/{project_id}/heat-instruments", {
            params: { path: { project_id: project.id } },
            body: { kind, make_model: model.trim(), serial_no: serial.trim(), iso7243_compliant: iso, calibration_valid_until: until, calibration_cert_ref: cert.trim() },
          }),
        );
        toast.success(t("registered", { no: r.instrument_no }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="in-kind" label={t("kind")} required>
        <Select id="in-kind" value={kind} onChange={(e) => setKind(e.target.value as S["InstrumentKind"])} data-testid="in-kind">
          {INSTRUMENT_KINDS.map((k) => (
            <option key={k} value={k}>
              {te(`instrumentKind.${k}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="in-model" label={t("model")} required>
        <Input id="in-model" value={model} maxLength={80} onChange={(e) => setModel(e.target.value)} data-testid="in-model" />
      </FormField>
      <FormField id="in-serial" label={t("serial")} required>
        <Input id="in-serial" dir="ltr" value={serial} maxLength={40} onChange={(e) => setSerial(e.target.value)} data-testid="in-serial" />
      </FormField>
      <Tick id="in-iso" label={t("iso")} checked={iso} onChange={setIso} />
      <FormField id="in-until" label={t("calibrationUntil")} required hint={t("calibrationHint")}>
        <Input id="in-until" type="date" dir="ltr" value={until} onChange={(e) => setUntil(e.target.value)} data-testid="in-until" />
      </FormField>
      <FormField id="in-cert" label={t("certRef")} required>
        <Input id="in-cert" dir="ltr" value={cert} maxLength={40} onChange={(e) => setCert(e.target.value)} data-testid="in-cert" />
      </FormField>
    </StepDialog>
  );
}

function TransitionDialog({ i, action, onClose }: { i: S["InstrumentRead"]; action: S["InstrumentAction"]; onClose: () => void }) {
  const t = useTranslations("heat.instruments");
  const tcm = useTranslations("heat.common");
  const refresh = useHeatRefresh();
  const [reason, setReason] = useState("");
  const [until, setUntil] = useState("");
  const [cert, setCert] = useState("");
  const activate = action === "activate";
  return (
    <StepDialog
      title={t(`${action}Title`, { no: i.instrument_no })}
      confirmLabel={t(action)}
      destructive={action !== "activate"}
      disabled={activate ? !until || !cert.trim() : !reason.trim()}
      testId="instrument-transition-confirm"
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/heat-instruments/{instrument_id}/transitions", {
            params: { path: { instrument_id: i.id } },
            body: { action, reason: reason.trim() || null, calibration_valid_until: until || null, calibration_cert_ref: cert.trim() || null },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      {activate ? (
        <>
          <FormField id="it-until" label={t("calibrationUntil")} required hint={t("calibrationHint")}>
            <Input id="it-until" type="date" dir="ltr" value={until} onChange={(e) => setUntil(e.target.value)} />
          </FormField>
          <FormField id="it-cert" label={t("certRef")} required>
            <Input id="it-cert" dir="ltr" value={cert} maxLength={40} onChange={(e) => setCert(e.target.value)} />
          </FormField>
        </>
      ) : (
        <FormField id="it-reason" label={tcm("reason")} required>
          <Input id="it-reason" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} data-testid="it-reason" />
        </FormField>
      )}
    </StepDialog>
  );
}

/** Register a weather-station device; the token is shown once (as Phase 2 gate devices, GC-1). */
function DeviceDialog({ i, onClose }: { i: S["InstrumentRead"]; onClose: () => void }) {
  const t = useTranslations("heat.instruments");
  const tc = useTranslations("common");
  const refresh = useHeatRefresh();
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const shown = useRef<string | null>(null);
  if (token) {
    return (
      <StepDialog title={t("tokenTitle")} confirmLabel={tc("close")} onConfirm={async () => undefined} onClose={onClose}>
        <Alert tone="warning">{t("tokenOnce")}</Alert>
        <code className="block rounded-md border bg-surface p-2 text-xs break-all ltr" data-testid="device-token">
          {token}
        </code>
      </StepDialog>
    );
  }
  return (
    <StepDialog
      title={t("registerDevice")}
      description={t("deviceHint")}
      confirmLabel={t("register")}
      disabled={!id.trim() || !label.trim()}
      testId="device-confirm"
      onConfirm={async () => {
        const r = await unwrap(api.POST("/api/v1/heat-instruments/{instrument_id}/devices", { params: { path: { instrument_id: i.id } }, body: { device_id: id.trim(), label: label.trim() } }));
        await refresh();
        shown.current = r.device_token;
      }}
      onClose={() => (shown.current ? setToken(shown.current) : onClose())}
    >
      <FormField id="dv-id" label={t("deviceId")} required>
        <Input id="dv-id" dir="ltr" value={id} onChange={(e) => setId(e.target.value)} data-testid="dv-id" />
      </FormField>
      <FormField id="dv-label" label={t("deviceLabel")} required>
        <Input id="dv-label" value={label} onChange={(e) => setLabel(e.target.value)} data-testid="dv-label" />
      </FormField>
    </StepDialog>
  );
}

/* ═════════════ monitoring points (§3.2, HS-3) ═════════════ */

export function MonitoringPointsPage() {
  return <ProjectGate>{(p) => <Points project={p} />}</ProjectGate>;
}

function Points({ project }: { project: Project }) {
  const t = useTranslations("heat.points");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const opts = useProjectOptions(project.id);
  const q = useMonitoringPoints(project.id, { page_size: 200 }, { enabled: caps.view });
  const [edit, setEdit] = useState<S["PointRead"] | "new" | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.manage ? (
            <Button onClick={() => setEdit("new")} data-testid="new-point">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <HeatSetupSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="points-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("site")}</TH>
              <TH>{t("zones")}</TH>
              <TH>{t("source")}</TH>
              <TH>{t("instrument")}</TH>
              <TH>{t("solar")}</TH>
              <TH>{tc("status")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {items.map((p) => (
              <TR key={p.id} data-testid="point-row" data-code={p.point_code}>
                <TD label={t("code")}>
                  <Code className="font-medium">{p.point_code}</Code>
                </TD>
                <TD label={t("site")}>{opts.sites.find((s) => s.value === p.site_id)?.code ?? "—"}</TD>
                <TD label={t("zones")}>
                  <Codes items={p.zone_codes} />
                </TD>
                <TD label={t("source")}>{te(`pointSource.${p.source_kind}`)}</TD>
                <TD label={t("instrument")}>{p.instrument_no ? <Code>{p.instrument_no}</Code> : "—"}</TD>
                <TD label={t("solar")}>{p.solar_load ? tc("yes") : tc("no")}</TD>
                <TD label={tc("status")}>
                  <StatusBadge status={p.active ? "active" : "inactive"} label={p.active ? t("active") : t("inactive")} />
                </TD>
                <TD>
                  {caps.manage ? (
                    <Button size="sm" variant="outline" onClick={() => setEdit(p)} data-testid="point-edit">
                      {tc("edit")}
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
      {edit ? <PointDialog project={project} point={edit === "new" ? null : edit} onClose={() => setEdit(null)} /> : null}
    </div>
  );
}

function PointDialog({ project, point, onClose }: { project: Project; point: S["PointRead"] | null; onClose: () => void }) {
  const t = useTranslations("heat.points");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useHeatRefresh();
  const opts = useProjectOptions(project.id);
  const instruments = useHeatInstruments(project.id, { page_size: 200 });
  const [code, setCode] = useState(point?.point_code ?? "");
  const [site, setSite] = useState(point?.site_id ?? "");
  const [zones, setZones] = useState<string[]>(point?.zone_ids ?? []);
  const [source, setSource] = useState<S["PointSourceKind"]>(point?.source_kind ?? "manual");
  const [instrument, setInstrument] = useState(point?.instrument_id ?? "");
  const [solar, setSolar] = useState(point?.solar_load ?? true);
  const [active, setActive] = useState(point?.active ?? true);
  const stations = (instruments.data?.items ?? []).filter((i) => i.status === "active" && (source === "station" ? i.kind === "fixed_station" : i.kind === "handheld_meter"));
  return (
    <StepDialog
      title={point ? t("editTitle", { code: point.point_code }) : t("new")}
      description={t("hint")}
      confirmLabel={tc("save")}
      disabled={!code.trim() || !site || !zones.length || (source === "station" && !instrument)}
      testId="point-confirm"
      onConfirm={async () => {
        if (point) {
          await unwrap(api.PATCH("/api/v1/monitoring-points/{point_id}", { params: { path: { point_id: point.id } }, body: { zone_ids: zones, instrument_id: instrument || null, solar_load: solar, active } }));
        } else {
          await unwrap(
            api.POST("/api/v1/projects/{project_id}/monitoring-points", {
              params: { path: { project_id: project.id } },
              body: { point_code: code.trim(), site_id: site, zone_ids: zones, source_kind: source, instrument_id: instrument || null, solar_load: solar },
            }),
          );
        }
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="pt-code" label={t("code")} required>
        <Input id="pt-code" dir="ltr" value={code} maxLength={16} disabled={!!point} onChange={(e) => setCode(e.target.value.toUpperCase())} data-testid="pt-code" />
      </FormField>
      <FormField id="pt-site" label={t("site")} required>
        <Select
          id="pt-site"
          value={site}
          disabled={!!point}
          onChange={(e) => {
            setSite(e.target.value);
            setZones([]);
          }}
          data-testid="pt-site"
        >
          <option value="">{tc("select")}</option>
          {opts.sites.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
      </FormField>
      <MultiSelect id="pt-zones" label={t("zones")} options={opts.zones.filter((z) => z.siteId === site)} value={zones} onChange={setZones} />
      <FormField id="pt-source" label={t("source")} required>
        <Select id="pt-source" value={source} disabled={!!point} onChange={(e) => setSource(e.target.value as S["PointSourceKind"])} data-testid="pt-source">
          {POINT_SOURCES.map((x) => (
            <option key={x} value={x}>
              {te(`pointSource.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="pt-inst" label={t("instrument")} required={source === "station"} hint={source === "manual" ? t("instrumentManualHint") : undefined}>
        <Select id="pt-inst" value={instrument} onChange={(e) => setInstrument(e.target.value)} data-testid="pt-inst">
          <option value="">{tc("select")}</option>
          {stations.map((i) => (
            <option key={i.id} value={i.id}>
              {i.instrument_no}
            </option>
          ))}
        </Select>
      </FormField>
      <Tick id="pt-solar" label={t("solarLabel")} checked={solar} onChange={setSolar} />
      {point ? <Tick id="pt-active" label={t("active")} checked={active} onChange={setActive} /> : null}
    </StepDialog>
  );
}

/* ═════════════ rest stations (§3.7, RS-1) ═════════════ */

export function RestStationsPage() {
  return <ProjectGate>{(p) => <Stations project={p} />}</ProjectGate>;
}

function Stations({ project }: { project: Project }) {
  const t = useTranslations("heat.stations");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tp = useTranslations("heat.points");
  const caps = useHeatCaps(project.id);
  const opts = useProjectOptions(project.id);
  const q = useRestStations(project.id, { page_size: 200 }, { enabled: caps.view });
  const [edit, setEdit] = useState<S["RestStationRead"] | "new" | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.manage ? (
            <Button onClick={() => setEdit("new")} data-testid="new-station">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <HeatSetupSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="stations-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{tp("site")}</TH>
              <TH>{tp("zones")}</TH>
              <TH>{t("type")}</TH>
              <TH>{t("cooling")}</TH>
              <TH className="text-end">{t("capacity")}</TH>
              <TH>{tc("status")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {items.map((x) => (
              <TR key={x.id} data-testid="station-row" data-code={x.station_code}>
                <TD label={t("code")}>
                  <Code className="font-medium">{x.station_code}</Code>
                </TD>
                <TD label={tp("site")}>{opts.sites.find((s) => s.value === x.site_id)?.code ?? "—"}</TD>
                <TD label={tp("zones")}>
                  <Codes items={x.zone_codes} />
                </TD>
                <TD label={t("type")}>{te(`stationType.${x.station_type}`)}</TD>
                <TD label={t("cooling")}>{te(`cooling.${x.cooling}`)}</TD>
                <TD label={t("capacity")} className="text-end tabular-nums">
                  {x.capacity_persons}
                </TD>
                <TD label={tc("status")}>
                  <StatusBadge status={x.active ? "active" : "inactive"} label={x.active ? tp("active") : tp("inactive")} />
                </TD>
                <TD>
                  {caps.manage ? (
                    <Button size="sm" variant="outline" onClick={() => setEdit(x)} data-testid="station-edit">
                      {tc("edit")}
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
      {edit ? <StationDialog project={project} station={edit === "new" ? null : edit} onClose={() => setEdit(null)} /> : null}
    </div>
  );
}

function StationDialog({ project, station, onClose }: { project: Project; station: S["RestStationRead"] | null; onClose: () => void }) {
  const t = useTranslations("heat.stations");
  const tp = useTranslations("heat.points");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useHeatRefresh();
  const opts = useProjectOptions(project.id);
  const [code, setCode] = useState(station?.station_code ?? "");
  const [site, setSite] = useState(station?.site_id ?? "");
  const [zones, setZones] = useState<string[]>(station?.zone_ids ?? []);
  const [type, setType] = useState<S["StationType"]>(station?.station_type ?? "shaded_shelter");
  const [cooling, setCooling] = useState<S["Cooling"]>(station?.cooling ?? "none");
  const [cap, setCap] = useState(String(station?.capacity_persons ?? ""));
  const [active, setActive] = useState(station?.active ?? true);
  return (
    <StepDialog
      title={station ? t("editTitle", { code: station.station_code }) : t("new")}
      confirmLabel={tc("save")}
      disabled={!code.trim() || !site || !zones.length || !cap}
      testId="station-confirm"
      onConfirm={async () => {
        if (station) {
          await unwrap(api.PATCH("/api/v1/rest-stations/{station_id}", { params: { path: { station_id: station.id } }, body: { zone_ids: zones, capacity_persons: Number(cap), cooling, active } }));
        } else {
          await unwrap(
            api.POST("/api/v1/projects/{project_id}/rest-stations", {
              params: { path: { project_id: project.id } },
              body: { station_code: code.trim(), site_id: site, zone_ids: zones, station_type: type, capacity_persons: Number(cap), cooling },
            }),
          );
        }
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="rs-code" label={t("code")} required>
        <Input id="rs-code" dir="ltr" value={code} maxLength={16} disabled={!!station} onChange={(e) => setCode(e.target.value.toUpperCase())} data-testid="rs-code" />
      </FormField>
      <FormField id="rs-site" label={tp("site")} required>
        <Select
          id="rs-site"
          value={site}
          disabled={!!station}
          onChange={(e) => {
            setSite(e.target.value);
            setZones([]);
          }}
          data-testid="rs-site"
        >
          <option value="">{tc("select")}</option>
          {opts.sites.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
      </FormField>
      <MultiSelect id="rs-zones" label={tp("zones")} options={opts.zones.filter((z) => z.siteId === site)} value={zones} onChange={setZones} />
      <FormField id="rs-type" label={t("type")} required>
        <Select id="rs-type" value={type} disabled={!!station} onChange={(e) => setType(e.target.value as S["StationType"])}>
          {STATION_TYPES.map((x) => (
            <option key={x} value={x}>
              {te(`stationType.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="rs-cooling" label={t("cooling")} required>
        <Select id="rs-cooling" value={cooling} onChange={(e) => setCooling(e.target.value as S["Cooling"])}>
          {COOLING.map((x) => (
            <option key={x} value={x}>
              {te(`cooling.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="rs-cap" label={t("capacity")} required hint="1–200">
        <Input id="rs-cap" inputMode="numeric" dir="ltr" value={cap} onChange={(e) => setCap(e.target.value.replace(/[^0-9]/g, ""))} data-testid="rs-cap" />
      </FormField>
      {station ? <Tick id="rs-active" label={tp("active")} checked={active} onChange={setActive} /> : null}
    </StepDialog>
  );
}
