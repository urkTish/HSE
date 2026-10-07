"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Pencil, Plus, Printer, RefreshCw, Sticker } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { AREA_CATEGORIES, AVP_CHECKLIST_ITEMS, AVP_NO_NA, CHECKLIST_OUTCOMES, PLATE_TYPES, VALIDITY_STATUSES, VEHICLE_CATEGORIES, VEHICLE_OWNER_TYPES, VEHICLE_STATUSES } from "@/lib/access-enums";
import { ak, useAvp, useAvpSticker, useAvps, useVehicle, useVehicles } from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { joinList } from "@/lib/i18n-helpers";
import { todayInZone } from "@/lib/datetime";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { AirportOnly, Code, DaysLeft, Plate, QrImage, StepDialog, SubNav, ValidityBadge, ValidityLine } from "./common";
import { CredentialPanel } from "./credential-actions";

const PAGE_SIZE = 50;
type Vehicle = Schemas["VehicleRead"];
type Avp = Schemas["AvpRead"];
type Item = Schemas["AvpChecklistItem"];
type Outcome = Schemas["ChecklistOutcome"];

function VehicleSubNav({ airport }: { airport: boolean }) {
  const t = useTranslations("vehicles");
  return (
    <SubNav
      items={[
        { href: "/vehicles", label: t("title"), testId: "sub-vehicles" },
        { href: "/avps", label: t("avps"), show: airport, testId: "sub-avps" },
      ]}
    />
  );
}

/* ───────────────────────────── Vehicle list ───────────────────────────── */

export function VehicleListPage() {
  return <ProjectGate>{(p) => <VehicleList project={p} />}</ProjectGate>;
}

function VehicleList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("vehicles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["VehicleStatus"][];
  const cats = s.getAll("category") as Schemas["VehicleCategory"][];
  const engs = s.getAll("engagement_id");
  const query = useVehicles(project.id, {
    status: status.length ? status : null,
    category: cats.length ? cats : null,
    engagement_id: engs.length ? engs : null,
    documents_expiring_within_days: s.getInt("documents_expiring_within_days", 0) || null,
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
          canWrite(me, "vehicle.edit", project.id) ? (
            <Button asChild>
              <Link href="/vehicles/new" data-testid="new-vehicle">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <VehicleSubNav airport={project.is_airport} />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="vehicles" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="vh-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="vh-status" label={tc("status")} options={VEHICLE_STATUSES.map((x) => ({ value: x, label: te(`vehicleStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="vh-cat" label={t("fields.category")} options={VEHICLE_CATEGORIES.map((x) => ({ value: x, label: te(`vehicleCategory.${x}`) }))} value={cats} onChange={(v) => s.set({ category: v })} />
        <MultiSelect id="vh-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <SelectFilter
          id="vh-docs"
          label={t("docsExpiring")}
          value={s.get("documents_expiring_within_days") ?? ""}
          onChange={(v) => s.set({ documents_expiring_within_days: v })}
          options={[
            { value: "30", label: t("withinDays", { n: 30 }) },
            { value: "7", label: t("withinDays", { n: 7 }) },
          ]}
        />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="vehicles-table">
            <THead>
              <TR>
                <TH>{t("fields.vehicle_no")}</TH>
                <TH>{t("fields.plate")}</TH>
                <TH>{t("fields.category")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("fields.max_working_height_m_agl")}</TH>
                <TH>{t("documents")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((v) => (
                <TR key={v.id} data-testid="vehicle-row">
                  <TD label={t("fields.vehicle_no")}>
                    <Link href={`/vehicles/${v.id}`} className="ltr font-medium text-primary hover:underline">
                      {v.vehicle_no}
                    </Link>
                    <span className="block text-xs text-muted-foreground ltr">{v.fleet_no}</span>
                  </TD>
                  <TD label={t("fields.plate")}>
                    <Plate ar={v.plate_letters_ar} en={v.plate_letters_en} digits={v.plate_digits} />
                  </TD>
                  <TD label={t("fields.category")}>{te(`vehicleCategory.${v.category}`)}</TD>
                  <TD label={tc("contractor")}>{v.engagement.short_code}</TD>
                  <TD label={t("fields.max_working_height_m_agl")}>
                    <span className="ltr tabular-nums">{t("mFt", { m: v.max_working_height_m_agl, ft: v.max_working_height_ft })}</span>
                  </TD>
                  <TD label={t("documents")}>
                    {v.documents_valid ? <StatusBadge status="valid" label={t("docsValid")} /> : <StatusBadge status="expired" label={t("docsExpired")} />}
                    {v.earliest_document_expiry ? <span className="block text-xs text-muted-foreground">{date(v.earliest_document_expiry)}</span> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={v.status} label={te(`vehicleStatus.${v.status}`)} />
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

/* ───────────────────────────── Vehicle form ───────────────────────────── */

export function VehicleCreatePage() {
  const t = useTranslations("vehicles");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/vehicles" }, { label: t("new") }]} />
      <PageHeader title={t("new")} />
      <ProjectGate>{(p) => <VehicleForm project={p} />}</ProjectGate>
    </div>
  );
}

export function VehicleEditPage({ id }: { id: string }) {
  const t = useTranslations("vehicles");
  const q = useVehicle(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const v = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/vehicles" }, { label: v.vehicle_no, href: `/vehicles/${v.id}` }, { label: t("edit") }]} />
      <PageHeader title={t("edit")} />
      <ProjectById id={v.project_id}>{(p) => <VehicleForm project={p} vehicle={v} />}</ProjectById>
    </div>
  );
}

const VIN = /^[A-HJ-NPR-Z0-9]{17}$/;

function VehicleForm({ project, vehicle }: { project: Schemas["ProjectRead"]; vehicle?: Vehicle }) {
  const t = useTranslations("vehicles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const me = useMeData();
  const opts = useProjectOptions(project.id);
  const ownEng = me.employer_type === "contractor" ? opts.engagements.find((e) => e.status !== "blacklisted")?.value : undefined;
  const [f, setF] = useState({
    engagement_id: vehicle?.engagement.id ?? "",
    owner_type: (vehicle?.owner_type ?? "company") as Schemas["VehicleOwnerType"],
    category: (vehicle?.category ?? "pickup") as Schemas["VehicleCategory"],
    plate_type: (vehicle?.plate_type ?? "private") as Schemas["PlateType"],
    plate_letters_ar: vehicle?.plate_letters_ar ?? "",
    plate_letters_en: vehicle?.plate_letters_en ?? "",
    plate_digits: vehicle?.plate_digits ?? "",
    fleet_no: vehicle?.fleet_no ?? "",
    serial_or_vin: vehicle?.serial_or_vin ?? "",
    make_model: vehicle?.make_model ?? "",
    year: String(vehicle?.year ?? new Date().getFullYear()),
    colour: vehicle?.colour ?? "",
    travel_height_m: vehicle?.travel_height_m ?? "",
    max_working_height_m_agl: vehicle?.max_working_height_m_agl ?? "",
    istimara_expiry: vehicle?.istimara_expiry ?? "",
    insurance_policy_no: vehicle?.insurance_policy_no ?? "",
    insurance_expiry: vehicle?.insurance_expiry ?? "",
    mvpi_expiry: vehicle?.mvpi_expiry ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const plated = f.plate_type !== "none";
  const engagement = f.engagement_id || ownEng || "";
  const roadVehicle = plated;
  const ftOf = (m: string) => (m && !Number.isNaN(Number(m)) ? (Number(m) / 0.3048).toFixed(2) : "—");

  async function save() {
    const e: Record<string, string> = {};
    const req = (k: keyof typeof f) => {
      if (!String(f[k]).trim()) e[k] = tv("required");
    };
    if (!vehicle && !engagement) e.engagement_id = tv("required");
    (["fleet_no", "serial_or_vin", "make_model", "colour", "travel_height_m", "max_working_height_m_agl", "insurance_policy_no", "insurance_expiry"] as const).forEach(req);
    if (plated) (["plate_letters_ar", "plate_digits", "istimara_expiry", "mvpi_expiry"] as const).forEach(req);
    if (plated && f.plate_digits && !/^\d{1,4}$/.test(f.plate_digits)) e.plate_digits = t("plateDigitsHint");
    if (roadVehicle && f.serial_or_vin && !VIN.test(f.serial_or_vin.toUpperCase())) e.serial_or_vin = t("vinHint");
    if (Number(f.max_working_height_m_agl) < Number(f.travel_height_m)) e.max_working_height_m_agl = t("workingBelowTravel");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    const body = {
      owner_type: f.owner_type,
      category: f.category,
      plate_type: f.plate_type,
      plate_letters_ar: plated ? f.plate_letters_ar.trim() : null,
      plate_letters_en: plated ? f.plate_letters_en.trim().toUpperCase() || null : null,
      plate_digits: plated ? f.plate_digits.trim() : null,
      fleet_no: f.fleet_no.trim(),
      serial_or_vin: f.serial_or_vin.trim().toUpperCase(),
      make_model: f.make_model.trim(),
      year: Number(f.year),
      colour: f.colour.trim(),
      travel_height_m: f.travel_height_m,
      max_working_height_m_agl: f.max_working_height_m_agl,
      istimara_expiry: plated ? f.istimara_expiry : null,
      insurance_policy_no: f.insurance_policy_no.trim(),
      insurance_expiry: f.insurance_expiry,
      mvpi_expiry: plated ? f.mvpi_expiry : null,
    };
    try {
      const v = vehicle
        ? await unwrap(api.PATCH("/api/v1/vehicles/{vehicle_id}", { params: { path: { vehicle_id: vehicle.id } }, body }))
        : await unwrap(api.POST("/api/v1/projects/{project_id}/vehicles", { params: { path: { project_id: project.id } }, body: { ...body, engagement_id: engagement } }));
      qc.setQueryData(ak.vehicle(v.id), v);
      await qc.invalidateQueries({ queryKey: ["vehicles"] });
      await qc.invalidateQueries({ queryKey: ["avps"] });
      warn(v.warnings);
      toast.success(tc("saved"));
      router.push(`/vehicles/${v.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      autoComplete="off"
      data-testid="vehicle-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <FormSection title={t("vehicle")}>
        <FormField id="vf-eng" label={tc("contractor")} required error={errors.engagement_id}>
          <Select value={engagement} disabled={Boolean(vehicle)} onChange={set("engagement_id")}>
            <option value="">{tc("select")}</option>
            {opts.engagements.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="vf-owner" label={t("fields.owner_type")} required>
          <Select value={f.owner_type} onChange={set("owner_type")}>
            {VEHICLE_OWNER_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`vehicleOwnerType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="vf-cat" label={t("fields.category")} required>
          <Select value={f.category} onChange={set("category")}>
            {VEHICLE_CATEGORIES.map((x) => (
              <option key={x} value={x}>
                {te(`vehicleCategory.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="vf-fleet" label={t("fields.fleet_no")} required error={errors.fleet_no}>
          <Input className="ltr" maxLength={20} value={f.fleet_no} onChange={set("fleet_no")} />
        </FormField>
        <FormField id="vf-make" label={t("fields.make_model")} required error={errors.make_model}>
          <Input maxLength={80} value={f.make_model} onChange={set("make_model")} />
        </FormField>
        <FormField id="vf-year" label={t("fields.year")} required>
          <Input type="number" min={1990} max={new Date().getFullYear() + 1} value={f.year} onChange={set("year")} />
        </FormField>
        <FormField id="vf-colour" label={t("fields.colour")} required error={errors.colour}>
          <Input maxLength={30} value={f.colour} onChange={set("colour")} />
        </FormField>
        <FormField id="vf-vin" label={t("fields.serial_or_vin")} required error={errors.serial_or_vin} hint={roadVehicle ? t("vinHint") : undefined}>
          <Input className="ltr uppercase" maxLength={30} value={f.serial_or_vin} onChange={set("serial_or_vin")} />
        </FormField>
      </FormSection>
      <FormSection title={t("plate")}>
        <FormField id="vf-plate-type" label={t("fields.plate_type")} required>
          <Select value={f.plate_type} onChange={set("plate_type")}>
            {PLATE_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`plateType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {plated ? (
          <>
            <FormField id="vf-plate-ar" label={t("fields.plate_letters_ar")} required error={errors.plate_letters_ar}>
              <Input dir="rtl" lang="ar" maxLength={5} value={f.plate_letters_ar} onChange={set("plate_letters_ar")} />
            </FormField>
            <FormField id="vf-plate-en" label={t("fields.plate_letters_en")}>
              <Input className="ltr uppercase" maxLength={5} value={f.plate_letters_en} onChange={set("plate_letters_en")} />
            </FormField>
            <FormField id="vf-plate-digits" label={t("fields.plate_digits")} required error={errors.plate_digits}>
              <Input className="ltr" inputMode="numeric" maxLength={4} value={f.plate_digits} onChange={set("plate_digits")} />
            </FormField>
          </>
        ) : null}
        {f.owner_type === "individual" && plated ? (
          <Alert tone="info" className="sm:col-span-2">
            {t("personalPlate")}
          </Alert>
        ) : null}
      </FormSection>
      <FormSection title={t("heights")} description={t("heightsHint")}>
        <FormField id="vf-travel" label={t("fields.travel_height_m")} required error={errors.travel_height_m} hint={`${ftOf(f.travel_height_m)} ft`}>
          <Input type="number" min={0.5} max={20} step="0.01" className="ltr" value={f.travel_height_m} onChange={set("travel_height_m")} />
        </FormField>
        <FormField id="vf-working" label={t("fields.max_working_height_m_agl")} required error={errors.max_working_height_m_agl} hint={`${ftOf(f.max_working_height_m_agl)} ft`}>
          <Input type="number" min={0.5} step="0.01" className="ltr" value={f.max_working_height_m_agl} onChange={set("max_working_height_m_agl")} />
        </FormField>
      </FormSection>
      <FormSection title={t("documents")}>
        {plated ? (
          <>
            <FormField id="vf-istimara" label={t("fields.istimara_expiry")} required error={errors.istimara_expiry}>
              <Input type="date" value={f.istimara_expiry} onChange={set("istimara_expiry")} />
            </FormField>
            <FormField id="vf-mvpi" label={t("fields.mvpi_expiry")} required error={errors.mvpi_expiry}>
              <Input type="date" value={f.mvpi_expiry} onChange={set("mvpi_expiry")} />
            </FormField>
          </>
        ) : null}
        <FormField id="vf-ins-no" label={t("fields.insurance_policy_no")} required error={errors.insurance_policy_no}>
          <Input className="ltr" maxLength={40} value={f.insurance_policy_no} onChange={set("insurance_policy_no")} />
        </FormField>
        <FormField id="vf-ins-exp" label={t("fields.insurance_expiry")} required error={errors.insurance_expiry}>
          <Input type="date" value={f.insurance_expiry} onChange={set("insurance_expiry")} />
        </FormField>
      </FormSection>
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-vehicle">
          {busy ? tc("saving") : tc("save")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

/* ───────────────────────────── Vehicle detail ───────────────────────────── */

export function VehicleDetail({ id }: { id: string }) {
  const t = useTranslations("vehicles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const q = useVehicle(id);
  const qc = useQueryClient();
  const [to, setTo] = useState<Schemas["VehicleStatus"] | null>(null);
  const [reason, setReason] = useState("");
  const [apply, setApply] = useState(false);
  const { date } = useFormatters(q.data?.project_id);
  const avps = useAvps(q.data?.project_id ?? "", { vehicle_id: id, page_size: 20 }, { enabled: Boolean(q.data) });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const v = q.data;
  const edit = canWrite(me, "vehicle.edit", v.project_id);
  const next: Schemas["VehicleStatus"][] = v.status === "active" ? ["off_site", "withdrawn"] : v.status === "off_site" ? ["active", "withdrawn"] : [];
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/vehicles" }, { label: v.vehicle_no }]} />
        <PageHeader
          title={v.vehicle_no}
          description={`${v.make_model} · ${te(`vehicleCategory.${v.category}`)} · ${v.engagement.short_code}`}
          actions={
            <>
              <StatusBadge status={v.status} label={te(`vehicleStatus.${v.status}`)} />
              {edit ? (
                <Button variant="outline" asChild>
                  <Link href={`/vehicles/${v.id}/edit`} data-testid="edit-vehicle">
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Link>
                </Button>
              ) : null}
              {edit && v.status === "active" && !v.active_avp_id ? (
                <Button onClick={() => setApply(true)} data-testid="apply-avp">
                  <Sticker aria-hidden />
                  {t("applyAvp")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {edit && next.length ? (
        <div className="flex flex-wrap gap-2">
          {next.map((s) => (
            <Button
              key={s}
              size="sm"
              variant={s === "withdrawn" ? "destructive" : "outline"}
              onClick={() => {
                setReason("");
                setTo(s);
              }}
              data-testid={`vehicle-${s}`}
            >
              {t("setStatus", { status: te(`vehicleStatus.${s}`) })}
            </Button>
          ))}
        </div>
      ) : null}
      {!v.documents_valid ? <Alert tone="danger">{t("docsExpiredHint")}</Alert> : null}
      <ApiWarnings warnings={v.warnings} />
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("fields.plate")}>
              <Plate ar={v.plate_letters_ar} en={v.plate_letters_en} digits={v.plate_digits} />
            </FieldItem>
            <FieldItem label={t("fields.plate_type")}>{te(`plateType.${v.plate_type}`)}</FieldItem>
            <FieldItem label={t("fields.fleet_no")} ltr>
              {v.fleet_no}
            </FieldItem>
            <FieldItem label={t("fields.serial_or_vin")} ltr>
              {v.serial_or_vin}
            </FieldItem>
            <FieldItem label={t("fields.owner_type")}>{te(`vehicleOwnerType.${v.owner_type}`)}</FieldItem>
            <FieldItem label={t("fields.year")}>{v.year}</FieldItem>
            <FieldItem label={t("fields.colour")}>{v.colour}</FieldItem>
            <FieldItem label={t("fields.travel_height_m")}>
              <span className="ltr">{v.travel_height_m} m</span>
            </FieldItem>
            <FieldItem label={t("fields.max_working_height_m_agl")}>
              <span className="ltr">{t("mFt", { m: v.max_working_height_m_agl, ft: v.max_working_height_ft })}</span>
            </FieldItem>
            <FieldItem label={t("fields.istimara_expiry")}>{date(v.istimara_expiry)}</FieldItem>
            <FieldItem label={t("fields.mvpi_expiry")}>{date(v.mvpi_expiry)}</FieldItem>
            <FieldItem label={t("fields.insurance_policy_no")} ltr>
              {v.insurance_policy_no}
            </FieldItem>
            <FieldItem label={t("fields.insurance_expiry")}>{date(v.insurance_expiry)}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("avps")}</CardTitle>
        </CardHeader>
        <CardContent>
          {(avps.data?.items ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noAvps")}</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {(avps.data?.items ?? []).map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <Link href={`/avps/${a.id}`} className="ltr font-medium text-primary hover:underline">
                    {a.avp_no ?? t("pending")}
                  </Link>
                  <span>{joinList(a.areas.map((x) => te(`areaCategory.${x}`)))}</span>
                  <ValidityBadge status={a.validity.validity_status} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <HistoryPanel entityType="vehicle" entityId={v.id} />
      {to ? (
        <StepDialog
          title={t("setStatus", { status: te(`vehicleStatus.${to}`) })}
          description={to === "withdrawn" ? t("withdrawHint") : undefined}
          destructive={to === "withdrawn"}
          confirmLabel={tc("confirm")}
          onConfirm={async () => {
            const u = await unwrap(api.POST("/api/v1/vehicles/{vehicle_id}/transitions", { params: { path: { vehicle_id: v.id } }, body: { to_status: to, reason: reason.trim() || null } }));
            qc.setQueryData(ak.vehicle(v.id), u);
            await qc.invalidateQueries({ queryKey: ["vehicles"] });
          }}
          onClose={() => setTo(null)}
        >
          <FormField id="vh-reason" label={tc("reason")}>
            <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
        </StepDialog>
      ) : null}
      {apply ? <ApplyAvpDialog vehicle={v} onClose={() => setApply(false)} /> : null}
    </div>
  );
}

function ApplyAvpDialog({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const t = useTranslations("vehicles");
  const te = useTranslations("enums");
  const router = useRouter();
  const qc = useQueryClient();
  const [areas, setAreas] = useState<Schemas["AreaCategory"][]>(["apron"]);
  return (
    <StepDialog
      title={t("applyAvp")}
      description={t("applyAvpHint")}
      confirmLabel={t("applyAvp")}
      testId="apply-avp-confirm"
      disabled={areas.length === 0}
      onConfirm={async () => {
        const a = await unwrap(api.POST("/api/v1/projects/{project_id}/avps", { params: { path: { project_id: vehicle.project_id } }, body: { vehicle_id: vehicle.id, areas } }));
        qc.setQueryData(ak.avp(a.id), a);
        await qc.invalidateQueries({ queryKey: ["avps"] });
        router.push(`/avps/${a.id}`);
      }}
      onClose={onClose}
    >
      <MultiSelect id="avp-areas" label={t("fields.areas")} options={AREA_CATEGORIES.map((x) => ({ value: x, label: te(`areaCategory.${x}`) }))} value={areas} onChange={(v) => setAreas(v as Schemas["AreaCategory"][])} className="lg:w-full" />
    </StepDialog>
  );
}

/* ───────────────────────────── AVPs ───────────────────────────── */

export function AvpListPage() {
  return <ProjectGate>{(p) => <AirportOnly project={p}>{<AvpList project={p} />}</AirportOnly>}</ProjectGate>;
}

function AvpList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("vehicles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const validity = s.getAll("validity_status") as Schemas["ValidityStatus"][];
  const engs = s.getAll("engagement_id");
  const query = useAvps(project.id, {
    validity_status: validity.length ? validity : null,
    area: (s.get("area") as Schemas["AreaCategory"] | null) || null,
    engagement_id: engs.length ? engs : null,
    expiring_within_days: s.getInt("expiring_within_days", 0) || null,
    vehicle_id: s.get("vehicle_id") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = query.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("avps")} description={t("avpsHint")} />
      <VehicleSubNav airport />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="avps" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="avp-validity" label={tc("status")} options={VALIDITY_STATUSES.map((x) => ({ value: x, label: te(`validityStatus.${x}`) }))} value={validity} onChange={(v) => s.set({ validity_status: v })} />
        <SelectFilter id="avp-area" label={t("fields.areas")} value={(s.get("area") ?? "") as Schemas["AreaCategory"] | ""} onChange={(v) => s.set({ area: v })} options={AREA_CATEGORIES.map((x) => ({ value: x, label: te(`areaCategory.${x}`) }))} />
        <MultiSelect id="avp-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="avps-table">
            <THead>
              <TR>
                <TH>{t("fields.avp_no")}</TH>
                <TH>{t("vehicle")}</TH>
                <TH>{t("fields.areas")}</TH>
                <TH>{t("fields.sticker_no")}</TH>
                <TH>{t("effectiveUntil")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="avp-row">
                  <TD label={t("fields.avp_no")}>
                    <Link href={`/avps/${a.id}`} className="ltr font-medium text-primary hover:underline">
                      {a.avp_no ?? t("pending")}
                    </Link>
                  </TD>
                  <TD label={t("vehicle")}>
                    <Link href={`/vehicles/${a.vehicle.id}`} className="hover:underline">
                      <Code>{a.vehicle.vehicle_no}</Code> <span className="ltr text-xs">{a.vehicle.fleet_no}</span>
                    </Link>
                    <span className="block text-xs text-muted-foreground">{a.engagement.short_code}</span>
                  </TD>
                  <TD label={t("fields.areas")}>{joinList(a.areas.map((x) => te(`areaCategory.${x}`)))}</TD>
                  <TD label={t("fields.sticker_no")}>
                    <span className="ltr">{a.sticker_no ?? "—"}</span>
                  </TD>
                  <TD label={t("effectiveUntil")}>
                    {date(a.validity.effective_valid_until)} {a.validity.validity_status === "active" ? <DaysLeft days={a.validity.days_left} /> : null}
                    {a.validity.limiting_factor ? <span className="block text-xs text-muted-foreground">{te(`limitingFactor.${a.validity.limiting_factor}`)}</span> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <ValidityBadge status={a.validity.validity_status} />
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

export function AvpDetail({ id }: { id: string }) {
  const t = useTranslations("vehicles");
  const te = useTranslations("enums");
  const me = useMeData();
  const q = useAvp(id);
  const qc = useQueryClient();
  const [step, setStep] = useState<"inspect" | "issue" | "withdraw" | "reissue" | null>(null);
  const { date } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const a = q.data;
  const pending = a.validity.validity_status === "pending";
  const issueCap = canWrite(me, "avp.issue", a.project_id);
  const editCap = canWrite(me, "vehicle.edit", a.project_id);
  async function refresh(u: Avp) {
    qc.setQueryData(ak.avp(a.id), u);
    await qc.invalidateQueries({ queryKey: ["avps"] });
    await qc.invalidateQueries({ queryKey: ["vehicle"] });
  }
  const checklist = a.checklist as Partial<Record<Item, Outcome>>;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("avps"), href: "/avps" }, { label: a.avp_no ?? t("pending") }]} />
        <PageHeader title={a.avp_no ?? t("pendingTitle")} description={`${a.vehicle.vehicle_no} · ${a.vehicle.fleet_no} · ${a.engagement.short_code}`} actions={<ValidityBadge status={a.validity.validity_status} />} />
      </div>
      {pending && (issueCap || editCap) ? (
        <div className="flex flex-wrap gap-2">
          {issueCap ? (
            <>
              <Button variant="outline" onClick={() => setStep("inspect")} data-testid="record-inspection">
                <ClipboardCheck aria-hidden />
                {t("recordInspection")}
              </Button>
              <Button onClick={() => setStep("issue")} disabled={a.checklist_problems.length > 0 || a.inspection_result !== "passed"} data-testid="issue-avp">
                {t("issueAvp")}
              </Button>
            </>
          ) : null}
          <Button variant="destructive" onClick={() => setStep("withdraw")} data-testid="withdraw-avp">
            {t("withdrawAvp")}
          </Button>
        </div>
      ) : null}
      {pending && a.checklist_problems.length ? (
        <Alert tone="warning" data-testid="checklist-problems">
          {t("checklistProblems", { items: joinList(a.checklist_problems.map((i) => te(`checklistItem.${i}`))) })}
        </Alert>
      ) : null}
      {a.hook_warnings.length ? (
        <Alert tone="warning" data-testid="hook-warnings">
          {a.hook_warnings.join(" · ")}
        </Alert>
      ) : null}
      {!pending ? <ValidityLine v={a.validity} projectId={a.project_id} /> : null}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("vehicle")}>
                <Link href={`/vehicles/${a.vehicle.id}`} className="text-primary hover:underline">
                  <Code>{a.vehicle.vehicle_no}</Code> {te(`vehicleCategory.${a.vehicle.category}`)}
                </Link>
              </FieldItem>
              <FieldItem label={t("fields.areas")}>{joinList(a.areas.map((x) => te(`areaCategory.${x}`)))}</FieldItem>
              <FieldItem label={t("fields.inspection_date")}>{date(a.inspection_date)}</FieldItem>
              <FieldItem label={t("fields.inspector")}>{a.inspector ?? "—"}</FieldItem>
              <FieldItem label={t("fields.inspection_result")}>{a.inspection_result ? <StatusBadge status={a.inspection_result} label={te(`inspectionResult.${a.inspection_result}`)} /> : "—"}</FieldItem>
              <FieldItem label={t("fields.sticker_no")} ltr>
                {a.sticker_no ?? "—"}
              </FieldItem>
              <FieldItem label={t("fields.issued_on")}>{date(a.issued_on)}</FieldItem>
              <FieldItem label={t("fields.own_valid_until")}>{date(a.own_valid_until)}</FieldItem>
            </FieldList>
            <h3 className="mt-6 mb-2 text-sm font-semibold">{t("checklist")}</h3>
            <ul className="grid gap-1 sm:grid-cols-2" data-testid="checklist">
              {AVP_CHECKLIST_ITEMS.map((i) => (
                <li key={i} className="flex items-center justify-between gap-2 rounded border px-2 py-1 text-sm">
                  <span>{te(`checklistItem.${i}`)}</span>
                  {checklist[i] ? <StatusBadge status={checklist[i] === "pass" ? "passed" : checklist[i] === "fail" ? "failed" : "not_required"} label={te(`checklistOutcome.${checklist[i] === "n.a." ? "na" : checklist[i]}`)} /> : <span className="text-muted-foreground">—</span>}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-6">
          {!pending && a.sticker_no ? <StickerCard avp={a} canReissue={issueCap} onReissue={() => setStep("reissue")} /> : null}
          {!pending ? <CredentialPanel kind="avp" id={a.id} projectId={a.project_id} onChanged={() => void qc.invalidateQueries({ queryKey: ak.avp(a.id) })} /> : null}
        </div>
      </div>
      <HistoryPanel entityType="avp" entityId={a.id} />
      {step === "inspect" ? <InspectionDialog avp={a} onSaved={refresh} onClose={() => setStep(null)} /> : null}
      {step === "issue" ? <IssueAvpDialog avp={a} onSaved={refresh} onClose={() => setStep(null)} /> : null}
      {step === "withdraw" ? (
        <StepDialog
          title={t("withdrawAvp")}
          destructive
          confirmLabel={t("withdrawAvp")}
          onConfirm={async () => {
            const u = await unwrap(api.POST("/api/v1/avps/{avp_id}/withdraw", { params: { path: { avp_id: a.id } } }));
            await refresh(u);
          }}
          onClose={() => setStep(null)}
        />
      ) : null}
      {step === "reissue" ? <ReissueStickerDialog avp={a} onClose={() => setStep(null)} /> : null}
    </div>
  );
}

function StickerCard({ avp, canReissue, onReissue }: { avp: Avp; canReissue: boolean; onReissue: () => void }) {
  const t = useTranslations("vehicles");
  const te = useTranslations("enums");
  const q = useAvpSticker(avp.id);
  return (
    <Card data-testid="sticker-card">
      <CardHeader>
        <CardTitle className="text-base">{t("sticker")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-3">
        {q.data ? (
          <>
            <QrImage payload={q.data.qr_payload} size={160} label={t("stickerQr", { no: q.data.sticker_no })} />
            <p className="ltr font-mono text-sm font-semibold" data-testid="sticker-ref">
              {q.data.printed_ref}
            </p>
            <StatusBadge status={q.data.token_status} label={te(`qrTokenStatus.${q.data.token_status}`)} />
          </>
        ) : q.isError ? (
          <p className="text-sm text-muted-foreground">—</p>
        ) : (
          <LoadingState rows={2} />
        )}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" asChild>
            <Link href={`/avps/${avp.id}/sticker`} data-testid="print-sticker">
              <Printer aria-hidden />
              {t("printSticker")}
            </Link>
          </Button>
          {canReissue ? (
            <Button size="sm" variant="outline" onClick={onReissue} data-testid="reissue-sticker">
              <RefreshCw aria-hidden />
              {t("reissueSticker")}
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function InspectionDialog({ avp, onSaved, onClose }: { avp: Avp; onSaved: (a: Avp) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("vehicles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [on, setOn] = useState(avp.inspection_date ?? todayInZone());
  const [inspector, setInspector] = useState(avp.inspector ?? "");
  const [result, setResult] = useState<Schemas["InspectionResult"] | "">(avp.inspection_result ?? "");
  const [areas, setAreas] = useState<Schemas["AreaCategory"][]>(avp.areas);
  const [list, setList] = useState<Partial<Record<Item, Outcome>>>(avp.checklist as Partial<Record<Item, Outcome>>);
  return (
    <StepDialog
      title={t("recordInspection")}
      description={t("inspectionHint")}
      confirmLabel={tc("save")}
      testId="save-inspection"
      wide
      onConfirm={async () => {
        const u = await unwrap(
          api.PATCH("/api/v1/avps/{avp_id}", { params: { path: { avp_id: avp.id } }, body: { areas, inspection_date: on || null, inspector: inspector.trim() || null, inspection_result: result || null, checklist: list } }),
        );
        await onSaved(u);
        toast.success(tc("saved"));
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField id="in-date" label={t("fields.inspection_date")}>
          <Input type="date" max={todayInZone()} value={on} onChange={(e) => setOn(e.target.value)} />
        </FormField>
        <FormField id="in-inspector" label={t("fields.inspector")}>
          <Input maxLength={120} value={inspector} onChange={(e) => setInspector(e.target.value)} />
        </FormField>
        <FormField id="in-result" label={t("fields.inspection_result")}>
          <Select value={result} onChange={(e) => setResult(e.target.value as Schemas["InspectionResult"] | "")}>
            <option value="">{tc("select")}</option>
            {(["passed", "failed"] as const).map((x) => (
              <option key={x} value={x}>
                {te(`inspectionResult.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      <MultiSelect id="in-areas" label={t("fields.areas")} options={AREA_CATEGORIES.map((x) => ({ value: x, label: te(`areaCategory.${x}`) }))} value={areas} onChange={(v) => setAreas(v as Schemas["AreaCategory"][])} className="lg:w-full" />
      <fieldset className="grid gap-2 sm:grid-cols-2" data-testid="checklist-editor">
        <legend className="mb-1 text-sm font-medium">{t("checklist")}</legend>
        {AVP_CHECKLIST_ITEMS.map((i) => (
          <label key={i} className="flex items-center justify-between gap-2 rounded border px-2 py-1 text-sm">
            <span>{te(`checklistItem.${i}`)}</span>
            <Select aria-label={te(`checklistItem.${i}`)} className="w-28" value={list[i] ?? ""} onChange={(e) => setList((l) => ({ ...l, [i]: (e.target.value || undefined) as Outcome | undefined }))} data-testid={`check-${i}`}>
              <option value="">—</option>
              {CHECKLIST_OUTCOMES.filter((o) => o !== "n.a." || !AVP_NO_NA.includes(i)).map((o) => (
                <option key={o} value={o}>
                  {te(`checklistOutcome.${o === "n.a." ? "na" : o}`)}
                </option>
              ))}
            </Select>
          </label>
        ))}
      </fieldset>
    </StepDialog>
  );
}

function IssueAvpDialog({ avp, onSaved, onClose }: { avp: Avp; onSaved: (a: Avp) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("vehicles");
  const [no, setNo] = useState("");
  const [sticker, setSticker] = useState("");
  const [issued, setIssued] = useState(todayInZone());
  const [until, setUntil] = useState("");
  return (
    <StepDialog
      title={t("issueAvp")}
      description={t("issueHint")}
      confirmLabel={t("issueAvp")}
      testId="issue-avp-confirm"
      disabled={!no.trim() || !sticker.trim() || !until}
      onConfirm={async () => {
        const u = await unwrap(api.POST("/api/v1/avps/{avp_id}/issue", { params: { path: { avp_id: avp.id } }, body: { avp_no: no.trim(), sticker_no: sticker.trim(), issued_on: issued, own_valid_until: until } }));
        await onSaved(u);
        toast.success(t("issued", { no: u.avp_no ?? "" }));
      }}
      onClose={onClose}
    >
      <FormField id="ia-avp-no" label={t("fields.avp_no")} required>
        <Input className="ltr" maxLength={30} value={no} onChange={(e) => setNo(e.target.value)} />
      </FormField>
      <FormField id="ia-sticker" label={t("fields.sticker_no")} required>
        <Input className="ltr" maxLength={20} value={sticker} onChange={(e) => setSticker(e.target.value)} />
      </FormField>
      <FormField id="ia-avp-on" label={t("fields.issued_on")} required>
        <Input type="date" value={issued} onChange={(e) => setIssued(e.target.value)} />
      </FormField>
      <FormField id="ia-avp-until" label={t("fields.own_valid_until")} required>
        <Input type="date" min={issued} value={until} onChange={(e) => setUntil(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function ReissueStickerDialog({ avp, onClose }: { avp: Avp; onClose: () => void }) {
  const t = useTranslations("vehicles");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("reissueSticker")}
      description={t("reissueHint")}
      confirmLabel={t("reissueSticker")}
      disabled={reason.trim().length < 10}
      onConfirm={async () => {
        const s = await unwrap(api.POST("/api/v1/avps/{avp_id}/sticker/reissue", { params: { path: { avp_id: avp.id } }, body: { reason: reason.trim() } }));
        qc.setQueryData(ak.sticker(avp.id), s);
        await qc.invalidateQueries({ queryKey: ak.avp(avp.id) });
        toast.success(t("stickerReissued"));
      }}
      onClose={onClose}
    >
      <FormField id="rs-reason" label={tc("reason")} required hint={t("min10")}>
        <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

/** Printable AVP sticker (QR + printed ref, no personal data). */
export function AvpStickerPrint({ id }: { id: string }) {
  const t = useTranslations("vehicles");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const locale = useLocale();
  const a = useAvp(id);
  const q = useAvpSticker(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data || !a.data) return <LoadingState />;
  const s = q.data;
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex gap-2 print:hidden">
        <Button onClick={() => window.print()} data-testid="do-print">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={`/avps/${id}`}>{tc("back")}</Link>
        </Button>
      </div>
      <div className="flex w-[90mm] flex-col items-center gap-2 rounded-xl border-4 border-black bg-white p-4 text-black" data-testid="sticker-print" lang={locale}>
        <p className="text-lg font-bold">{t("stickerTitle")}</p>
        <QrImage payload={s.qr_payload} size={220} label={t("stickerQr", { no: s.sticker_no })} />
        <p className="ltr font-mono text-xl font-bold tracking-wider">{s.printed_ref}</p>
        <div className="ltr grid w-full grid-cols-2 gap-1 text-sm">
          <span>AVP</span>
          <span className="font-semibold">{s.avp_no}</span>
          <span>{t("fields.sticker_no")}</span>
          <span className="font-semibold">{s.sticker_no}</span>
          <span>{t("fields.vehicle_no")}</span>
          <span className="font-semibold">{s.vehicle_no}</span>
          <span>{t("fields.fleet_no")}</span>
          <span className="font-semibold">{s.fleet_no}</span>
        </div>
        <p className="text-sm">{a.data.areas.map((x) => te(`areaCategory.${x}`)).join(" · ")}</p>
      </div>
    </div>
  );
}
