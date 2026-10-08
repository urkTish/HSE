"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Pencil, Plus, Trash2 } from "lucide-react";
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
import { ApiWarnings } from "@/components/common/api-warnings";
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
import { Code } from "@/components/access/common";
import { DecimalInput } from "@/components/ptw/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import {
  ck,
  useCertSettings,
  useConfigurationEvents,
  useEquipmentCertificate,
  useEquipmentCertificates,
  useEquipmentCertVerifications,
  useEquipmentDeployments,
  useVerificationLog,
} from "@/lib/api/cert";
import {
  CERT_INSPECTION_TYPES,
  CERT_KINDS,
  CERT_SOURCES,
  CERTIFICATE_STATUSES,
  DEFECT_CATEGORIES,
  EQUIPMENT_CERT_CATEGORIES,
  LIFTING_GEAR_COLOURS,
  LIMITATION_CODES,
  LINE_RESULTS,
  VERIFICATION_OUTCOMES,
  VERIFICATION_STATUSES,
} from "@/lib/cert-enums";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import {
  CertStatusBadge,
  CertTransitionButtons,
  CertValidityView,
  DefectCategoryBadge,
  EquipmentLabel,
  EquipmentLimitations,
  EquipmentSubNav,
  LineResultBadge,
  Tick,
  TpiLabel,
  TpiSelect,
  UploadField,
  UserName,
  VerificationBadge,
  VerificationsCard,
} from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

/* ───────────── list ───────────── */

export function EqCertListPage() {
  return <ProjectGate>{(p) => <EqCertList project={p} />}</ProjectGate>;
}

function EqCertList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("eqCerts");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const { date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["CertificateStatus"][];
  const verif = s.getAll("verification_status") as S["VerificationStatus"][];
  const cat = s.getAll("category") as S["EquipmentCertCategory"][];
  const q = useEquipmentCertificates(project.id, {
    q: s.get("q") || null,
    status: status.length ? status : null,
    verification_status: verif.length ? verif : null,
    category: cat.length ? cat : null,
    source: (s.get("source") as S["CertSource"]) || null,
    engagement_id: s.get("engagement_id") ? [s.get("engagement_id") as string] : null,
    include_subcontractors: true,
    in_force: s.get("in_force") === "1" ? true : s.get("in_force") === "0" ? false : null,
    expiring_days: s.getInt("expiring", 0) || null,
    verification_overdue: s.get("overdue") === "1" ? true : null,
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
            <Button asChild data-testid="new-eq-cert">
              <Link href="/equipment-certificates/new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <EquipmentSubNav />
      <ListToolbar actions={can(me, "export.cert", project.id) ? <ExportButtons dataset="equipment_certificates" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="ec-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="ec-status" label={tc("status")} options={CERTIFICATE_STATUSES.map((x) => ({ value: x, label: te(`certStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="ec-verif" label={t("verification")} options={VERIFICATION_STATUSES.map((x) => ({ value: x, label: te(`verificationStatus.${x}`) }))} value={verif} onChange={(v) => s.set({ verification_status: v })} />
        <MultiSelect id="ec-cat" label={t("category")} options={EQUIPMENT_CERT_CATEGORIES.map((x) => ({ value: x, label: te(`eqc.${x}`) }))} value={cat} onChange={(v) => s.set({ category: v })} />
        <SelectFilter id="ec-eng" label={tc("contractor")} value={s.get("engagement_id") ?? ""} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter
          id="ec-inforce"
          label={t("inForce")}
          value={s.get("in_force") ?? ""}
          onChange={(v) => s.set({ in_force: v })}
          options={[
            { value: "1", label: tc("yes") },
            { value: "0", label: tc("no") },
          ]}
        />
        <SelectFilter
          id="ec-exp"
          label={t("expiring")}
          value={s.get("expiring") ?? ""}
          onChange={(v) => s.set({ expiring: v })}
          options={[
            { value: "7", label: t("withinDays", { n: 7 }) },
            { value: "30", label: t("withinDays", { n: 30 }) },
          ]}
        />
        <SelectFilter id="ec-overdue" label={t("verificationOverdue")} value={s.get("overdue") ?? ""} onChange={(v) => s.set({ overdue: v })} options={[{ value: "1", label: tc("yes") }]} />
        <SelectFilter id="ec-source" label={t("source")} value={s.get("source") ?? ""} onChange={(v) => s.set({ source: v })} options={CERT_SOURCES.map((x) => ({ value: x, label: te(`certSource.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="eq-certs-table">
            <THead>
              <TR>
                <TH>{t("certNo")}</TH>
                <TH>{t("items")}</TH>
                <TH>{t("inspection")}</TH>
                <TH>{t("validUntil")}</TH>
                <TH>{t("verification")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="eq-cert-row" data-cert-no={c.cert_no}>
                  <TD label={t("certNo")}>
                    <Link href={`/equipment-certificates/${c.id}`} className="font-medium text-primary hover:underline">
                      <Code>{c.cert_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{c.tpi_code}</Code>
                    </span>
                  </TD>
                  <TD label={t("items")}>
                    <span className="text-sm">
                      <bdi className="ltr">{c.equipment_tags.slice(0, 4).join(", ")}</bdi>
                      {c.line_count > 4 ? ` +${c.line_count - 4}` : ""}
                    </span>
                    <span className="block text-xs text-muted-foreground">{c.categories.map((x) => te(`eqc.${x as S["EquipmentCertCategory"]}`)).join(" · ")}</span>
                  </TD>
                  <TD label={t("inspection")}>
                    {te(`certInspectionType.${c.inspection_type}`)}
                    <span className="block text-xs text-muted-foreground">{date(c.inspected_on)}</span>
                  </TD>
                  <TD label={t("validUntil")}>
                    {c.valid_until ? date(c.valid_until) : "—"}
                    {c.limiting_factor ? <span className="block text-xs text-muted-foreground">{te(`certLimitingFactor.${c.limiting_factor}`)}</span> : null}
                    {c.in_force ? <Badge tone="success">{t("inForce")}</Badge> : null}
                  </TD>
                  <TD label={t("verification")}>
                    <VerificationBadge status={c.verification_status} />
                  </TD>
                  <TD label={tc("status")}>
                    <CertStatusBadge status={c.status} />
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

/* ───────────── create / edit form with live preview ───────────── */

type LineState = {
  key: number;
  equipment_id: string;
  serial_as_printed: string;
  result: S["LineResult"];
  swl_t: string;
  configuration_ref: string;
  load_performed: boolean;
  load_pct: string;
  load_weight: string;
  structural_repair: boolean;
  lifting_duty_certified: boolean;
  colour_code: S["LiftingGearColour"] | "";
  limitations: { code: S["LimitationCode"]; value: string; text: string }[];
  defects: { category: S["DefectCategory"]; description_en: string; tpi_due_date: string }[];
};

let lineKey = 1;
const newLine = (): LineState => ({
  key: lineKey++,
  equipment_id: "",
  serial_as_printed: "",
  result: "pass",
  swl_t: "",
  configuration_ref: "",
  load_performed: false,
  load_pct: "",
  load_weight: "",
  structural_repair: false,
  lifting_duty_certified: false,
  colour_code: "",
  limitations: [],
  defects: [],
});

function lineFromRead(l: S["CertLineRead"]): LineState {
  return {
    key: lineKey++,
    equipment_id: l.equipment.id,
    serial_as_printed: l.serial_as_printed,
    result: l.result,
    swl_t: l.swl_t ?? "",
    configuration_ref: l.configuration_ref ?? "",
    load_performed: l.load_test?.performed ?? false,
    load_pct: l.load_test?.percent_of_swl ?? "",
    load_weight: l.load_test?.test_weight_t ?? "",
    structural_repair: l.structural_repair,
    lifting_duty_certified: l.lifting_duty_certified,
    colour_code: l.colour_code ?? "",
    limitations: l.limitations.map((x) => ({ code: x.code, value: x.value ?? "", text: x.text ?? "" })),
    defects: [],
  };
}

export function EqCertNewPage() {
  return <ProjectGate>{(p) => <EqCertForm project={p} />}</ProjectGate>;
}

function EqCertForm({ project, cert }: { project: S["ProjectRead"]; cert?: S["EquipmentCertificateRead"] }) {
  const t = useTranslations("eqCerts");
  const tErr = useTranslations("errors");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const settings = useCertSettings(project.id);
  const deps = useEquipmentDeployments(project.id, { status: ["planned", "approved", "on_site"], page_size: 200 });
  const [tpi, setTpi] = useState(cert?.tpi.id ?? "");
  const [certNo, setCertNo] = useState(cert?.cert_no ?? "");
  const [type, setType] = useState<S["CertInspectionType"]>(cert?.inspection_type ?? "periodic");
  const [inspected, setInspected] = useState(cert?.inspected_on ?? "");
  const [issued, setIssued] = useState(cert?.issued_on ?? "");
  const [nextDue, setNextDue] = useState(cert?.printed_next_due ?? "");
  const [inspector, setInspector] = useState(cert?.inspector_name ?? "");
  const [staffNo, setStaffNo] = useState(cert?.inspector_staff_no ?? "");
  const [url, setUrl] = useState(cert?.tpi_verification_url ?? "");
  const [configEvent, setConfigEvent] = useState(cert?.configuration_event_id ?? "");
  const [historic, setHistoric] = useState(false);
  const [lines, setLines] = useState<LineState[]>(cert ? cert.lines.map(lineFromRead) : [newLine()]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const colourEnabled = settings.data?.lifting_gear_colour_scheme.enabled ?? false;
  const items = useMemo(() => {
    const m = new Map<string, { id: string; label: string; category: S["EquipmentCertCategory"]; tag: string }>();
    for (const d of deps.data?.items ?? []) m.set(d.equipment.id, { id: d.equipment.id, label: `${d.tag} · ${d.equipment.equipment_no} · ${te(`eqc.${d.equipment.category}`)}`, category: d.equipment.category, tag: d.tag });
    for (const l of cert?.lines ?? []) if (!m.has(l.equipment.id)) m.set(l.equipment.id, { id: l.equipment.id, label: `${l.equipment.equipment_no} · ${te(`eqc.${l.equipment.category}`)}`, category: l.equipment.category, tag: "" });
    return [...m.values()];
  }, [deps.data, cert, te]);
  const firstEquipment = lines[0]?.equipment_id ?? "";
  const configs = useConfigurationEvents(firstEquipment, { enabled: type === "after_configuration_change" && Boolean(firstEquipment) });
  const setLine = (k: number, v: Partial<LineState>) => setLines(lines.map((l) => (l.key === k ? { ...l, ...v } : l)));
  const body: S["EquipmentCertificateCreate"] = {
    tpi_id: tpi,
    cert_no: certNo.trim(),
    inspection_type: type,
    inspected_on: inspected,
    issued_on: issued,
    printed_next_due: nextDue || null,
    inspector_name: inspector.trim(),
    inspector_staff_no: staffNo.trim() || null,
    tpi_verification_url: url.trim() || null,
    configuration_event_id: configEvent || null,
    historic,
    lines: lines.map((l) => ({
      equipment_id: l.equipment_id,
      serial_as_printed: l.serial_as_printed.trim(),
      result: l.result,
      swl_t: l.swl_t || null,
      configuration_ref: l.configuration_ref.trim() || null,
      load_test: l.load_performed ? { performed: true, percent_of_swl: l.load_pct || null, test_weight_t: l.load_weight || null } : null,
      structural_repair: l.structural_repair,
      lifting_duty_certified: l.lifting_duty_certified,
      colour_code: l.colour_code || null,
      limitations: l.limitations.map((x) => ({ code: x.code, value: x.value || null, text: x.text.trim() || null })),
      defects: l.defects.filter((d) => d.description_en.trim()).map((d) => ({ category: d.category, description_en: d.description_en.trim(), tpi_due_date: d.tpi_due_date || null })),
    })),
  };
  const ready = Boolean(tpi && certNo.trim() && inspected && issued && inspector.trim() && lines.length && lines.every((l) => l.equipment_id && l.serial_as_printed.trim()));
  const previewKey = useDebounced(JSON.stringify(body), 600);
  const preview = useQuery({
    queryKey: ["eq-cert-preview", project.id, previewKey],
    queryFn: () => unwrap(api.POST("/api/v1/projects/{project_id}/equipment-certificates/preview", { params: { path: { project_id: project.id } }, body: JSON.parse(previewKey) as S["EquipmentCertificateCreate"] })),
    enabled: ready,
    retry: false,
    placeholderData: keepPreviousData,
  });
  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (cert) {
        const { historic: _h, ...upd } = body;
        void _h;
        const r = await unwrap(api.PATCH("/api/v1/equipment-certificates/{certificate_id}", { params: { path: { certificate_id: cert.id } }, body: upd }));
        qc.setQueryData(ck.eqCert(cert.id), r);
        await qc.invalidateQueries({ queryKey: ["equipment-certificates"] });
        toast.success(tc("saved"));
        router.push(`/equipment-certificates/${cert.id}`);
      } else {
        const r = await unwrap(api.POST("/api/v1/projects/{project_id}/equipment-certificates", { params: { path: { project_id: project.id } }, body }));
        await qc.invalidateQueries({ queryKey: ["equipment-certificates"] });
        toast.success(t("created", { no: r.cert_no }));
        router.push(`/equipment-certificates/${r.id}`);
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const pv = preview.data;
  const codeText = (c: string) => (tErr.has(`code.${c}` as never) ? tErr(`code.${c}` as never) : c);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/equipment-certificates" }, { label: cert ? cert.cert_no : t("new") }]} />
        <PageHeader title={cert ? t("edit") : t("new")} description={t("newHint")} />
      </div>
      <FormSection title={t("certificate")}>
        <TpiSelect id="ec-tpi" label={t("tpi")} value={tpi} onChange={(v) => setTpi(v)} kind="inspection_body" required />
        <FormField id="ec-no" label={t("certNo")} required>
          <Input value={certNo} onChange={(e) => setCertNo(e.target.value)} className="ltr" data-testid="ec-cert-no" />
        </FormField>
        <FormField id="ec-type" label={t("inspectionType")} required>
          <Select value={type} onChange={(e) => setType(e.target.value as S["CertInspectionType"])} data-testid="ec-type">
            {CERT_INSPECTION_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`certInspectionType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ec-inspected" label={t("inspectedOn")} required>
          <Input type="date" className="ltr" value={inspected} onChange={(e) => setInspected(e.target.value)} data-testid="ec-inspected" />
        </FormField>
        <FormField id="ec-issued" label={t("issuedOn")} required>
          <Input type="date" className="ltr" value={issued} onChange={(e) => setIssued(e.target.value)} data-testid="ec-issued" />
        </FormField>
        <FormField id="ec-next" label={t("printedNextDue")} hint={t("printedNextDueHint")}>
          <Input type="date" className="ltr" value={nextDue} onChange={(e) => setNextDue(e.target.value)} data-testid="ec-next-due" />
        </FormField>
        <FormField id="ec-inspector" label={t("inspector")} required>
          <Input value={inspector} onChange={(e) => setInspector(e.target.value)} data-testid="ec-inspector" />
        </FormField>
        <FormField id="ec-staff" label={t("inspectorStaffNo")}>
          <Input value={staffNo} onChange={(e) => setStaffNo(e.target.value)} className="ltr" />
        </FormField>
        <FormField id="ec-url" label={t("verificationUrl")} hint={t("verificationUrlHint")}>
          <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} className="ltr" />
        </FormField>
        {type === "after_configuration_change" ? (
          <FormField id="ec-config" label={t("configEvent")} required>
            <Select value={configEvent} onChange={(e) => setConfigEvent(e.target.value)} data-testid="ec-config">
              <option value="">{tc("select")}</option>
              {(configs.data?.items ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {te(`configEventType.${c.event_type}`)} · {c.occurred_at.slice(0, 16).replace("T", " ")} · {c.new_configuration}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        {!cert ? <Tick id="ec-historic" label={t("historic")} checked={historic} onChange={setHistoric} /> : null}
      </FormSection>
      {lines.map((l, idx) => {
        const lp = pv?.lines.find((x) => x.equipment_id === l.equipment_id);
        return (
          <FormSection key={l.key} title={t("lineN", { n: idx + 1 })}>
            <FormField id={`ln-eq-${l.key}`} label={t("item")} required>
              <Select value={l.equipment_id} onChange={(e) => setLine(l.key, { equipment_id: e.target.value })} data-testid={`ln-equipment-${idx}`}>
                <option value="">{tc("select")}</option>
                {items.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.label}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id={`ln-serial-${l.key}`} label={t("serialAsPrinted")} required hint={t("serialHint")}>
              <Input value={l.serial_as_printed} onChange={(e) => setLine(l.key, { serial_as_printed: e.target.value })} className="ltr" data-testid={`ln-serial-${idx}`} />
            </FormField>
            <FormField id={`ln-result-${l.key}`} label={t("result")} required>
              <Select value={l.result} onChange={(e) => setLine(l.key, { result: e.target.value as S["LineResult"] })} data-testid={`ln-result-${idx}`}>
                {LINE_RESULTS.map((x) => (
                  <option key={x} value={x}>
                    {te(`lineResult.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id={`ln-swl-${l.key}`} label={t("swl")}>
              <DecimalInput id={`ln-swl-${l.key}`} value={l.swl_t} onChange={(v) => setLine(l.key, { swl_t: v })} data-testid={`ln-swl-${idx}`} />
            </FormField>
            <FormField id={`ln-config-${l.key}`} label={t("configurationRef")}>
              <Input value={l.configuration_ref} onChange={(e) => setLine(l.key, { configuration_ref: e.target.value })} />
            </FormField>
            {colourEnabled ? (
              <FormField id={`ln-colour-${l.key}`} label={t("colourCode")}>
                <Select value={l.colour_code} onChange={(e) => setLine(l.key, { colour_code: e.target.value as S["LiftingGearColour"] })}>
                  <option value="">—</option>
                  {LIFTING_GEAR_COLOURS.map((x) => (
                    <option key={x} value={x}>
                      {te(`liftingGearColour.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
            ) : null}
            <div className="flex flex-col gap-1 sm:col-span-2">
              <Tick id={`ln-load-${l.key}`} label={t("loadTest")} checked={l.load_performed} onChange={(v) => setLine(l.key, { load_performed: v })} />
              {l.load_performed ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <FormField id={`ln-pct-${l.key}`} label={t("loadPct")}>
                    <DecimalInput id={`ln-pct-${l.key}`} value={l.load_pct} onChange={(v) => setLine(l.key, { load_pct: v })} data-testid={`ln-load-pct-${idx}`} />
                  </FormField>
                  <FormField id={`ln-weight-${l.key}`} label={t("loadWeight")}>
                    <DecimalInput id={`ln-weight-${l.key}`} value={l.load_weight} onChange={(v) => setLine(l.key, { load_weight: v })} />
                  </FormField>
                </div>
              ) : null}
              <Tick id={`ln-struct-${l.key}`} label={t("structuralRepair")} checked={l.structural_repair} onChange={(v) => setLine(l.key, { structural_repair: v })} />
              <Tick id={`ln-duty-${l.key}`} label={t("liftingDutyCertified")} checked={l.lifting_duty_certified} onChange={(v) => setLine(l.key, { lifting_duty_certified: v })} />
            </div>
            <LimitationsEditor value={l.limitations} onChange={(v) => setLine(l.key, { limitations: v })} />
            {l.result !== "pass" && !cert ? <LineDefectsEditor value={l.defects} onChange={(v) => setLine(l.key, { defects: v })} /> : null}
            {lp ? (
              <div className="rounded-md border p-3 sm:col-span-2" data-testid={`ln-preview-${idx}`}>
                <p className="mb-1 text-xs font-semibold text-muted-foreground">{t("previewLine")}</p>
                <CertValidityView v={lp.validity} projectId={project.id} />
                <PreviewIssues errors={lp.errors} warnings={lp.warnings} />
              </div>
            ) : null}
            {lines.length > 1 ? (
              <Button variant="ghost" className="self-start" onClick={() => setLines(lines.filter((x) => x.key !== l.key))}>
                <Trash2 aria-hidden />
                {t("removeLine")}
              </Button>
            ) : null}
          </FormSection>
        );
      })}
      <Button variant="outline" className="self-start" onClick={() => setLines([...lines, newLine()])} data-testid="add-line">
        <Plus aria-hidden />
        {t("addLine")}
      </Button>
      <Card data-testid="eq-cert-preview">
        <CardHeader>
          <CardTitle className="text-base">{t("preview")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {!ready ? (
            <p className="text-muted-foreground">{t("previewNeeds")}</p>
          ) : preview.isError ? (
            <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
          ) : pv ? (
            <>
              <span className="flex flex-wrap items-center gap-2" data-testid="preview-tpi" data-acceptable={pv.tpi_acceptable ? "yes" : "no"}>
                {pv.tpi_acceptable ? <Badge tone="success">{t("tpiAcceptable")}</Badge> : <Badge tone="danger">{t("tpiNotAcceptable")}</Badge>}
                {pv.tpi_reason ? <span className="text-xs text-destructive">{codeText(pv.tpi_reason)}</span> : null}
              </span>
              {/* The scan is uploaded on the saved Draft, so SCAN_REQUIRED is a reminder here, not an error. */}
              <PreviewIssues errors={pv.errors.filter((e) => e.code !== "SCAN_REQUIRED")} warnings={pv.warnings} />
              {pv.errors.some((e) => e.code === "SCAN_REQUIRED") ? <p className="text-xs text-muted-foreground">{t("scanAfterSave")}</p> : null}
              {!pv.errors.some((e) => e.code !== "SCAN_REQUIRED") && !pv.warnings.length && pv.tpi_acceptable ? <p className="text-success">{t("previewClean")}</p> : null}
            </>
          ) : (
            <LoadingState rows={1} />
          )}
        </CardContent>
      </Card>
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void save()} disabled={!ready || busy} data-testid="save-eq-cert">
          {busy ? tc("saving") : cert ? tc("save") : t("saveDraft")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={cert ? `/equipment-certificates/${cert.id}` : "/equipment-certificates"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </div>
  );
}

function PreviewIssues({ errors, warnings }: { errors: S["ApiWarning"][]; warnings: S["ApiWarning"][] }) {
  const locale = useLocale();
  const msg = (w: S["ApiWarning"]) => (locale === "ar" && w.message_ar ? w.message_ar : w.message);
  if (!errors.length && !warnings.length) return null;
  return (
    <ul className="mt-1 flex flex-col gap-1 text-sm" data-testid="preview-issues">
      {errors.map((w, i) => (
        <li key={`e${i}`} className="flex gap-2 text-destructive" data-code={w.code} data-kind="error">
          <Badge tone="danger">{w.code}</Badge>
          <span>{msg(w)}</span>
        </li>
      ))}
      {warnings.map((w, i) => (
        <li key={`w${i}`} className="flex gap-2" data-code={w.code} data-kind="warning">
          <Badge tone="warning">{w.code}</Badge>
          <span>{msg(w)}</span>
        </li>
      ))}
    </ul>
  );
}

function LimitationsEditor({ value, onChange }: { value: LineState["limitations"]; onChange: (v: LineState["limitations"]) => void }) {
  const t = useTranslations("eqCerts");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  return (
    <fieldset className="flex flex-col gap-2 sm:col-span-2">
      <legend className="mb-1 text-sm font-medium">{t("limitations")}</legend>
      {value.map((l, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-[14rem_8rem_1fr_auto]">
          <Select aria-label={t("limitations")} value={l.code} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, code: e.target.value as S["LimitationCode"] } : x)))}>
            {LIMITATION_CODES.map((c) => (
              <option key={c} value={c}>
                {te(`limitationCode.${c}`)}
              </option>
            ))}
          </Select>
          <Input aria-label={t("limitationValue")} placeholder={t("limitationValue")} value={l.value} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} className="ltr" />
          <Input aria-label={t("limitationText")} placeholder={t("limitationText")} value={l.text} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} />
          <Button variant="ghost" onClick={() => onChange(value.filter((_, j) => j !== i))}>
            <Trash2 aria-hidden />
            <span className="sr-only">{tc("remove")}</span>
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" className="self-start" onClick={() => onChange([...value, { code: "derated_swl", value: "", text: "" }])}>
        <Plus aria-hidden />
        {t("addLimitation")}
      </Button>
    </fieldset>
  );
}

function LineDefectsEditor({ value, onChange }: { value: LineState["defects"]; onChange: (v: LineState["defects"]) => void }) {
  const t = useTranslations("eqCerts");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  return (
    <fieldset className="flex flex-col gap-2 sm:col-span-2">
      <legend className="mb-1 text-sm font-medium">{t("lineDefects")}</legend>
      <p className="text-xs text-muted-foreground">{t("lineDefectsHint")}</p>
      {value.map((d, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-[8rem_1fr_10rem_auto]">
          <Select aria-label={t("defectCategory")} value={d.category} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, category: e.target.value as S["DefectCategory"] } : x)))}>
            {DEFECT_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {te(`defectCategory.${c}`)}
              </option>
            ))}
          </Select>
          <Input aria-label={t("defectDescription")} placeholder={t("defectDescription")} value={d.description_en} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, description_en: e.target.value } : x)))} />
          <Input aria-label={t("tpiDueDate")} type="date" className="ltr" value={d.tpi_due_date} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, tpi_due_date: e.target.value } : x)))} />
          <Button variant="ghost" onClick={() => onChange(value.filter((_, j) => j !== i))}>
            <Trash2 aria-hidden />
            <span className="sr-only">{tc("remove")}</span>
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" className="self-start" onClick={() => onChange([...value, { category: "B", description_en: "", tpi_due_date: "" }])}>
        <Plus aria-hidden />
        {t("addDefect")}
      </Button>
    </fieldset>
  );
}

/* ───────────── detail ───────────── */

export function EqCertDetail({ id }: { id: string }) {
  const q = useEquipmentCertificate(id);
  const s = useSearchState();
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => (s.get("edit") === "1" ? <EqCertForm project={p} cert={q.data} /> : <EqCertView project={p} c={q.data} />)}</ProjectById>;
}

function EqCertView({ project, c }: { project: S["ProjectRead"]; c: S["EquipmentCertificateRead"] }) {
  const t = useTranslations("eqCerts");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const msg = useErrorMessage();
  const s = useSearchState();
  const { date, dateTime } = useFormatters(project.id);
  const verifs = useEquipmentCertVerifications(c.id);
  const edit = canWrite(me, "equipment.edit", project.id);
  const verify = canWrite(me, "cert.verify", project.id);
  const configMismatch = c.warnings.some((w) => w.code === "CONFIGURATION_MISMATCH");
  async function setScan(id: string | null) {
    const r = await unwrap(api.PATCH("/api/v1/equipment-certificates/{certificate_id}", { params: { path: { certificate_id: c.id } }, body: { scan_attachment_id: id } }));
    qc.setQueryData(ck.eqCert(c.id), r);
  }
  async function openScan() {
    if (!c.scan_attachment_id) return;
    try {
      const u = await unwrap(api.POST("/api/v1/attachments/{attachment_id}/signed-url", { params: { path: { attachment_id: c.scan_attachment_id } } }));
      window.open(u.url, "_blank", "noopener");
    } catch (e) {
      toast.error(msg(e));
    }
  }
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/equipment-certificates" }, { label: c.cert_no }]} />
        <PageHeader
          title={c.cert_no}
          description={`${c.tpi.tpi_code} · ${te(`certInspectionType.${c.inspection_type}`)} · ${date(c.inspected_on)}`}
          actions={
            <>
              <CertStatusBadge status={c.status} />
              <VerificationBadge status={c.verification_status} />
              {edit && c.status === "draft" ? (
                <Button variant="outline" onClick={() => s.set({ edit: "1" })} data-testid="edit-eq-cert">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              <CertTransitionButtons kind="equipment" id={c.id} actions={c.allowed_actions} needsConfigTick={configMismatch} />
            </>
          }
        />
      </div>
      {c.status === "draft" && !c.scan_attachment_id ? <Alert tone="info">{t("scanNeeded")}</Alert> : null}
      <ApiWarnings warnings={c.warnings} />
      {c.status_reason ? (
        <Alert tone={c.status === "suspended" || c.status === "revoked" || c.status === "rejected" ? "danger" : "info"}>
          {te(`certStatusReason.${c.status_reason}`)}
          {c.status_reason_text ? ` — ${c.status_reason_text}` : ""}
        </Alert>
      ) : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("tpi")} wide>
              <TpiLabel tpi={c.tpi} />
              {!c.tpi.accepted_for_use ? <Badge tone="danger">{t("tpiNotAcceptable")}</Badge> : null}
            </FieldItem>
            <FieldItem label={t("issuedOn")}>{date(c.issued_on)}</FieldItem>
            <FieldItem label={t("printedNextDue")}>{c.printed_next_due ? date(c.printed_next_due) : "—"}</FieldItem>
            <FieldItem label={t("validUntil")}>{c.valid_until ? date(c.valid_until) : "—"}</FieldItem>
            <FieldItem label={t("inForceFrom")}>{c.in_force_from ? dateTime(c.in_force_from) : "—"}</FieldItem>
            <FieldItem label={t("inspector")}>
              {c.inspector_name ?? "—"}
              {c.inspector_staff_no ? <Code className="ms-1 text-muted-foreground">{c.inspector_staff_no}</Code> : null}
            </FieldItem>
            <FieldItem label={t("source")}>{te(`certSource.${c.source}`)}</FieldItem>
            <FieldItem label={t("submitted")}>
              {c.submitted_by ? (
                <>
                  <UserName u={c.submitted_by} /> · {c.submitted_at ? dateTime(c.submitted_at) : ""}
                </>
              ) : (
                "—"
              )}
            </FieldItem>
            <FieldItem label={t("reviewed")}>
              {c.reviewed_by ? (
                <>
                  <UserName u={c.reviewed_by} /> · {c.reviewed_at ? dateTime(c.reviewed_at) : ""}
                </>
              ) : (
                "—"
              )}
            </FieldItem>
            <FieldItem label={t("verificationDue")}>{c.verification_due_on ? date(c.verification_due_on) : "—"}</FieldItem>
            <FieldItem label={t("verificationUrl")} wide>
              {c.tpi_verification_url ? (
                <span className="ltr inline-flex items-center gap-1 text-sm break-all">
                  {c.tpi_verification_url}
                  <ExternalLink aria-hidden className="size-3.5" />
                </span>
              ) : (
                "—"
              )}
            </FieldItem>
            <FieldItem label={t("scan")} wide>
              <span className="flex flex-wrap items-center gap-2">
                {c.scan_attachment_id ? (
                  <Button size="sm" variant="outline" onClick={() => void openScan()} data-testid="open-scan">
                    <FileText aria-hidden />
                    {t("openScan")}
                  </Button>
                ) : (
                  <span className="text-sm text-muted-foreground">{t("noScan")}</span>
                )}
              </span>
              {edit && c.status === "draft" ? (
                <div className="mt-2 max-w-md">
                  <UploadField id="ec-scan" label={t("uploadScan")} ownerType="equipment_certificate_scan" ownerId={c.id} accept="application/pdf,image/*" value={c.scan_attachment_id} onChange={(v) => void setScan(v)} hint={t("scanHint")} />
                </div>
              ) : null}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("lines", { n: c.lines.length })}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col divide-y" data-testid="cert-lines">
            {c.lines.map((l) => (
              <li key={l.id} className="grid gap-3 py-3 sm:grid-cols-[1.2fr_1fr]" data-testid="cert-line" data-equipment={l.equipment.equipment_no}>
                <div className="flex flex-col gap-1 text-sm">
                  <EquipmentLabel e={l.equipment} />
                  <span className="text-xs text-muted-foreground">
                    {t("serialAsPrinted")}: <Code>{l.serial_as_printed}</Code>
                  </span>
                  <span className="flex flex-wrap items-center gap-2">
                    <LineResultBadge result={l.result} />
                    {l.swl_t ? <span className="text-xs">{t("swlValue", { swl: l.swl_t })}</span> : null}
                    {l.load_test?.performed ? <span className="text-xs">{t("loadTested", { pct: l.load_test.percent_of_swl ?? "—" })}</span> : null}
                    {l.colour_code ? <span className="text-xs">{te(`liftingGearColour.${l.colour_code}`)}</span> : null}
                    {l.lifting_duty_certified ? <Badge tone="info">{t("liftingDutyCertified")}</Badge> : null}
                    {l.suspended_for_configuration ? <Badge tone="danger">{t("suspendedConfig")}</Badge> : null}
                    {l.superseded_by_line_id ? <Badge tone="neutral">{te("certStatus.superseded")}</Badge> : null}
                  </span>
                  <EquipmentLimitations items={l.limitations} />
                  {l.defects.length ? (
                    <span className="flex flex-wrap gap-2">
                      {l.defects.map((d) => (
                        <Link key={d.id} href={`/defects/${d.id}`} className="inline-flex items-center gap-1 text-primary hover:underline">
                          <Code>{d.defect_no}</Code>
                          <DefectCategoryBadge category={d.category} />
                        </Link>
                      ))}
                    </span>
                  ) : null}
                </div>
                <CertValidityView v={l.validity} projectId={project.id} />
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <VerificationsCard kind="equipment" id={c.id} projectId={project.id} tpi={c.tpi} canRecord={verify && (c.status === "submitted" || c.status === "accepted")} query={verifs} />
      <HistoryPanel entityType="equipment_certificate" entityId={c.id} />
    </div>
  );
}

/* ───────────── verification log ───────────── */

export function VerificationLogPage() {
  return <ProjectGate>{(p) => <VerificationLog project={p} />}</ProjectGate>;
}

function VerificationLog({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("eqCerts");
  const tv = useTranslations("cert");
  const te = useTranslations("enums");
  const me = useMeData();
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const outcome = s.getAll("outcome") as S["VerificationOutcome"][];
  const q = useVerificationLog(project.id, {
    cert_kind: (s.get("kind") as S["CertKind"]) || null,
    outcome: outcome.length ? outcome : null,
    date_from: s.get("from") || null,
    date_to: s.get("to") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("logTitle")} description={t("logSubtitle")} />
      <EquipmentSubNav />
      <ListToolbar actions={can(me, "export.cert", project.id) ? <ExportButtons dataset="cert_verifications" params={{ project_id: project.id }} /> : null}>
        <SelectFilter id="vl-kind" label={t("certKind")} value={s.get("kind") ?? ""} onChange={(v) => s.set({ kind: v })} options={CERT_KINDS.map((x) => ({ value: x, label: te(`certKind.${x}`) }))} />
        <MultiSelect id="vl-outcome" label={tv("outcome")} options={VERIFICATION_OUTCOMES.map((x) => ({ value: x, label: te(`verificationOutcome.${x}`) }))} value={outcome} onChange={(v) => s.set({ outcome: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="verification-log">
            <THead>
              <TR>
                <TH>{tv("performedAt")}</TH>
                <TH>{t("certNo")}</TH>
                <TH>{t("subject")}</TH>
                <TH>{tv("method")}</TH>
                <TH>{tv("outcome")}</TH>
                <TH>{tv("by")}</TH>
                <TH>{tv("verificationStatus")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((v) => (
                <TR key={v.id} data-testid="verification-log-row">
                  <TD label={tv("performedAt")}>{dateTime(v.performed_at)}</TD>
                  <TD label={t("certNo")}>
                    <Link href={v.cert_kind === "equipment" ? `/equipment-certificates/${v.cert_id}` : `/personnel-certificates/${v.cert_id}`} className="text-primary hover:underline">
                      <Code>{v.cert_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">{te(`certKind.${v.cert_kind}`)}</span>
                  </TD>
                  <TD label={t("subject")}>
                    <Code>{v.holder_or_item_ref}</Code>
                  </TD>
                  <TD label={tv("method")}>{te(`certVerificationMethod.${v.method}`)}</TD>
                  <TD label={tv("outcome")}>{v.outcome ? te(`verificationOutcome.${v.outcome}`) : "—"}</TD>
                  <TD label={tv("by")}>
                    <UserName u={v.performed_by} />
                  </TD>
                  <TD label={tv("verificationStatus")}>
                    <VerificationBadge status={v.verification_status_after} />
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
