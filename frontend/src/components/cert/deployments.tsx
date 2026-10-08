"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Plus, Printer, QrCode, RefreshCw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
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
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { AccessPrintHeader, BiLabel, Code, QrImage, StepDialog } from "@/components/access/common";
import { DateTimeInput } from "@/components/ptw/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { ck, useCertRefresh, useEquipmentDeployment, useEquipmentDeployments, useEquipmentList, useEquipmentSticker } from "@/lib/api/cert";
import { ARRIVAL_CHECKLIST_ITEMS, DEFECT_CATEGORIES, EQUIPMENT_CERT_CATEGORIES, EQUIPMENT_DEPLOYMENT_STATUSES, SERVICE_STATUSES } from "@/lib/cert-enums";
import { todayInZone } from "@/lib/datetime";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { useDebounced } from "@/lib/use-debounced";
import { EquipmentLabel, EquipmentSubNav, ServiceStatusBadge, UserName } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

export function DeploymentStatusBadge({ status }: { status: S["EquipmentDeploymentStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="deployment-status" data-status={status}>
      <StatusBadge status={status} label={te(`eqDeploymentStatus.${status}`)} />
    </span>
  );
}

/* ───────────── list ───────────── */

export function DeploymentListPage() {
  return <ProjectGate>{(p) => <DeploymentList project={p} />}</ProjectGate>;
}

function DeploymentList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("eqDeployments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["EquipmentDeploymentStatus"][];
  const cat = s.getAll("category") as S["EquipmentCertCategory"][];
  const svc = s.getAll("service_status") as S["ServiceStatus"][];
  const [create, setCreate] = useState(false);
  const q = useEquipmentDeployments(project.id, {
    q: s.get("q") || null,
    status: status.length ? status : null,
    category: cat.length ? cat : null,
    service_status: svc.length ? svc : null,
    engagement_id: s.get("engagement_id") ? [s.get("engagement_id") as string] : null,
    include_subcontractors: true,
    site_id: s.get("site_id") || null,
    arrival_inspection_due: s.get("arrival") === "1" ? true : null,
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
            <Button onClick={() => setCreate(true)} data-testid="new-eq-deployment">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EquipmentSubNav />
      <ListToolbar actions={can(me, "export.cert", project.id) ? <ExportButtons dataset="equipment_deployments" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="ed-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="ed-status" label={tc("status")} options={EQUIPMENT_DEPLOYMENT_STATUSES.map((x) => ({ value: x, label: te(`eqDeploymentStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="ed-svc" label={t("serviceStatus")} options={SERVICE_STATUSES.map((x) => ({ value: x, label: te(`serviceStatus.${x}`) }))} value={svc} onChange={(v) => s.set({ service_status: v })} />
        <MultiSelect id="ed-cat" label={t("category")} options={EQUIPMENT_CERT_CATEGORIES.map((x) => ({ value: x, label: te(`eqc.${x}`) }))} value={cat} onChange={(v) => s.set({ category: v })} />
        <SelectFilter id="ed-eng" label={tc("contractor")} value={s.get("engagement_id") ?? ""} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter id="ed-site" label={tc("site")} value={s.get("site_id") ?? ""} onChange={(v) => s.set({ site_id: v })} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter id="ed-arrival" label={t("arrivalInspection")} value={s.get("arrival") ?? ""} onChange={(v) => s.set({ arrival: v })} options={[{ value: "1", label: t("arrivalDue") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="eq-deployments-table">
            <THead>
              <TR>
                <TH>{t("tag")}</TH>
                <TH>{t("equipment")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("serviceStatus")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((d) => (
                <TR key={d.id} data-testid="eq-deployment-row" data-tag={d.tag}>
                  <TD label={t("tag")}>
                    <Link href={`/equipment-deployments/${d.id}`} className="font-medium text-primary hover:underline">
                      <Code>{d.tag}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{d.deployment_no}</Code>
                    </span>
                  </TD>
                  <TD label={t("equipment")}>
                    <EquipmentLabel e={d.equipment} />
                  </TD>
                  <TD label={tc("contractor")}>
                    <Code>{d.engagement.short_code}</Code>
                  </TD>
                  <TD label={t("serviceStatus")}>
                    <ServiceStatusBadge status={d.equipment.service_status} />
                    {!d.usable && d.not_usable_reason ? <span className="block text-xs text-destructive">{d.not_usable_reason}</span> : null}
                    {d.status === "on_site" && !d.arrival_inspection ? (
                      <Badge tone="warning" className="mt-1" data-testid="arrival-due">
                        {t("arrivalDue")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={tc("status")}>
                    <DeploymentStatusBadge status={d.status} />
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
      {create ? <DeploymentDialog project={project} onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

/** Search the equipment register and pick an item. */
export function EquipmentPicker({ id, value, onChange, label, required, projectId, onlyCategories }: { id: string; value: S["EquipmentListItem"] | null; onChange: (e: S["EquipmentListItem"] | null) => void; label: string; required?: boolean; projectId?: string | null; onlyCategories?: S["EquipmentCertCategory"][] }) {
  const t = useTranslations("eqDeployments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const res = useEquipmentList({ q: dq || null, project_id: projectId ?? null, category: onlyCategories?.length ? onlyCategories : null, page_size: 25 });
  const list = res.data?.items ?? [];
  const items = value && !list.some((x) => x.id === value.id) ? [value, ...list] : list;
  return (
    <FormField id={id} label={label} required={required}>
      <div className="grid gap-2 sm:grid-cols-2">
        <Input type="search" aria-label={t("searchEquipment")} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchEquipment")} autoComplete="off" data-testid={`${id}-search`} />
        <Select value={value?.id ?? ""} onChange={(e) => onChange(items.find((x) => x.id === e.target.value) ?? null)} data-testid={id}>
          <option value="">{tc("select")}</option>
          {items.map((x) => (
            <option key={x.id} value={x.id}>
              {x.equipment_no} · {te(`eqc.${x.category}`)} · {x.manufacturer} {x.model}
              {x.current_tag ? ` · ${x.current_tag}` : ""}
            </option>
          ))}
        </Select>
      </div>
    </FormField>
  );
}

function DeploymentDialog({ project, dep, onClose }: { project: S["ProjectRead"]; dep?: S["EquipmentDeploymentRead"]; onClose: () => void }) {
  const t = useTranslations("eqDeployments");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const opts = useProjectOptions(project.id);
  const [eq, setEq] = useState<S["EquipmentListItem"] | null>(null);
  const [eng, setEng] = useState("");
  const [tag, setTag] = useState(dep?.tag ?? "");
  const [sites, setSites] = useState<string[]>(dep?.sites.map((x) => x.id) ?? []);
  const [zone, setZone] = useState(dep?.zone?.id ?? "");
  const [planned, setPlanned] = useState(dep?.planned_arrival_on ?? todayInZone());
  const valid = tag.trim() && sites.length && planned && (dep || (eq && eng));
  async function save() {
    if (dep) {
      const r = await unwrap(api.PATCH("/api/v1/equipment-deployments/{deployment_id}", { params: { path: { deployment_id: dep.id } }, body: { tag: tag.trim(), site_ids: sites, zone_id: zone || null, planned_arrival_on: planned } }));
      qc.setQueryData(ck.deployment(dep.id), r);
      await qc.invalidateQueries({ queryKey: ["equipment-deployments"] });
      toast.success(tc("saved"));
      return;
    }
    const r = await unwrap(
      api.POST("/api/v1/projects/{project_id}/equipment-deployments", {
        params: { path: { project_id: project.id } },
        body: { equipment_id: (eq as S["EquipmentListItem"]).id, engagement_id: eng, tag: tag.trim(), site_ids: sites, zone_id: zone || null, planned_arrival_on: planned },
      }),
    );
    await qc.invalidateQueries({ queryKey: ["equipment-deployments"] });
    toast.success(t("created", { tag: r.tag }));
    router.push(`/equipment-deployments/${r.id}`);
  }
  return (
    <StepDialog title={dep ? t("edit") : t("new")} description={t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-eq-deployment">
      {!dep ? (
        <>
          <EquipmentPicker id="ed-equipment" label={t("equipment")} value={eq} onChange={setEq} required />
          <FormField id="ed-eng" label={tc("contractor")} required>
            <Select value={eng} onChange={(e) => setEng(e.target.value)} data-testid="ed-engagement">
              <option value="">{tc("select")}</option>
              {opts.engagements.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </Select>
          </FormField>
        </>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ed-tag" label={t("tag")} required hint={t("tagHint")}>
          <Input value={tag} onChange={(e) => setTag(e.target.value)} className="ltr uppercase" maxLength={20} data-testid="ed-tag" />
        </FormField>
        <FormField id="ed-planned" label={t("plannedArrival")} required>
          <Input type="date" className="ltr" value={planned} onChange={(e) => setPlanned(e.target.value)} data-testid="ed-planned" />
        </FormField>
      </div>
      <MultiSelect id="ed-sites" label={tc("site")} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} value={sites} onChange={setSites} testId="ed-sites" />
      <FormField id="ed-zone" label={t("zoneOptional")}>
        <Select value={zone} onChange={(e) => setZone(e.target.value)}>
          <option value="">—</option>
          {opts.zones
            .filter((z) => sites.includes(z.siteId))
            .map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
        </Select>
      </FormField>
    </StepDialog>
  );
}

/* ───────────── detail ───────────── */

export function DeploymentDetail({ id }: { id: string }) {
  const q = useEquipmentDeployment(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => <DeploymentView project={p} d={q.data} />}</ProjectById>;
}

type DStep = "approve" | "arrive" | "demobilise" | "cancel" | "edit" | "arrival" | "reissue" | null;

function DeploymentView({ project, d }: { project: S["ProjectRead"]; d: S["EquipmentDeploymentRead"] }) {
  const t = useTranslations("eqDeployments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const locale = useLocale();
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useCertRefresh();
  const [step, setStep] = useState<DStep>(null);
  const [reason, setReason] = useState("");
  const [at, setAt] = useState("");
  const [demobOn, setDemobOn] = useState(todayInZone());
  const mobilise = canWrite(me, "equipment.mobilise", project.id);
  const edit = canWrite(me, "equipment.edit", project.id);
  async function transition(to: S["EquipmentDeploymentStatus"]) {
    const r = await unwrap(
      api.POST("/api/v1/equipment-deployments/{deployment_id}/transitions", {
        params: { path: { deployment_id: d.id } },
        body: { to_status: to, reason: reason.trim() || null, arrived_at: to === "on_site" ? at || null : null, demobilised_on: to === "demobilised" ? demobOn : null },
      }),
    );
    qc.setQueryData(ck.deployment(d.id), r);
    await refresh();
    toast.success(te(`eqDeploymentStatus.${to}`));
  }
  async function reissue() {
    await unwrap(api.POST("/api/v1/equipment-deployments/{deployment_id}/sticker/reissue", { params: { path: { deployment_id: d.id } }, body: { reason: reason.trim() } }));
    await refresh();
    toast.success(t("reissued"));
  }
  const cfg: Record<"approve" | "arrive" | "demobilise" | "cancel", { to: S["EquipmentDeploymentStatus"]; destructive: boolean; reason: boolean }> = {
    approve: { to: "approved", destructive: false, reason: false },
    arrive: { to: "on_site", destructive: false, reason: false },
    demobilise: { to: "demobilised", destructive: false, reason: false },
    cancel: { to: "cancelled", destructive: true, reason: true },
  };
  const live = d.status === "approved" || d.status === "on_site";
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/equipment-deployments" }, { label: d.tag }]} />
        <PageHeader
          title={`${project.code}-${d.tag}`}
          description={`${d.deployment_no} · ${te(`eqc.${d.equipment.category}`)} · ${d.engagement.short_code}`}
          actions={
            <>
              <DeploymentStatusBadge status={d.status} />
              {edit && (d.status === "planned" || d.status === "approved") ? (
                <Button variant="outline" onClick={() => setStep("edit")} data-testid="edit-eq-deployment">
                  {tc("edit")}
                </Button>
              ) : null}
              {mobilise && d.status === "planned" ? (
                <Button onClick={() => setStep("approve")} data-testid="approve-mobilisation">
                  {t("approve")}
                </Button>
              ) : null}
              {mobilise && d.status === "approved" ? (
                <Button onClick={() => setStep("arrive")} data-testid="record-arrival">
                  {t("recordArrival")}
                </Button>
              ) : null}
              {mobilise && d.status === "on_site" && (!d.arrival_inspection || d.arrival_inspection.result === "fail") ? (
                <Button onClick={() => setStep("arrival")} data-testid="arrival-inspection">
                  <ClipboardCheck aria-hidden />
                  {t("arrivalInspection")}
                </Button>
              ) : null}
              {live && d.has_sticker ? (
                <Button variant="outline" asChild>
                  <Link href={`/equipment-deployments/${d.id}/sticker`} data-testid="print-eq-sticker">
                    <QrCode aria-hidden />
                    {t("sticker")}
                  </Link>
                </Button>
              ) : null}
              {mobilise && live && d.has_sticker ? (
                <Button variant="outline" onClick={() => setStep("reissue")} data-testid="reissue-sticker">
                  <RefreshCw aria-hidden />
                  {t("reissue")}
                </Button>
              ) : null}
              {(mobilise || edit) && d.status === "on_site" ? (
                <Button variant="outline" onClick={() => setStep("demobilise")} data-testid="demobilise-equipment">
                  {t("demobilise")}
                </Button>
              ) : null}
              {mobilise && (d.status === "planned" || d.status === "approved") ? (
                <Button variant="destructive-outline" onClick={() => setStep("cancel")} data-testid="cancel-eq-deployment">
                  {t("cancel")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {live && !d.usable ? (
        <Alert tone="danger" data-testid="not-usable">
          <p className="font-semibold">{t("notUsable")}</p>
          {d.not_usable_reason ? <p className="text-sm">{d.not_usable_reason}</p> : null}
        </Alert>
      ) : null}
      {d.status === "on_site" && !d.arrival_inspection && d.arrival_inspection_due_at ? <Alert tone="warning">{t("arrivalDueBy", { at: dateTime(d.arrival_inspection_due_at) })}</Alert> : null}
      <ApiWarnings warnings={d.warnings} />
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("equipment")} wide>
              <EquipmentLabel e={d.equipment} />
            </FieldItem>
            <FieldItem label={t("serviceStatus")}>
              <ServiceStatusBadge status={d.equipment.service_status} />
            </FieldItem>
            <FieldItem label={tc("contractor")}>
              <Code>{d.engagement.short_code}</Code> {locale === "ar" ? d.engagement.name_ar : d.engagement.name_en}
            </FieldItem>
            <FieldItem label={tc("site")}>{d.sites.map((x) => x.code).join(", ")}</FieldItem>
            <FieldItem label={tc("zone")}>{d.zone?.code ?? "—"}</FieldItem>
            <FieldItem label={t("plannedArrival")}>{date(d.planned_arrival_on)}</FieldItem>
            <FieldItem label={t("approvedBy")}>
              {d.approved_by ? (
                <>
                  <UserName u={d.approved_by} /> · {d.approved_at ? dateTime(d.approved_at) : ""}
                </>
              ) : (
                "—"
              )}
            </FieldItem>
            <FieldItem label={t("arrivedAt")}>{d.arrived_at ? dateTime(d.arrived_at) : "—"}</FieldItem>
            {d.demobilised_on ? <FieldItem label={t("demobilisedOn")}>{date(d.demobilised_on)}</FieldItem> : null}
            <FieldItem label={t("stickerRef")}>{d.sticker_printed_ref ? <Code>{d.sticker_printed_ref}</Code> : "—"}</FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      {d.arrival_inspection ? (
        <Card data-testid="arrival-result" data-result={d.arrival_inspection.result}>
          <CardHeader className="flex flex-row flex-wrap items-center gap-2">
            <CardTitle className="text-base">{t("arrivalInspection")}</CardTitle>
            <StatusBadge status={d.arrival_inspection.result === "pass" ? "line_pass" : "line_fail"} label={te(`passFail.${d.arrival_inspection.result}`)} />
            <span className="text-xs text-muted-foreground">
              {dateTime(d.arrival_inspection.at)} · <UserName u={d.arrival_inspection.by} />
            </span>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-1 text-sm sm:grid-cols-2">
              {d.arrival_inspection.checklist.map((l) => (
                <li key={l.item} className="flex justify-between gap-2 border-b py-1">
                  <span>{locale === "ar" ? l.label_ar : l.label_en}</span>
                  <span className={l.result === "fail" ? "font-medium text-destructive" : "text-muted-foreground"}>{te(`checkResult.${l.result === "n.a." ? "na" : l.result}`)}</span>
                </li>
              ))}
            </ul>
            {d.arrival_inspection.defects.length ? (
              <p className="mt-2 text-sm">
                {t("defectsRaised")}{" "}
                {d.arrival_inspection.defects.map((x) => (
                  <Link key={x.id} href={`/defects/${x.id}`} className="me-2 text-primary hover:underline">
                    <Code>{x.defect_no}</Code>
                  </Link>
                ))}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
      <HistoryPanel entityType="equipment_deployment" entityId={d.id} />
      {step === "edit" ? <DeploymentDialog project={project} dep={d} onClose={() => setStep(null)} /> : null}
      {step === "arrival" ? <ArrivalInspectionDialog d={d} onClose={() => setStep(null)} /> : null}
      {step === "reissue" ? (
        <StepDialog title={t("reissueTitle")} description={t("reissueHint")} confirmLabel={t("reissue")} disabled={reason.trim().length < 5} onClose={() => setStep(null)} onConfirm={reissue} testId="reissue-confirm">
          <FormField id="rs-reason" label={tc("reason")} required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="rs-reason" />
          </FormField>
        </StepDialog>
      ) : null}
      {step && step in cfg ? (
        <StepDialog
          title={t(`${step as keyof typeof cfg}Title`)}
          description={t(`${step as keyof typeof cfg}Hint`)}
          confirmLabel={t(step as keyof typeof cfg)}
          destructive={cfg[step as keyof typeof cfg].destructive}
          disabled={cfg[step as keyof typeof cfg].reason && reason.trim().length < 5}
          onClose={() => {
            setStep(null);
            setReason("");
          }}
          onConfirm={() => transition(cfg[step as keyof typeof cfg].to)}
          testId="eq-deployment-confirm"
        >
          {step === "arrive" ? (
            <FormField id="ar-at" label={t("arrivedAt")} hint={t("nowHint")}>
              <DateTimeInput id="ar-at" value={at} onChange={setAt} />
            </FormField>
          ) : null}
          {step === "demobilise" ? (
            <FormField id="dm-on" label={t("demobilisedOn")} required>
              <Input type="date" className="ltr" value={demobOn} onChange={(e) => setDemobOn(e.target.value)} />
            </FormField>
          ) : null}
          {cfg[step as keyof typeof cfg].reason ? (
            <FormField id="dp-reason" label={tc("reason")} required>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="dp-reason" />
            </FormField>
          ) : null}
        </StepDialog>
      ) : null}
    </div>
  );
}

/** EM-3 arrival inspection: AIC-01…08, each pass / fail / n.a.; a fail can raise a defect A/B/C. */
function ArrivalInspectionDialog({ d, onClose }: { d: S["EquipmentDeploymentRead"]; onClose: () => void }) {
  const t = useTranslations("eqDeployments");
  const te = useTranslations("enums");
  const refresh = useCertRefresh();
  type Line = { result: S["ChecklistItemResult"] | ""; cat: S["DefectCategory"] | ""; desc: string };
  const [lines, setLines] = useState<Record<string, Line>>(Object.fromEntries(ARRIVAL_CHECKLIST_ITEMS.map((i) => [i, { result: "", cat: "", desc: "" }])));
  const [notes, setNotes] = useState("");
  const set = (i: string, v: Partial<Line>) => setLines({ ...lines, [i]: { ...(lines[i] as Line), ...v } });
  const complete = ARRIVAL_CHECKLIST_ITEMS.every((i) => lines[i]?.result);
  async function save() {
    const r = await unwrap(
      api.POST("/api/v1/equipment-deployments/{deployment_id}/arrival-inspection", {
        params: { path: { deployment_id: d.id } },
        body: {
          checklist: ARRIVAL_CHECKLIST_ITEMS.map((i) => {
            const l = lines[i] as Line;
            return { item: i, result: l.result as S["ChecklistItemResult"], defect_category: l.result === "fail" && l.cat ? l.cat : null, defect_description: l.result === "fail" && l.desc.trim() ? l.desc.trim() : null };
          }),
          notes: notes.trim() || null,
        },
      }),
    );
    await refresh();
    if (r.result === "pass") toast.success(t("arrivalPassed"));
    else toast.warning(t("arrivalFailed"));
  }
  return (
    <StepDialog title={t("arrivalInspection")} description={t("arrivalHint")} confirmLabel={t("saveInspection")} onConfirm={save} onClose={onClose} disabled={!complete} wide testId="arrival-confirm">
      <ul className="flex flex-col divide-y rounded-md border">
        {ARRIVAL_CHECKLIST_ITEMS.map((i) => {
          const l = lines[i] as Line;
          return (
            <li key={i} className="flex flex-col gap-2 p-2" data-testid={`aic-${i}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm">{te(`aic.${i}`)}</span>
                <span className="flex gap-1" role="radiogroup" aria-label={te(`aic.${i}`)}>
                  {(["pass", "fail", "n.a."] as const).map((r) => (
                    <Button key={r} type="button" size="sm" variant={l.result === r ? (r === "fail" ? "destructive" : "default") : "outline"} aria-pressed={l.result === r} onClick={() => set(i, { result: r })} data-testid={`aic-${i}-${r === "n.a." ? "na" : r}`}>
                      {te(`checkResult.${r === "n.a." ? "na" : r}`)}
                    </Button>
                  ))}
                </span>
              </div>
              {l.result === "fail" ? (
                <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
                  <Select aria-label={t("defectCategory")} value={l.cat} onChange={(e) => set(i, { cat: e.target.value as S["DefectCategory"] })}>
                    <option value="">{t("noDefect")}</option>
                    {DEFECT_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {te(`defectCategory.${c}`)}
                      </option>
                    ))}
                  </Select>
                  <Input aria-label={t("defectDescription")} value={l.desc} onChange={(e) => set(i, { desc: e.target.value })} placeholder={t("defectDescription")} />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      <FormField id="ai-notes" label={t("notes")}>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── EQ sticker (print) ───────────── */

export function EquipmentStickerPage({ id }: { id: string }) {
  const tc = useTranslations("common");
  const t = useTranslations("eqDeployments");
  const te = useTranslations("enums");
  const locale = useLocale();
  const d = useEquipmentDeployment(id);
  const q = useEquipmentSticker(id);
  const { dateTime } = useFormatters(d.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data || !d.data) return <LoadingState />;
  const s = q.data;
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex gap-2 print:hidden">
        <Button onClick={() => window.print()} data-testid="do-print">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={`/equipment-deployments/${id}`}>{tc("back")}</Link>
        </Button>
      </div>
      {/* 90 mm weatherproof sticker: no personal data (VF-8), labels in both languages, codes LTR. */}
      <div className="paper flex w-[90mm] flex-col gap-2 rounded-xl border-4 border-black bg-white p-[4mm] text-black" data-testid="eq-sticker-print" lang={locale}>
        <AccessPrintHeader title="eqStickerTitle" projectId={d.data.project_id} variant="narrow" />
        <div className="flex flex-col items-center gap-1">
          <QrImage payload={s.qr_payload} size={220} label={t("stickerQr", { tag: s.tag })} />
          <p className="ltr font-mono text-xl font-bold tracking-wider" data-testid="eq-printed-ref">
            {s.printed_ref}
          </p>
          <BiLabel k="scanToCheck" className="text-[8pt]" />
        </div>
        <dl className="grid w-full grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-t border-black pt-2 text-sm">
          <dt>
            <BiLabel k="eqTag" className="text-[8pt]" />
          </dt>
          <dd className="text-end font-semibold">
            <Code>{s.tag}</Code>
          </dd>
          <dt>
            <BiLabel k="eqCategory" className="text-[8pt]" />
          </dt>
          <dd className="text-end font-semibold">
            <span lang="en" dir="ltr" className="block">
              {te(`eqc.${s.category}`)}
            </span>
          </dd>
          <dt>
            <BiLabel k="eqOwner" className="text-[8pt]" />
          </dt>
          <dd className="text-end font-semibold">
            <Code>{s.owner_short_code}</Code>
          </dd>
          <dt>
            <BiLabel k="eqIssued" className="text-[8pt]" />
          </dt>
          <dd className="text-end text-xs">{dateTime(s.issued_at)}</dd>
        </dl>
        <p className="border-t border-black pt-1 text-center text-[7pt]">
          <BiLabel k="eqStickerNote" stack />
        </p>
      </div>
    </div>
  );
}
