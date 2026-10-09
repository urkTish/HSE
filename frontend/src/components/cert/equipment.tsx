"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Archive, Ban, CircleCheck, Clock, Hourglass, OctagonX, Pencil, Plus, Search, Tag, Trash2, TriangleAlert, Undo2, Wrench } from "lucide-react";
import { useTranslations } from "next-intl";
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
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { RecordActions } from "@/components/common/record-actions";
import { StackedDate } from "@/components/medical/common";
import { Code, DaysLeft, StepDialog, VehicleSelect } from "@/components/access/common";
import { DateTimeInput, DecimalInput } from "@/components/ptw/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { ck, useCertRefresh, useConfigurationEvents, useEquipment, useEquipmentList, useEquipmentStatusEvents } from "@/lib/api/cert";
import { useEngagements } from "@/lib/api/queries";
import { CONFIGURATION_EVENT_TYPES, EQUIPMENT_BLACKLIST_REASONS, EQUIPMENT_CERT_CATEGORIES, EQUIPMENT_DOC_TYPES, RETIRE_REASONS, SAFETY_DEVICES, SERVICE_STATUSES } from "@/lib/cert-enums";
import { useCurrentProject } from "@/lib/current-project";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { CertStatePanel, EquipmentLimitations, EquipmentSubNav, ServiceStatusBadge, Tick, UserName, useCertTypes, type StateTone } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

/** Contractors engaged on the project (owner of an item). */
function useProjectContractors(projectId: string) {
  const q = useEngagements(projectId, { page_size: 200 });
  return useMemo(() => {
    const seen = new Map<string, string>();
    for (const e of q.data?.items ?? []) if (!seen.has(e.contractor.id)) seen.set(e.contractor.id, `${e.contractor.short_code} — ${e.contractor.legal_name_en}`);
    return [...seen.entries()].map(([value, label]) => ({ value, label }));
  }, [q.data]);
}

/* ───────────── list ───────────── */

export function EquipmentListPage() {
  return <ProjectGate>{(p) => <EquipmentList project={p} />}</ProjectGate>;
}

function EquipmentList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("equipment");
  const te = useTranslations("enums");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const cat = s.getAll("category") as S["EquipmentCertCategory"][];
  const status = s.getAll("service_status") as S["ServiceStatus"][];
  const allProjects = s.get("scope") === "all";
  const [create, setCreate] = useState(false);
  const q = useEquipmentList({
    q: s.get("q") || null,
    project_id: allProjects ? null : project.id,
    category: cat.length ? cat : null,
    service_status: status.length ? status : null,
    expiring_days: s.getInt("expiring", 0) || null,
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
          canWrite(me, "equipment.edit", project.id) ? (
            <Button onClick={() => setCreate(true)} data-testid="new-equipment">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EquipmentSubNav />
      <ListToolbar actions={can(me, "export.cert", project.id) ? <ExportButtons dataset="equipment" params={{ project_id: allProjects ? null : project.id }} /> : null}>
        <SearchFilter id="eq-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="eq-cat" label={t("category")} options={EQUIPMENT_CERT_CATEGORIES.map((x) => ({ value: x, label: te(`eqc.${x}`) }))} value={cat} onChange={(v) => s.set({ category: v })} />
        <MultiSelect id="eq-status" label={t("serviceStatus")} options={SERVICE_STATUSES.map((x) => ({ value: x, label: te(`serviceStatus.${x}`) }))} value={status} onChange={(v) => s.set({ service_status: v })} />
        <SelectFilter
          id="eq-exp"
          label={t("expiring")}
          value={s.get("expiring") ?? ""}
          onChange={(v) => s.set({ expiring: v })}
          options={[
            { value: "7", label: t("withinDays", { n: 7 }) },
            { value: "30", label: t("withinDays", { n: 30 }) },
          ]}
        />
        <SelectFilter id="eq-scope" label={t("scope")} value={s.get("scope") ?? ""} onChange={(v) => s.set({ scope: v })} options={[{ value: "all", label: t("allProjects") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="equipment-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("category")}</TH>
                <TH>{t("makeModel")}</TH>
                <TH>{t("owner")}</TH>
                <TH>{t("tag")}</TH>
                <TH>{t("validUntil")}</TH>
                <TH>{t("serviceStatus")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="equipment-row" data-no={x.equipment_no} data-tag={x.current_tag ?? ""}>
                  <TD label={t("no")}>
                    <Link href={`/equipment/${x.id}`} className="font-medium text-primary hover:underline">
                      <Code>{x.equipment_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("category")}>
                    {te(`eqc.${x.category}`)}
                    {x.subtype ? <span className="block text-xs text-muted-foreground">{te(`eqSubtype.${x.subtype}`)}</span> : null}
                  </TD>
                  <TD label={t("makeModel")}>
                    {x.manufacturer} {x.model}
                    <span className="block text-xs text-muted-foreground">
                      <Code>{x.serial_no}</Code>
                    </span>
                  </TD>
                  <TD label={t("owner")}>
                    <Code>{x.owner_short_code}</Code>
                  </TD>
                  <TD label={t("tag")}>
                    {x.current_tag ? (
                      <Code>
                        {x.current_project_code}-{x.current_tag}
                      </Code>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD label={t("validUntil")}>
                    {x.valid_until ? date(x.valid_until) : "—"}
                    {x.swl_t ? <span className="block text-xs text-muted-foreground">{t("swlT", { swl: x.swl_t })}</span> : null}
                  </TD>
                  <TD label={t("serviceStatus")}>
                    <ServiceStatusBadge status={x.service_status} reason={x.service_status_reason} />
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
      {create ? <EquipmentCreateDialog project={project} onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

/* ───────────── create (lookup first, EQ-1) ───────────── */

type DocRow = { doc_type: S["EquipmentDocType"]; ref: string };

function EquipmentCreateDialog({ project, onClose }: { project: S["ProjectRead"]; onClose: () => void }) {
  const t = useTranslations("equipment");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const msg = useErrorMessage();
  const owners = useProjectContractors(project.id);
  const { catalogue } = useCertTypes(project.id);
  const [manufacturer, setManufacturer] = useState("");
  const [serial, setSerial] = useState("");
  const [lookup, setLookup] = useState<S["EquipmentLookupResult"] | null>(null);
  const [lookupErr, setLookupErr] = useState<unknown>(null);
  const [category, setCategory] = useState<S["EquipmentCertCategory"] | "">("");
  const [subtype, setSubtype] = useState<S["EquipmentSubtype"] | "">("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [owner, setOwner] = useState("");
  const [hiredFrom, setHiredFrom] = useState("");
  const [fleet, setFleet] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [capacity, setCapacity] = useState("");
  const [radius, setRadius] = useState("");
  const [height, setHeight] = useState("");
  const [persons, setPersons] = useState("");
  const [liftingDuty, setLiftingDuty] = useState(false);
  const [devices, setDevices] = useState<S["SafetyDevice"][]>([]);
  const [docs, setDocs] = useState<DocRow[]>([]);
  const [pressure, setPressure] = useState({ design: "", mawp: "", volume: "", relief: "" });
  const info = catalogue?.equipment_categories.find((c) => c.code === category);
  async function runLookup() {
    setLookupErr(null);
    try {
      setLookup(await unwrap(api.POST("/api/v1/equipment/lookup", { body: { manufacturer: manufacturer.trim(), serial_no: serial.trim() } })));
    } catch (e) {
      setLookupErr(e);
    }
  }
  const isPressure = category === "pressure_vessel";
  const valid =
    lookup && !lookup.exists && category && model.trim() && /^\d{4}$/.test(year) && owner && (!info?.subtype_required || subtype) && (!isPressure || (pressure.design && pressure.mawp && pressure.volume && pressure.relief));
  async function save() {
    try {
      const r = await unwrap(
        api.POST("/api/v1/equipment", {
          body: {
            category: category as S["EquipmentCertCategory"],
            subtype: subtype || null,
            manufacturer: manufacturer.trim(),
            model: model.trim(),
            serial_no: serial.trim(),
            year_of_manufacture: Number(year),
            owner_contractor_id: owner,
            hired_from: hiredFrom.trim() || null,
            owner_fleet_no: fleet.trim() || null,
            vehicle_id: vehicle || null,
            rated_capacity_t: capacity || null,
            max_radius_m: radius || null,
            max_height_m: height || null,
            persons_capacity: persons ? Number(persons) : null,
            pressure: isPressure ? { design_pressure_bar: pressure.design, mawp_bar: pressure.mawp, volume_l: pressure.volume, relief_set_bar: pressure.relief } : null,
            lifting_duty: liftingDuty,
            safety_devices: devices,
            documents: docs.filter((d) => d.ref.trim()).map((d) => ({ doc_type: d.doc_type, ref: d.ref.trim() })),
          },
        }),
      );
      await qc.invalidateQueries({ queryKey: ["equipment"] });
      toast.success(t("created", { no: r.equipment_no }));
      router.push(`/equipment/${r.id}`);
    } catch (e) {
      if (e instanceof ApiError && (e.code === "EQUIPMENT_EXISTS" || e.code === "EQUIPMENT_EXISTS_OUT_OF_SCOPE") && typeof e.meta.equipment_no === "string") {
        throw new ApiError(e.status, { code: e.code, message: `${msg(e)} (${e.meta.equipment_no})` });
      }
      throw e;
    }
  }
  return (
    <StepDialog title={t("new")} description={t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-equipment">
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <FormField id="eq-mfr" label={t("manufacturer")} required>
          <Input
            value={manufacturer}
            onChange={(e) => {
              setManufacturer(e.target.value);
              setLookup(null);
            }}
            data-testid="eq-manufacturer"
          />
        </FormField>
        <FormField id="eq-serial" label={t("serial")} required>
          <Input
            value={serial}
            onChange={(e) => {
              setSerial(e.target.value);
              setLookup(null);
            }}
            className="ltr"
            data-testid="eq-serial"
          />
        </FormField>
        <Button variant="outline" onClick={() => void runLookup()} disabled={!manufacturer.trim() || !serial.trim()} data-testid="eq-lookup">
          <Search aria-hidden />
          {t("lookup")}
        </Button>
      </div>
      <MutationError error={lookupErr} />
      {lookup?.exists ? (
        <Alert tone={lookup.blacklisted ? "danger" : "warning"} data-testid="lookup-exists">
          {lookup.blacklisted ? t("lookupBlacklisted") : t("lookupExists")}{" "}
          {lookup.equipment ? (
            <Link href={`/equipment/${lookup.equipment.id}`} className="font-medium underline">
              <Code>{lookup.equipment.equipment_no}</Code>
            </Link>
          ) : null}
        </Alert>
      ) : null}
      {lookup && !lookup.exists ? (
        <>
          <Alert tone="info" data-testid="lookup-new">
            {t("lookupNew")}
          </Alert>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="eq-cat" label={t("category")} required hint={t("categoryHint")}>
              <Select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value as S["EquipmentCertCategory"]);
                  setSubtype("");
                }}
                data-testid="eq-category"
              >
                <option value="">{tc("select")}</option>
                {EQUIPMENT_CERT_CATEGORIES.filter((c) => c !== "scaffold").map((c) => (
                  <option key={c} value={c}>
                    {te(`eqc.${c}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            {info?.subtypes.length ? (
              <FormField id="eq-sub" label={t("subtype")} required={info.subtype_required}>
                <Select value={subtype} onChange={(e) => setSubtype(e.target.value as S["EquipmentSubtype"])} data-testid="eq-subtype">
                  <option value="">{tc("select")}</option>
                  {info.subtypes.map((c) => (
                    <option key={c} value={c}>
                      {te(`eqSubtype.${c}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
            ) : (
              <div />
            )}
            <FormField id="eq-model" label={t("model")} required>
              <Input value={model} onChange={(e) => setModel(e.target.value)} data-testid="eq-model" />
            </FormField>
            <FormField id="eq-year" label={t("year")} required>
              <Input value={year} onChange={(e) => setYear(e.target.value)} inputMode="numeric" maxLength={4} className="ltr" data-testid="eq-year" />
            </FormField>
            <FormField id="eq-owner" label={t("owner")} required>
              <Select value={owner} onChange={(e) => setOwner(e.target.value)} data-testid="eq-owner">
                <option value="">{tc("select")}</option>
                {owners.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="eq-hired" label={t("hiredFrom")}>
              <Input value={hiredFrom} onChange={(e) => setHiredFrom(e.target.value)} />
            </FormField>
            <FormField id="eq-fleet" label={t("fleetNo")}>
              <Input value={fleet} onChange={(e) => setFleet(e.target.value)} className="ltr" />
            </FormField>
            <FormField id="eq-vehicle" label={t("vehicle")} hint={t("vehicleHint")}>
              <VehicleSelect id="eq-vehicle" projectId={project.id} value={vehicle} onChange={(v) => setVehicle(v)} placeholder={t("noVehicle")} />
            </FormField>
            <FormField id="eq-cap" label={t("ratedCapacity")}>
              <DecimalInput id="eq-cap" value={capacity} onChange={setCapacity} data-testid="eq-capacity" />
            </FormField>
            <FormField id="eq-radius" label={t("maxRadius")}>
              <DecimalInput id="eq-radius" value={radius} onChange={setRadius} />
            </FormField>
            <FormField id="eq-height" label={t("maxHeight")}>
              <DecimalInput id="eq-height" value={height} onChange={setHeight} />
            </FormField>
            <FormField id="eq-persons" label={t("persons")}>
              <Input value={persons} onChange={(e) => setPersons(e.target.value)} inputMode="numeric" className="ltr" />
            </FormField>
          </div>
          {isPressure ? (
            <div className="grid gap-3 sm:grid-cols-4">
              {(["design", "mawp", "volume", "relief"] as const).map((k) => (
                <FormField key={k} id={`eq-p-${k}`} label={t(`pressure.${k}`)} required>
                  <DecimalInput id={`eq-p-${k}`} value={pressure[k]} onChange={(v) => setPressure({ ...pressure, [k]: v })} />
                </FormField>
              ))}
            </div>
          ) : null}
          <Tick id="eq-lifting-duty" label={t("liftingDuty")} checked={liftingDuty} onChange={setLiftingDuty} />
          <CheckboxGroup id="eq-devices" legend={t("safetyDevices")} options={SAFETY_DEVICES.map((d) => ({ value: d, label: te(`safetyDevice.${d}`) }))} value={devices} onChange={setDevices} />
          <DocsEditor docs={docs} onChange={setDocs} />
        </>
      ) : null}
    </StepDialog>
  );
}

function DocsEditor({ docs, onChange }: { docs: DocRow[]; onChange: (d: DocRow[]) => void }) {
  const t = useTranslations("equipment");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">{t("documents")}</legend>
      <p className="text-xs text-muted-foreground">{t("documentsHint")}</p>
      {docs.map((d, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-[12rem_1fr_auto]">
          <Select aria-label={t("docType")} value={d.doc_type} onChange={(e) => onChange(docs.map((x, j) => (j === i ? { ...x, doc_type: e.target.value as S["EquipmentDocType"] } : x)))}>
            {EQUIPMENT_DOC_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`equipmentDocType.${x}`)}
              </option>
            ))}
          </Select>
          <Input aria-label={t("docRef")} value={d.ref} onChange={(e) => onChange(docs.map((x, j) => (j === i ? { ...x, ref: e.target.value } : x)))} placeholder={t("docRef")} />
          <Button variant="ghost" onClick={() => onChange(docs.filter((_, j) => j !== i))}>
            <Trash2 aria-hidden />
            <span className="sr-only">{tc("remove")}</span>
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" className="self-start" onClick={() => onChange([...docs, { doc_type: "load_chart", ref: "" }])} data-testid="eq-add-doc">
        <Plus aria-hidden />
        {t("addDocument")}
      </Button>
    </fieldset>
  );
}

/* ───────────── detail ───────────── */

export function EquipmentDetail({ id }: { id: string }) {
  const q = useEquipment(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <EquipmentView e={q.data} />;
}

type EqStep = "tagout" | "rts" | "retire" | "blacklist" | "lift" | "edit" | "config" | null;

function EquipmentView({ e }: { e: S["EquipmentRead"] }) {
  const t = useTranslations("equipment");
  const td = useTranslations("certDesign");
  const th = useTranslations("history");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const { project } = useCurrentProject();
  const { date, dateTime } = useFormatters(project?.id);
  const refresh = useCertRefresh();
  const events = useEquipmentStatusEvents(e.id);
  const configs = useConfigurationEvents(e.id);
  const [step, setStep] = useState<EqStep>(null);
  const [reason, setReason] = useState("");
  const [physical, setPhysical] = useState(true);
  const [retireReason, setRetireReason] = useState<S["RetireReason"]>("retired_other");
  const [blReason, setBlReason] = useState<S["EquipmentBlacklistReason"]>("structural_damage");
  const onSite = e.deployments.find((d) => d.status === "on_site") ?? e.deployments.find((d) => d.status === "approved") ?? null;
  const pid = onSite?.project_id ?? project?.id ?? null;
  const caps = {
    edit: canWrite(me, "equipment.edit", pid),
    raise: canWrite(me, "defect.raise", pid),
    close: canWrite(me, "defect.close", pid),
    blacklist: can(me, "cert.blacklist", pid),
  };
  const terminal = e.service_status === "retired" || e.service_status === "blacklisted";
  async function run() {
    const path = { params: { path: { equipment_id: e.id } } };
    let r: S["EquipmentRead"];
    if (step === "tagout") r = await unwrap(api.POST("/api/v1/equipment/{equipment_id}/tag-out", { ...path, body: { project_id: pid as string, reason: reason.trim(), physical_tag_applied: physical } }));
    else if (step === "rts") r = await unwrap(api.POST("/api/v1/equipment/{equipment_id}/return-to-service", { ...path, body: { note: reason.trim() } }));
    else if (step === "retire") r = await unwrap(api.POST("/api/v1/equipment/{equipment_id}/retire", { ...path, body: { reason: retireReason, reason_text: reason.trim() } }));
    else if (step === "blacklist") r = await unwrap(api.POST("/api/v1/equipment/{equipment_id}/blacklist", { ...path, body: { reason_code: blReason, reason_text: reason.trim() } }));
    else r = await unwrap(api.POST("/api/v1/equipment/{equipment_id}/lift-blacklist", { ...path, body: { reason: reason.trim() } }));
    qc.setQueryData(ck.equipment(e.id), r);
    await refresh();
    toast.success(te(`serviceStatus.${r.service_status}`));
  }
  const minReason = step === "blacklist" ? 20 : 5;
  const line = e.current_line;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/equipment" }, { label: e.equipment_no }]} />
        <PageHeader
          title={e.equipment_no}
          description={`${te(`eqc.${e.category}`)}${e.subtype ? ` · ${te(`eqSubtype.${e.subtype}`)}` : ""} · ${e.manufacturer} ${e.model}`}
          actions={
            <>
              <ServiceStatusBadge status={e.service_status} reason={e.service_status_reason} />
              {caps.edit && !terminal ? (
                <Button variant="outline" onClick={() => setStep("edit")} data-testid="edit-equipment">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              {caps.edit && !terminal && pid ? (
                <Button variant="outline" onClick={() => setStep("config")} data-testid="record-config-event">
                  <Wrench aria-hidden />
                  {t("configEvent")}
                </Button>
              ) : null}
              {caps.raise && !terminal && pid && e.service_status !== "out_of_service" ? (
                <Button variant="destructive-outline" onClick={() => setStep("tagout")} data-testid="tag-out">
                  <Tag aria-hidden />
                  {t("tagOut")}
                </Button>
              ) : null}
              {caps.close && e.service_status === "out_of_service" ? (
                <Button onClick={() => setStep("rts")} data-testid="return-to-service">
                  <Undo2 aria-hidden />
                  {t("returnToService")}
                </Button>
              ) : null}
              {caps.blacklist && e.service_status === "blacklisted" ? (
                <Button variant="outline" onClick={() => setStep("lift")} data-testid="lift-blacklist">
                  {t("liftBlacklist")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      <EquipmentStatePanel e={e} />
      {e.configuration_suspended ? <Alert tone="warning">{t("configSuspended")}</Alert> : null}
      <Card data-testid="current-line">
        <CardHeader>
          <CardTitle className="text-base">{t("currentCertificate")}</CardTitle>
        </CardHeader>
        <CardContent>
          {line ? (
            <div className="flex flex-col gap-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Link href={`/equipment-certificates/${line.line.certificate_id}`} className="font-medium text-primary hover:underline" data-testid="current-cert-no">
                  <Code>{line.line.cert_no}</Code>
                </Link>
                <Code className="text-muted-foreground">{line.line.tpi_code}</Code>
                {line.in_force ? (
                  <Badge tone="success">
                    <CircleCheck aria-hidden />
                    {t("inForce")}
                  </Badge>
                ) : (
                  <Badge tone="danger">
                    <OctagonX aria-hidden />
                    {t("notInForce")}
                  </Badge>
                )}
                {line.line.valid_until ? (
                  <span className="inline-flex items-start gap-1">
                    {t("validUntil")}: <StackedDate v={line.line.valid_until} projectId={project?.id} className="font-medium" />
                  </span>
                ) : null}
                {line.in_force ? <DaysLeft days={line.days_left} /> : null}
              </div>
              <span className="text-xs text-muted-foreground">
                {t("inspectedOn", { date: date(line.inspected_on) })} · {te(`lineResult.${line.result as S["LineResult"]}`)}
                {line.swl_t ? ` · ${t("swlT", { swl: line.swl_t })}` : ""}
              </span>
              <EquipmentLimitations items={line.limitations} />
              {line.tpi_accreditation_lapsed ? (
                <span className="inline-flex items-start gap-1 text-xs font-medium text-warning">
                  <TriangleAlert aria-hidden className="mt-px size-3.5 shrink-0" />
                  {t("accreditationLapsedNote")}
                </span>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noCertificate")}</p>
          )}
        </CardContent>
      </Card>
      {e.open_defects.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("openDefects", { n: e.open_defects.length })}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2" data-testid="open-defects">
              {e.open_defects.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <Link href={`/defects/${d.id}`} className="text-primary hover:underline">
                    <Code>{d.defect_no}</Code>
                  </Link>
                  <StatusBadge status={`defect_${d.category}`} label={te(`defectCategory.${d.category}`)} />
                  <span className="text-xs text-muted-foreground">{te(`defectStatus.${d.status as S["DefectStatus"]}`)}</span>
                  {d.due_date ? <span className="text-xs">{t("dueOn", { date: date(d.due_date) })}</span> : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("serial")} ltr>
              {e.serial_no}
            </FieldItem>
            <FieldItem label={t("year")}>{e.year_of_manufacture}</FieldItem>
            <FieldItem label={t("owner")}>
              <Code>{e.owner_short_code}</Code>
              {e.hired_from ? <span className="ms-1 text-xs text-muted-foreground">({t("hiredFromX", { x: e.hired_from })})</span> : null}
            </FieldItem>
            <FieldItem label={t("fleetNo")} ltr>
              {e.owner_fleet_no ?? "—"}
            </FieldItem>
            <FieldItem label={t("vehicle")}>
              {e.vehicle ? (
                <Link href={`/vehicles/${e.vehicle.id}`} className="text-primary hover:underline">
                  <Code>{e.vehicle.vehicle_no}</Code>
                </Link>
              ) : (
                "—"
              )}
            </FieldItem>
            <FieldItem label={t("ratedCapacity")}>{e.rated_capacity_t ? t("tonnes", { v: e.rated_capacity_t }) : "—"}</FieldItem>
            <FieldItem label={t("maxRadius")}>{e.max_radius_m ?? "—"}</FieldItem>
            <FieldItem label={t("maxHeight")}>{e.max_height_m ?? "—"}</FieldItem>
            <FieldItem label={t("persons")}>{e.persons_capacity ?? "—"}</FieldItem>
            <FieldItem label={t("liftingDuty")}>{e.lifting_duty ? tc("yes") : tc("no")}</FieldItem>
            {e.pressure ? (
              <FieldItem label={t("pressureTitle")} wide>
                <span className="ltr text-sm">
                  {t("pressure.design")} {e.pressure.design_pressure_bar} · {t("pressure.mawp")} {e.pressure.mawp_bar} · {t("pressure.volume")} {e.pressure.volume_l} · {t("pressure.relief")} {e.pressure.relief_set_bar}
                </span>
              </FieldItem>
            ) : null}
            <FieldItem label={t("safetyDevices")} wide>
              {e.safety_devices.length ? e.safety_devices.map((d) => te(`safetyDevice.${d}`)).join(" · ") : "—"}
            </FieldItem>
            <FieldItem label={t("documents")} wide>
              {e.documents.length
                ? e.documents.map((d, i) => (
                    <span key={i} className="me-3 inline-block">
                      {te(`equipmentDocType.${d.doc_type}`)}: <Code>{d.ref}</Code>
                    </span>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={t("hookCode")}>{e.hook_code ? <Code>{e.hook_code}</Code> : "—"}</FieldItem>
            <FieldItem label={t("operatorCode")}>{e.operator_code ? <Code>{e.operator_code}</Code> : "—"}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      {e.blacklist ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("blacklistRecord")}</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldList>
              <FieldItem label={t("from")}>{date(e.blacklist.from_date)}</FieldItem>
              <FieldItem label={tc("reason")}>{e.blacklist.reason_code ? te(`equipmentBlacklistReason.${e.blacklist.reason_code}`) : t("reasonHidden")}</FieldItem>
              {e.blacklist.reason_text ? (
                <FieldItem label={t("details")} wide>
                  {e.blacklist.reason_text}
                </FieldItem>
              ) : null}
              <FieldItem label={t("by")}>
                <UserName u={e.blacklist.by} />
              </FieldItem>
              {e.blacklist.lifted_at ? <FieldItem label={t("liftedAt")}>{dateTime(e.blacklist.lifted_at)}</FieldItem> : null}
            </FieldList>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("deployments")}</CardTitle>
        </CardHeader>
        <CardContent>
          {e.deployments.length ? (
            <ul className="flex flex-col gap-2" data-testid="item-deployments">
              {e.deployments.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <Link href={`/equipment-deployments/${d.id}`} className="text-primary hover:underline">
                    <Code>{d.deployment_no}</Code>
                  </Link>
                  <Code>
                    {d.project_code}-{d.tag}
                  </Code>
                  <StatusBadge status={d.status} label={te(`eqDeploymentStatus.${d.status}`)} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noDeployments")}</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("statusHistory")}</CardTitle>
        </CardHeader>
        <CardContent>
          {events.isLoading ? (
            <LoadingState rows={2} />
          ) : (events.data?.items ?? []).length ? (
            <ol className="flex flex-col gap-2 border-s ps-4" data-testid="status-events">
              {(events.data?.items ?? []).map((ev) => (
                <li key={ev.id} className="text-sm">
                  <StackedDate v={ev.occurred_at} time projectId={project?.id} className="text-xs text-muted-foreground" />{" "}
                  {ev.from_status ? <span className="text-muted-foreground">{te(`serviceStatus.${ev.from_status}`)} → </span> : null}
                  <span className="font-medium">{te(`serviceStatus.${ev.to_status}`)}</span>
                  {ev.reason ? <span className="text-muted-foreground"> · {te(`serviceStatusReason.${ev.reason}`)}</span> : null}
                  {ev.ref ? (
                    <span className="ms-1">
                      <Code>{ev.ref}</Code>
                    </span>
                  ) : null}
                  {ev.text ? <span className="block text-xs">{ev.text}</span> : null}
                  {ev.actor ? (
                    <span className="block text-xs text-muted-foreground">
                      <UserName u={ev.actor} />
                    </span>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">{th("empty")}</p>
          )}
        </CardContent>
      </Card>
      {(configs.data?.items ?? []).length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("configEvents")}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table data-testid="config-events">
              <THead>
                <TR>
                  <TH>{t("occurredAt")}</TH>
                  <TH>{t("eventType")}</TH>
                  <TH>{t("newConfiguration")}</TH>
                  <TH>{t("suspendedLines")}</TH>
                  <TH>{t("clearedBy")}</TH>
                </TR>
              </THead>
              <TBody>
                {(configs.data?.items ?? []).map((c) => (
                  <TR key={c.id}>
                    <TD label={t("occurredAt")}>
                      <StackedDate v={c.occurred_at} time projectId={project?.id} />
                      {c.late_record ? (
                        <span className="flex items-center gap-1 text-xs font-medium text-warning">
                          <Clock aria-hidden className="size-3.5 shrink-0" />
                          {t("lateRecord")}
                        </span>
                      ) : null}
                    </TD>
                    <TD label={t("eventType")}>{te(`configEventType.${c.event_type}`)}</TD>
                    <TD label={t("newConfiguration")}>
                      {c.new_configuration}
                      {c.new_height_m ? <span className="block text-xs text-muted-foreground">{c.new_height_m} m</span> : null}
                    </TD>
                    <TD label={t("suspendedLines")}>
                      {c.suspended_lines.map((l) => (
                        <Code key={l.line_id} className="me-1">
                          {l.cert_no}
                        </Code>
                      ))}
                    </TD>
                    <TD label={t("clearedBy")}>
                      {c.cleared_by ? (
                        <Code>{c.cleared_by.cert_no}</Code>
                      ) : (
                        <Badge tone="warning">
                          <Hourglass aria-hidden />
                          {t("notCleared")}
                        </Badge>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
      <HistoryPanel entityType="equipment_item" entityId={e.id} />
      {(caps.close && !terminal) || (caps.blacklist && e.service_status !== "blacklisted") ? (
        // Retire / Blacklist cannot be undone: at the page end, apart from Tag out (a stop-use step, kept at the top).
        <RecordActions className="mt-0" label={td("irreversible")}>
          {caps.close && !terminal ? (
            <Button variant="destructive-outline" onClick={() => setStep("retire")} data-testid="retire-equipment">
              <Archive aria-hidden />
              {t("retire")}
            </Button>
          ) : null}
          {caps.blacklist && e.service_status !== "blacklisted" ? (
            <Button variant="destructive-outline" onClick={() => setStep("blacklist")} data-testid="blacklist-equipment">
              <Ban aria-hidden />
              {t("blacklist")}
            </Button>
          ) : null}
        </RecordActions>
      ) : null}
      {step === "edit" ? <EquipmentEditDialog e={e} projectId={pid} onClose={() => setStep(null)} /> : null}
      {step === "config" && pid ? <ConfigEventDialog e={e} projectId={pid} onClose={() => setStep(null)} /> : null}
      {step && step !== "edit" && step !== "config" ? (
        <StepDialog
          title={t(`${step}Title`)}
          description={t(`${step}Hint`)}
          confirmLabel={t(`${step}Confirm`)}
          destructive={step === "tagout" || step === "retire" || step === "blacklist"}
          warning={step === "retire" || step === "blacklist" ? td("irreversible") : undefined}
          disabled={reason.trim().length < minReason}
          onClose={() => {
            setStep(null);
            setReason("");
          }}
          onConfirm={run}
          testId="equipment-confirm"
        >
          {step === "tagout" ? <Tick id="to-physical" label={t("physicalTag")} checked={physical} onChange={setPhysical} /> : null}
          {step === "retire" ? (
            <FormField id="rt-reason" label={t("retireReason")} required>
              <Select value={retireReason} onChange={(ev) => setRetireReason(ev.target.value as S["RetireReason"])}>
                {RETIRE_REASONS.map((x) => (
                  <option key={x} value={x}>
                    {te(`retireReason.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          {step === "blacklist" ? (
            <FormField id="bl-reason" label={t("blacklistReason")} required>
              <Select value={blReason} onChange={(ev) => setBlReason(ev.target.value as S["EquipmentBlacklistReason"])} data-testid="bl-reason-code">
                {EQUIPMENT_BLACKLIST_REASONS.map((x) => (
                  <option key={x} value={x}>
                    {te(`equipmentBlacklistReason.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          <FormField id="eq-reason" label={step === "rts" ? t("rtsNote") : tc("reason")} required hint={minReason === 20 ? t("reason20") : undefined}>
            <Textarea value={reason} onChange={(ev) => setReason(ev.target.value)} maxLength={1000} data-testid="eq-reason" />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

const STOP: S["ServiceStatus"][] = ["out_of_service", "quarantined", "blacklisted"];

/**
 * Equipment state at a glance, worded from the server's service status and has_valid_certificate (the UI decides
 * nothing): red "do not use" for out of service / quarantined / blacklisted or no certificate in force, blue while
 * awaiting a certificate, grey once retired, green only when in service with a certificate in force.
 */
function EquipmentStatePanel({ e }: { e: S["EquipmentRead"] }) {
  const t = useTranslations("equipment");
  const td = useTranslations("certDesign");
  const te = useTranslations("enums");
  const { project } = useCurrentProject();
  const { date, dateTime } = useFormatters(project?.id);
  const stop = STOP.includes(e.service_status);
  const ok = e.service_status === "in_service" && e.has_valid_certificate;
  const tone: StateTone = stop || (e.service_status === "in_service" && !e.has_valid_certificate) ? "danger" : ok ? "success" : e.service_status === "retired" ? "neutral" : "info";
  const Icon = stop ? (e.service_status === "blacklisted" ? Ban : OctagonX) : ok ? CircleCheck : e.service_status === "retired" ? Archive : e.service_status === "awaiting_certificate" ? Hourglass : OctagonX;
  const word = stop ? te(`serviceStatus.${e.service_status}`) : ok ? td("eq.inServiceOk") : e.service_status === "in_service" ? td("eq.noCert") : te(`serviceStatus.${e.service_status}`);
  const line = stop ? t(`stop.${e.service_status as "out_of_service" | "quarantined" | "blacklisted"}`) : ok ? td("eq.inServiceOkLine") : e.service_status === "in_service" ? td("eq.noCertLine") : e.service_status === "retired" ? td("eq.retiredLine") : td("eq.awaitingLine");
  const line_ = e.current_line;
  const onSite = e.deployments.filter((d) => d.status === "on_site" || d.status === "approved");
  return (
    <CertStatePanel
      tone={tone}
      Icon={Icon}
      word={word}
      sub={stop && e.service_status_reason && e.service_status_reason !== e.service_status ? te(`serviceStatusReason.${e.service_status_reason}`) : undefined}
      line={line}
      testId={stop ? "equipment-stop" : "equipment-state"}
      data={{ "data-status": e.service_status }}
    >
      {stop && e.service_status_text ? (
        <p className="whitespace-pre-line" dir="auto">
          {e.service_status_text}
        </p>
      ) : null}
      {stop && e.service_status_since ? <p className="text-xs text-muted-foreground">{t("since", { at: dateTime(e.service_status_since) })}</p> : null}
      {!stop && line_ && line_.in_force && line_.line.valid_until ? (
        <p className="flex flex-wrap items-center gap-2">
          <span>
            {t("validUntil")}: <span className="font-semibold">{date(line_.line.valid_until)}</span>
          </span>
          <DaysLeft days={line_.days_left} />
        </p>
      ) : null}
      {onSite.length ? (
        <p className="flex flex-wrap gap-x-3 gap-y-1">
          {onSite.map((d) => (
            <Link key={d.id} href={`/equipment-deployments/${d.id}`} className="font-medium text-primary hover:underline">
              {td("eq.onProject", { ref: `${d.project_code}-${d.tag}` })} <span aria-hidden className="inline-block rtl:-scale-x-100">→</span>
            </Link>
          ))}
        </p>
      ) : null}
    </CertStatePanel>
  );
}

function EquipmentEditDialog({ e, projectId, onClose }: { e: S["EquipmentRead"]; projectId: string | null; onClose: () => void }) {
  const t = useTranslations("equipment");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [model, setModel] = useState(e.model);
  const [fleet, setFleet] = useState(e.owner_fleet_no ?? "");
  const [vehicle, setVehicle] = useState(e.vehicle?.id ?? "");
  const [capacity, setCapacity] = useState(e.rated_capacity_t ?? "");
  const [radius, setRadius] = useState(e.max_radius_m ?? "");
  const [height, setHeight] = useState(e.max_height_m ?? "");
  const [liftingDuty, setLiftingDuty] = useState(e.lifting_duty);
  const [devices, setDevices] = useState<S["SafetyDevice"][]>(e.safety_devices);
  const [docs, setDocs] = useState<DocRow[]>(e.documents.map((d) => ({ doc_type: d.doc_type, ref: d.ref })));
  async function save() {
    const r = await unwrap(
      api.PATCH("/api/v1/equipment/{equipment_id}", {
        params: { path: { equipment_id: e.id } },
        body: {
          model: model.trim(),
          owner_fleet_no: fleet.trim() || null,
          vehicle_id: vehicle || null,
          rated_capacity_t: capacity || null,
          max_radius_m: radius || null,
          max_height_m: height || null,
          lifting_duty: liftingDuty,
          safety_devices: devices,
          documents: docs.filter((d) => d.ref.trim()).map((d) => ({ doc_type: d.doc_type, ref: d.ref.trim() })),
        },
      }),
    );
    qc.setQueryData(ck.equipment(e.id), r);
    await qc.invalidateQueries({ queryKey: ["equipment"] });
    toast.success(tc("saved"));
  }
  return (
    <StepDialog title={t("edit")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!model.trim()} wide testId="save-equipment">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ee-model" label={t("model")} required>
          <Input value={model} onChange={(ev) => setModel(ev.target.value)} />
        </FormField>
        <FormField id="ee-fleet" label={t("fleetNo")}>
          <Input value={fleet} onChange={(ev) => setFleet(ev.target.value)} className="ltr" />
        </FormField>
        {projectId ? (
          <FormField id="ee-vehicle" label={t("vehicle")} hint={t("vehicleHint")}>
            <VehicleSelect id="ee-vehicle" projectId={projectId} value={vehicle} onChange={(v) => setVehicle(v)} placeholder={t("noVehicle")} />
          </FormField>
        ) : null}
        <FormField id="ee-cap" label={t("ratedCapacity")}>
          <DecimalInput id="ee-cap" value={capacity} onChange={setCapacity} />
        </FormField>
        <FormField id="ee-radius" label={t("maxRadius")}>
          <DecimalInput id="ee-radius" value={radius} onChange={setRadius} />
        </FormField>
        <FormField id="ee-height" label={t("maxHeight")}>
          <DecimalInput id="ee-height" value={height} onChange={setHeight} />
        </FormField>
      </div>
      <Tick id="ee-lifting-duty" label={t("liftingDuty")} checked={liftingDuty} onChange={setLiftingDuty} />
      <CheckboxGroup id="ee-devices" legend={t("safetyDevices")} options={SAFETY_DEVICES.map((d) => ({ value: d, label: te(`safetyDevice.${d}`) }))} value={devices} onChange={setDevices} />
      <DocsEditor docs={docs} onChange={setDocs} />
    </StepDialog>
  );
}

/** CF-1/CF-2: a configuration event suspends the current line at once (hard stop) until a new inspection clears it. */
function ConfigEventDialog({ e, projectId, onClose }: { e: S["EquipmentRead"]; projectId: string; onClose: () => void }) {
  const t = useTranslations("equipment");
  const te = useTranslations("enums");
  const refresh = useCertRefresh();
  const [type, setType] = useState<S["ConfigurationEventType"]>("climb_jacking");
  const [at, setAt] = useState("");
  const [config, setConfig] = useState("");
  const [height, setHeight] = useState("");
  async function save() {
    const r = await unwrap(
      api.POST("/api/v1/equipment/{equipment_id}/configuration-events", {
        params: { path: { equipment_id: e.id } },
        body: { project_id: projectId, event_type: type, occurred_at: at, new_configuration: config.trim(), new_height_m: height || null },
      }),
    );
    await refresh();
    toast.warning(t("configRecorded", { n: r.suspended_lines.length }));
  }
  return (
    <StepDialog title={t("configEvent")} description={t("configHint")} warning={t("configWarning")} confirmLabel={t("configEvent")} destructive onConfirm={save} onClose={onClose} disabled={!at || !config.trim()} wide testId="config-confirm">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ce-type" label={t("eventType")} required>
          <Select value={type} onChange={(ev) => setType(ev.target.value as S["ConfigurationEventType"])} data-testid="ce-type">
            {CONFIGURATION_EVENT_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`configEventType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ce-at" label={t("occurredAt")} required hint={t("occurredAtHint")}>
          <DateTimeInput id="ce-at" value={at} onChange={setAt} data-testid="ce-at" />
        </FormField>
        <FormField id="ce-config" label={t("newConfiguration")} required>
          <Input value={config} onChange={(ev) => setConfig(ev.target.value)} data-testid="ce-config" />
        </FormField>
        <FormField id="ce-height" label={t("newHeight")}>
          <DecimalInput id="ce-height" value={height} onChange={setHeight} />
        </FormField>
      </div>
    </StepDialog>
  );
}
