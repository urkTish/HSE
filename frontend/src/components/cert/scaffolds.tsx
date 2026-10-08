"use client";
import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, ClipboardCheck, CloudLightning, OctagonX, Plus, Printer, QrCode, RefreshCw, TriangleAlert, X } from "lucide-react";
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
import { AccessPrintHeader, BiLabel, Code, DeploymentPicker, EligibilityItems, QrImage, StepDialog, WorkerLabel } from "@/components/access/common";
import { DateTimeInput, DecimalInput } from "@/components/ptw/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { ck, useCertRefresh, useScaffold, useScaffoldBoard, useScaffoldInspections, useScaffolds, useScaffoldSticker } from "@/lib/api/cert";
import { REINSPECTION_REASONS, SCAFFOLD_CHECKLIST_ITEMS, SCAFFOLD_INSPECTION_RESULTS, SCAFFOLD_INSPECTION_TYPES, SCAFFOLD_STATUSES, SCAFFOLD_TAG_STATUSES, SCAFFOLD_TYPES } from "@/lib/cert-enums";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { CertStatePanel, ScaffoldStatusBadge, ScaffoldSubNav, TAG_BORDER, TAG_TONE, TagStatusBadge, Tick, UserName } from "./common";
import { formatDate } from "@/lib/datetime";

type S = Schemas;
const PAGE_SIZE = 50;

/* ───────────── list ───────────── */

export function ScaffoldListPage() {
  return <ProjectGate>{(p) => <ScaffoldList project={p} />}</ProjectGate>;
}

function ScaffoldList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("scaffolds");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const opts = useProjectOptions(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["ScaffoldStatus"][];
  const tag = s.getAll("tag_status") as S["ScaffoldTagStatus"][];
  const [create, setCreate] = useState(false);
  const q = useScaffolds(project.id, {
    q: s.get("q") || null,
    status: status.length ? status : null,
    tag_status: tag.length ? tag : null,
    site_id: s.get("site_id") || null,
    zone_id: s.get("zone_id") ? [s.get("zone_id") as string] : null,
    engagement_id: s.get("engagement_id") ? [s.get("engagement_id") as string] : null,
    include_subcontractors: true,
    inspection_due_by: s.get("due_by") || null,
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
            <Button onClick={() => setCreate(true)} data-testid="new-scaffold">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <ScaffoldSubNav />
      <ListToolbar actions={can(me, "export.cert", project.id) ? <ExportButtons dataset="scaffolds" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="sc-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="sc-status" label={tc("status")} options={SCAFFOLD_STATUSES.map((x) => ({ value: x, label: te(`scaffoldStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="sc-tag" label={t("tagStatus")} options={SCAFFOLD_TAG_STATUSES.map((x) => ({ value: x, label: te(`tagStatus.${x}`) }))} value={tag} onChange={(v) => s.set({ tag_status: v })} />
        <SelectFilter id="sc-site" label={tc("site")} value={s.get("site_id") ?? ""} onChange={(v) => s.set({ site_id: v, zone_id: "" })} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter id="sc-zone" label={tc("zone")} value={s.get("zone_id") ?? ""} onChange={(v) => s.set({ zone_id: v })} options={opts.zones.filter((z) => !s.get("site_id") || z.siteId === s.get("site_id")).map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter id="sc-eng" label={tc("contractor")} value={s.get("engagement_id") ?? ""} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="scaffolds-table">
            <THead>
              <TR>
                <TH>{t("tag")}</TH>
                <TH>{t("location")}</TH>
                <TH>{t("type")}</TH>
                <TH>{t("tagStatus")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="scaffold-row" data-tag={x.tag}>
                  <TD label={t("tag")}>
                    <Link href={`/scaffolds/${x.id}`} className="font-medium text-primary hover:underline">
                      <Code>{x.tag}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{x.scaffold_no}</Code> · {x.engagement.short_code}
                    </span>
                  </TD>
                  <TD label={t("location")}>
                    <Code>{x.zone.code}</Code> {x.location_desc}
                  </TD>
                  <TD label={t("type")}>
                    {te(`scaffoldType.${x.scaffold_type}`)}
                    <span className="block text-xs text-muted-foreground">{t("heightClass", { h: x.height_m, c: x.load_class })}</span>
                  </TD>
                  <TD label={t("tagStatus")}>
                    <TagStatusBadge status={x.tag_status} />
                    {x.tag_valid_until ? <span className="block text-xs text-muted-foreground">{t("tagValidUntil", { date: date(x.tag_valid_until) })}</span> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <ScaffoldStatusBadge status={x.status} />
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
      {create ? <ScaffoldDialog project={project} onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

function ScaffoldDialog({ project, sc, onClose }: { project: S["ProjectRead"]; sc?: S["ScaffoldRead"]; onClose: () => void }) {
  const t = useTranslations("scaffolds");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const opts = useProjectOptions(project.id);
  const [eng, setEng] = useState(sc?.engagement.id ?? "");
  const [zone, setZone] = useState(sc?.zone.id ?? "");
  const [loc, setLoc] = useState(sc?.location_desc ?? "");
  const [level, setLevel] = useState(sc?.level_code ?? "");
  const [type, setType] = useState<S["ScaffoldType"]>(sc?.scaffold_type ?? "independent_tied");
  const [height, setHeight] = useState(sc?.height_m ?? "");
  const [loadClass, setLoadClass] = useState(String(sc?.load_class ?? 3));
  const [design, setDesign] = useState(sc?.design_ref ?? "");
  const [sheeting, setSheeting] = useState(sc?.sheeting_fitted ?? false);
  const [supervisor, setSupervisor] = useState<S["DeploymentRead"] | null>(null);
  const [crew, setCrew] = useState<S["DeploymentRead"][]>([]);
  const [pick, setPick] = useState<S["DeploymentRead"] | null>(null);
  const [tag, setTag] = useState(sc?.tag ?? "");
  const valid = zone && loc.trim() && height && (sc || (eng && supervisor && crew.length && tag.trim()));
  async function save() {
    if (sc) {
      const r = await unwrap(
        api.PATCH("/api/v1/scaffolds/{scaffold_id}", {
          params: { path: { scaffold_id: sc.id } },
          body: { zone_id: zone, location_desc: loc.trim(), level_code: level.trim() || null, scaffold_type: type, height_m: height, load_class: Number(loadClass), design_ref: design.trim() || null, sheeting_fitted: sheeting },
        }),
      );
      qc.setQueryData(ck.scaffold(sc.id), r);
      await qc.invalidateQueries({ queryKey: ["scaffolds"] });
      toast.success(tc("saved"));
      return;
    }
    const r = await unwrap(
      api.POST("/api/v1/projects/{project_id}/scaffolds", {
        params: { path: { project_id: project.id } },
        body: {
          engagement_id: eng,
          zone_id: zone,
          location_desc: loc.trim(),
          level_code: level.trim() || null,
          scaffold_type: type,
          height_m: height,
          load_class: Number(loadClass),
          design_ref: design.trim() || null,
          sheeting_fitted: sheeting,
          erection_supervisor_worker_id: (supervisor as S["DeploymentRead"]).worker_id,
          erection_crew_worker_ids: crew.map((c) => c.worker_id),
          tag: tag.trim(),
        },
      }),
    );
    await qc.invalidateQueries({ queryKey: ["scaffolds"] });
    toast.success(t("created", { tag: r.tag }));
    router.push(`/scaffolds/${r.id}`);
  }
  return (
    <StepDialog title={sc ? t("edit") : t("new")} description={t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-scaffold">
      <div className="grid gap-3 sm:grid-cols-2">
        {!sc ? (
          <FormField id="sc-eng" label={tc("contractor")} required>
            <Select value={eng} onChange={(e) => setEng(e.target.value)} data-testid="sc-engagement">
              <option value="">{tc("select")}</option>
              {opts.engagements.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        {!sc ? (
          <FormField id="sc-tag" label={t("tag")} required>
            <Input value={tag} onChange={(e) => setTag(e.target.value)} className="ltr uppercase" data-testid="sc-tag" />
          </FormField>
        ) : null}
        <FormField id="sc-zone" label={tc("zone")} required>
          <Select value={zone} onChange={(e) => setZone(e.target.value)} data-testid="sc-zone">
            <option value="">{tc("select")}</option>
            {opts.zones.map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sc-level" label={t("level")}>
          <Input value={level} onChange={(e) => setLevel(e.target.value)} className="ltr" />
        </FormField>
        <FormField id="sc-loc" label={t("location")} required>
          <Input value={loc} onChange={(e) => setLoc(e.target.value)} data-testid="sc-location" />
        </FormField>
        <FormField id="sc-type" label={t("type")} required>
          <Select value={type} onChange={(e) => setType(e.target.value as S["ScaffoldType"])}>
            {SCAFFOLD_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`scaffoldType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sc-height" label={t("height")} required hint={t("heightHint")}>
          <DecimalInput id="sc-height" value={height} onChange={setHeight} data-testid="sc-height" />
        </FormField>
        <FormField id="sc-class" label={t("loadClass")} required>
          <Select value={loadClass} onChange={(e) => setLoadClass(e.target.value)}>
            {[1, 2, 3, 4, 5, 6].map((x) => (
              <option key={x} value={x}>
                {t("classN", { n: x })}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sc-design" label={t("designRef")}>
          <Input value={design} onChange={(e) => setDesign(e.target.value)} className="ltr" data-testid="sc-design" />
        </FormField>
      </div>
      <Tick id="sc-sheeting" label={t("sheeting")} checked={sheeting} onChange={setSheeting} />
      {!sc ? (
        <>
          <DeploymentPicker id="sc-supervisor" projectId={project.id} value={supervisor} onChange={setSupervisor} label={t("supervisor")} required status={["mobilised"]} />
          <div className="flex flex-col gap-2">
            <DeploymentPicker id="sc-crew" projectId={project.id} value={pick} onChange={setPick} label={t("crew")} required status={["mobilised"]} />
            <Button
              variant="outline"
              size="sm"
              className="self-start"
              disabled={!pick || crew.some((c) => c.id === pick.id)}
              onClick={() => {
                if (pick) setCrew([...crew, pick]);
                setPick(null);
              }}
              data-testid="sc-add-crew"
            >
              <Plus aria-hidden />
              {t("addCrew")}
            </Button>
            <ul className="flex flex-wrap gap-2">
              {crew.map((c) => (
                <li key={c.id} className="flex items-center gap-1 rounded border px-2 py-1 text-sm">
                  <WorkerLabel w={c} />
                  <button type="button" aria-label={tc("remove")} onClick={() => setCrew(crew.filter((x) => x.id !== c.id))}>
                    <X aria-hidden className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </StepDialog>
  );
}

/* ───────────── detail ───────────── */

export function ScaffoldDetail({ id }: { id: string }) {
  const q = useScaffold(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => <ScaffoldView project={p} sc={q.data} />}</ProjectById>;
}

type ScStep = "inspect" | "edit" | "alteration" | "dismantle" | "close_red" | "reissue" | null;

function ScaffoldView({ project, sc }: { project: S["ProjectRead"]; sc: S["ScaffoldRead"] }) {
  const t = useTranslations("scaffolds");
  const td = useTranslations("certDesign");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const locale = useLocale();
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useCertRefresh();
  const inspections = useScaffoldInspections(sc.id);
  const [step, setStep] = useState<ScStep>(null);
  const [reason, setReason] = useState("");
  const edit = canWrite(me, "equipment.edit", project.id);
  const inspect = canWrite(me, "scaffold.inspect", project.id);
  const raise = canWrite(me, "defect.raise", project.id);
  const live = sc.status !== "dismantled";
  async function transition(to: S["ScaffoldStatus"]) {
    const r = await unwrap(api.POST("/api/v1/scaffolds/{scaffold_id}/transitions", { params: { path: { scaffold_id: sc.id } }, body: { to_status: to, reason: reason.trim() || null } }));
    qc.setQueryData(ck.scaffold(sc.id), r);
    await refresh();
    toast.success(te(`scaffoldStatus.${to}`));
  }
  async function reissue() {
    await unwrap(api.POST("/api/v1/scaffolds/{scaffold_id}/sticker/reissue", { params: { path: { scaffold_id: sc.id } }, body: { reason: reason.trim() } }));
    await refresh();
    toast.success(t("reissued"));
  }
  const restrictions = locale === "ar" ? sc.restrictions_ar || sc.restrictions_en : sc.restrictions_en || sc.restrictions_ar;
  const cfg = {
    alteration: { to: "under_alteration" as const, destructive: false },
    dismantle: { to: "dismantled" as const, destructive: true },
    close_red: { to: "closed_red" as const, destructive: true },
  };
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/scaffolds" }, { label: sc.tag }]} />
        <PageHeader
          title={`${sc.tag} — ${sc.zone.code}`}
          description={`${sc.scaffold_no} · ${te(`scaffoldType.${sc.scaffold_type}`)} · ${sc.location_desc}`}
          actions={
            <>
              <ScaffoldStatusBadge status={sc.status} />
              {inspect && live ? (
                <Button onClick={() => setStep("inspect")} data-testid="inspect-scaffold">
                  <ClipboardCheck aria-hidden />
                  {t("recordInspection")}
                </Button>
              ) : null}
              {edit && live ? (
                <Button variant="outline" onClick={() => setStep("edit")} data-testid="edit-scaffold">
                  {tc("edit")}
                </Button>
              ) : null}
              {sc.has_sticker ? (
                <Button variant="outline" asChild>
                  <Link href={`/scaffolds/${sc.id}/sticker`} data-testid="print-scaffold-sticker">
                    <QrCode aria-hidden />
                    {t("sticker")}
                  </Link>
                </Button>
              ) : null}
              {edit && sc.has_sticker ? (
                <Button variant="outline" onClick={() => setStep("reissue")}>
                  <RefreshCw aria-hidden />
                  {t("reissue")}
                </Button>
              ) : null}
              {edit && sc.status === "in_use" ? (
                <Button variant="outline" onClick={() => setStep("alteration")} data-testid="scaffold-alteration">
                  {t("alteration")}
                </Button>
              ) : null}
              {raise && sc.status === "in_use" ? (
                <Button variant="destructive-outline" onClick={() => setStep("close_red")} data-testid="scaffold-close-red">
                  {t("close_red")}
                </Button>
              ) : null}
              {edit && live && sc.status !== "in_use" ? (
                <Button variant="destructive-outline" onClick={() => setStep("dismantle")} data-testid="scaffold-dismantle">
                  {t("dismantle")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      <CertStatePanel
        tone={!sc.usable_today ? "danger" : sc.tag_status === "yellow" ? "warning" : "success"}
        Icon={!sc.usable_today ? OctagonX : sc.tag_status === "yellow" ? TriangleAlert : CircleCheck}
        word={!sc.usable_today ? t("notUsableToday") : sc.tag_status === "yellow" ? td("sc.usableRestricted") : t("usableToday")}
        line={!sc.usable_today ? td("sc.notUsableLine") : sc.tag_status === "yellow" ? td("sc.restrictedLine") : td("sc.usableLine")}
        testId="scaffold-usable"
        data={{ "data-usable": sc.usable_today ? "yes" : "no" }}
      >
        <p className="flex flex-wrap items-center gap-2">
          <TagStatusBadge status={sc.tag_status} size="lg" />
          {sc.tag_valid_until ? <span>{t("tagValidUntil", { date: date(sc.tag_valid_until) })}</span> : null}
        </p>
        {restrictions ? (
          <p className="flex items-start gap-2 rounded-md border-2 border-tag-yellow bg-surface p-2 text-base font-semibold" data-testid="scaffold-restrictions" dir="auto">
            <TriangleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-warning" />
            <span>
              <span className="block text-xs font-medium text-muted-foreground">{t("restrictions")}</span>
              {restrictions}
            </span>
          </p>
        ) : null}
        {sc.inspection_required_reason ? (
          <p className="font-medium text-destructive">
            {t("inspectionRequired", { reason: te(`reinspectionReason.${sc.inspection_required_reason}`), at: sc.inspection_required_at ? dateTime(sc.inspection_required_at) : "" })}
          </p>
        ) : null}
      </CertStatePanel>
      {sc.design_required && !sc.design_ref ? <Alert tone="warning">{t("designRequired")}</Alert> : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={tc("contractor")}>
              <Code>{sc.engagement.short_code}</Code>
            </FieldItem>
            <FieldItem label={tc("zone")}>
              <Code>{sc.zone.code}</Code> {locale === "ar" ? sc.zone.name_ar : sc.zone.name_en}
            </FieldItem>
            <FieldItem label={t("level")}>{sc.level_code ?? "—"}</FieldItem>
            <FieldItem label={t("height")}>{sc.height_m} m</FieldItem>
            <FieldItem label={t("loadClass")}>
              {t("classN", { n: sc.load_class })} · <bdi className="ltr">{sc.load_class_kn_m2} kN/m²</bdi>
            </FieldItem>
            <FieldItem label={t("designRef")}>{sc.design_ref ? <Code>{sc.design_ref}</Code> : "—"}</FieldItem>
            <FieldItem label={t("sheeting")}>{sc.sheeting_fitted ? tc("yes") : tc("no")}</FieldItem>
            <FieldItem label={t("supervisor")}>{sc.erection_supervisor ? <WorkerLabel w={sc.erection_supervisor} /> : "—"}</FieldItem>
            <FieldItem label={t("crew")} wide>
              <span className="flex flex-wrap gap-3">
                {sc.erection_crew.map((w) => (
                  <WorkerLabel key={w.id} w={w} />
                ))}
              </span>
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      {sc.crew_certification.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("crewCertification")}</CardTitle>
          </CardHeader>
          <CardContent>
            <EligibilityItems items={sc.crew_certification} projectId={project.id} />
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("inspections")}</CardTitle>
        </CardHeader>
        <CardContent>
          {inspections.isLoading ? (
            <LoadingState rows={2} />
          ) : (inspections.data?.items ?? []).length ? (
            <ul className="flex flex-col divide-y" data-testid="scaffold-inspections">
              {(inspections.data?.items ?? []).map((i) => (
                <li key={i.id} className="flex flex-col gap-1 py-2 text-sm" data-result={i.result}>
                  <span className="flex flex-wrap items-center gap-2">
                    <TagStatusBadge status={i.result} />
                    <span className="font-medium">{te(`scaffoldInspectionType.${i.inspection_type}`)}</span>
                    <span className="text-xs text-muted-foreground">{dateTime(i.inspected_at)}</span>
                    {i.tag_valid_until ? <span className="text-xs">{t("tagValidUntil", { date: date(i.tag_valid_until) })}</span> : null}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {t("inspector")}: {i.inspector ? <WorkerLabel w={i.inspector} /> : "—"} · {t("recordedBy")} <UserName u={i.recorded_by} />
                  </span>
                  {i.restrictions_en || i.restrictions_ar ? <span>{locale === "ar" ? i.restrictions_ar || i.restrictions_en : i.restrictions_en || i.restrictions_ar}</span> : null}
                  {i.checklist.some((c) => c.result === "fail") ? (
                    <span className="text-xs text-destructive">
                      {t("failedItems")}{" "}
                      {i.checklist
                        .filter((c) => c.result === "fail")
                        .map((c) => (locale === "ar" ? c.label_ar : c.label_en))
                        .join(" · ")}
                    </span>
                  ) : null}
                  <ApiWarnings warnings={i.warnings} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noInspections")}</p>
          )}
        </CardContent>
      </Card>
      <HistoryPanel entityType="scaffold" entityId={sc.id} />
      {step === "edit" ? <ScaffoldDialog project={project} sc={sc} onClose={() => setStep(null)} /> : null}
      {step === "inspect" ? <InspectionDialog project={project} sc={sc} onClose={() => setStep(null)} /> : null}
      {step === "reissue" ? (
        <StepDialog title={t("reissue")} description={t("reissueHint")} confirmLabel={t("reissue")} disabled={reason.trim().length < 5} onClose={() => setStep(null)} onConfirm={reissue}>
          <FormField id="sr-reason" label={tc("reason")} required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
          </FormField>
        </StepDialog>
      ) : null}
      {step === "alteration" || step === "dismantle" || step === "close_red" ? (
        <StepDialog
          title={t(`${step}Title`)}
          description={t(`${step}Hint`)}
          confirmLabel={t(step)}
          destructive={cfg[step].destructive}
          disabled={reason.trim().length < 5}
          onClose={() => {
            setStep(null);
            setReason("");
          }}
          onConfirm={() => transition(cfg[step].to)}
          testId="scaffold-confirm"
        >
          <FormField id="st-reason" label={tc("reason")} required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="st-reason" />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

/** SF-4: the inspector must hold SCAFFOLD-INSPECTOR and must not be the erection supervisor (server checks). */
function InspectionDialog({ project, sc, onClose }: { project: S["ProjectRead"]; sc: S["ScaffoldRead"]; onClose: () => void }) {
  const t = useTranslations("scaffolds");
  const te = useTranslations("enums");
  const refresh = useCertRefresh();
  const [type, setType] = useState<S["ScaffoldInspectionType"]>(sc.status === "under_erection" ? "handover" : sc.inspection_required_reason ? "after_adverse_weather" : "periodic");
  const [at, setAt] = useState("");
  const [inspector, setInspector] = useState<S["DeploymentRead"] | null>(null);
  const [lines, setLines] = useState<Record<string, S["ChecklistItemResult"] | "">>(Object.fromEntries(SCAFFOLD_CHECKLIST_ITEMS.map((i) => [i, ""])));
  const [result, setResult] = useState<S["ScaffoldInspectionResult"]>("green");
  const [rEn, setREn] = useState("");
  const [rAr, setRAr] = useState("");
  const complete = SCAFFOLD_CHECKLIST_ITEMS.every((i) => lines[i]);
  const valid = complete && inspector && (result !== "yellow" || rEn.trim() || rAr.trim());
  async function save() {
    const r = await unwrap(
      api.POST("/api/v1/scaffolds/{scaffold_id}/inspections", {
        params: { path: { scaffold_id: sc.id } },
        body: {
          inspection_type: type,
          inspected_at: at || null,
          inspector_worker_id: (inspector as S["DeploymentRead"]).worker_id,
          checklist: SCAFFOLD_CHECKLIST_ITEMS.map((i) => ({ item: i, result: lines[i] as S["ChecklistItemResult"] })),
          result,
          restrictions_en: rEn.trim() || null,
          restrictions_ar: rAr.trim() || null,
        },
      }),
    );
    await refresh();
    toast.success(te(`tagStatus.${r.result}`));
  }
  return (
    <StepDialog title={t("recordInspection")} description={t("inspectionHint")} confirmLabel={t("saveInspection")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="inspection-confirm">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="si-type" label={t("inspectionType")} required>
          <Select value={type} onChange={(e) => setType(e.target.value as S["ScaffoldInspectionType"])} data-testid="si-type">
            {SCAFFOLD_INSPECTION_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`scaffoldInspectionType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="si-at" label={t("inspectedAt")} hint={t("nowHint")}>
          <DateTimeInput id="si-at" value={at} onChange={setAt} />
        </FormField>
      </div>
      <DeploymentPicker id="si-inspector" projectId={project.id} value={inspector} onChange={setInspector} label={t("inspector")} required status={["mobilised"]} />
      <ul className="flex flex-col divide-y rounded-md border">
        {SCAFFOLD_CHECKLIST_ITEMS.map((i) => (
          <li key={i} className="flex flex-wrap items-center justify-between gap-2 p-2" data-testid={`sic-${i}`}>
            <span className="text-sm">{te(`sic.${i}`)}</span>
            <span className="flex gap-1" role="radiogroup" aria-label={te(`sic.${i}`)}>
              {(["pass", "fail", "n.a."] as const).map((r) => (
                <Button key={r} type="button" size="sm" variant={lines[i] === r ? (r === "fail" ? "destructive" : "default") : "outline"} aria-pressed={lines[i] === r} onClick={() => setLines({ ...lines, [i]: r })} data-testid={`sic-${i}-${r === "n.a." ? "na" : r}`}>
                  {te(`checkResult.${r === "n.a." ? "na" : r}`)}
                </Button>
              ))}
            </span>
          </li>
        ))}
      </ul>
      <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setLines(Object.fromEntries(SCAFFOLD_CHECKLIST_ITEMS.map((i) => [i, "pass"])))} data-testid="sic-all-pass">
        {t("allPass")}
      </Button>
      <fieldset className="flex flex-wrap gap-2">
        <legend className="mb-1 text-sm font-medium">{t("tagResult")}</legend>
        {SCAFFOLD_INSPECTION_RESULTS.map((r) => (
          <Button key={r} type="button" variant={result === r ? "default" : "outline"} aria-pressed={result === r} onClick={() => setResult(r)} data-testid={`si-result-${r}`}>
            <TagStatusBadge status={r} />
          </Button>
        ))}
      </fieldset>
      {result !== "green" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="si-ren" label={t("restrictionsEn")} required={result === "yellow"}>
            <Textarea value={rEn} onChange={(e) => setREn(e.target.value)} dir="ltr" maxLength={300} data-testid="si-restrictions" />
          </FormField>
          <FormField id="si-rar" label={t("restrictionsAr")}>
            <Textarea value={rAr} onChange={(e) => setRAr(e.target.value)} dir="rtl" maxLength={300} />
          </FormField>
        </div>
      ) : null}
    </StepDialog>
  );
}

/* ───────────── tag board ───────────── */

export function ScaffoldBoardPage() {
  return <ProjectGate>{(p) => <ScaffoldBoard project={p} />}</ProjectGate>;
}

function ScaffoldBoard({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("scaffolds");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const opts = useProjectOptions(project.id);
  const { date, hijri, prefs } = useFormatters(project.id);
  const s = useSearchState();
  const [reinspect, setReinspect] = useState(false);
  const q = useScaffoldBoard(project.id, { site_id: s.get("site_id") || null });
  const zones = q.data?.zones ?? [];
  return (
    <div>
      <PageHeader
        title={t("boardTitle")}
        description={t("boardSubtitle", { date: q.data ? date(q.data.as_of) : "" })}
        actions={
          canWrite(me, "defect.close", project.id) ? (
            <Button variant="destructive-outline" onClick={() => setReinspect(true)} data-testid="request-reinspection">
              <CloudLightning aria-hidden />
              {t("requestReinspection")}
            </Button>
          ) : null
        }
      />
      <ScaffoldSubNav />
      <ListToolbar>
        <SelectFilter id="sb-site" label={tc("site")} value={s.get("site_id") ?? ""} onChange={(v) => s.set({ site_id: v })} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : zones.length ? (
        <div className="flex flex-col gap-4" data-testid="scaffold-board">
          {zones.map((z) => (
            <section key={z.zone.id} className="rounded-lg border p-3" data-testid="board-zone" data-zone={z.zone.code}>
              <h2 className="mb-2 flex flex-wrap items-center gap-2 text-sm font-semibold">
                <Code>{z.zone.code}</Code>
                <span>{locale === "ar" ? z.zone.name_ar : z.zone.name_en}</span>
                <span className="text-xs font-normal text-muted-foreground">{t("countN", { n: z.scaffolds.length })}</span>
                <ZoneCounts counts={z.counts} />
              </h2>
              <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                {z.scaffolds.map((x) => (
                  <li key={x.id}>
                    <Link
                      href={`/scaffolds/${x.id}`}
                      className={cn("flex h-full min-h-touch flex-col gap-1.5 rounded-md border-2 border-s-[10px] bg-surface p-2 hover:shadow", TAG_BORDER[TAG_TONE[x.tag_status]])}
                      data-testid="board-tag"
                      data-tag={x.tag}
                      data-tag-status={x.tag_status}
                    >
                      <span className="ltr text-lg leading-tight font-bold">{x.tag}</span>
                      <TagStatusBadge status={x.tag_status} />
                      <span className="text-xs leading-snug">
                        {x.tag_valid_until ? (
                          <>
                            {t("tagValidUntil", { date: formatDate(x.tag_valid_until, { ...prefs, showHijri: false }) })}
                            {prefs.showHijri ? <span className="block text-muted-foreground">{hijri(x.tag_valid_until)}</span> : null}
                          </>
                        ) : (
                          <span className="text-muted-foreground">{te(`scaffoldStatus.${x.status}`)}</span>
                        )}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <EmptyState />
      )}
      {reinspect ? <ReinspectionDialog project={project} onClose={() => setReinspect(false)} /> : null}
    </div>
  );
}

/** Zone summary from the server's per-tag counts: what cannot be used first, never colour alone. */
function ZoneCounts({ counts }: { counts: Record<string, number> }) {
  const td = useTranslations("certDesign");
  const dnu = (counts.red ?? 0) + (counts.expired ?? 0) + (counts.inspection_required ?? 0);
  const yellow = counts.yellow ?? 0;
  const green = counts.green ?? 0;
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-xs font-semibold" data-testid="zone-counts">
      {dnu ? (
        <span className="inline-flex items-center gap-1 rounded-md bg-tag-red px-1.5 py-0.5 text-tag-red-fg">
          <OctagonX aria-hidden className="size-3.5" />
          {td("zoneDoNotUse", { n: dnu })}
        </span>
      ) : null}
      {yellow ? (
        <span className="inline-flex items-center gap-1 rounded-md bg-tag-yellow px-1.5 py-0.5 text-tag-yellow-fg">
          <TriangleAlert aria-hidden className="size-3.5" />
          {td("zoneRestricted", { n: yellow })}
        </span>
      ) : null}
      {green ? (
        <span className="inline-flex items-center gap-1 rounded-md border border-tag-green px-1.5 py-0.5 text-success">
          <CircleCheck aria-hidden className="size-3.5" />
          {td("zoneGreen", { n: green })}
        </span>
      ) : null}
    </span>
  );
}

/** SF-5: adverse weather / impact → every In Use scaffold in the site (or zone) needs re-inspection (hard stop). */
function ReinspectionDialog({ project, onClose }: { project: S["ProjectRead"]; onClose: () => void }) {
  const t = useTranslations("scaffolds");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const opts = useProjectOptions(project.id);
  const refresh = useCertRefresh();
  const [site, setSite] = useState("");
  const [zone, setZone] = useState("");
  const [reason, setReason] = useState<S["ReinspectionReason"]>("adverse_weather");
  const [text, setText] = useState("");
  async function save() {
    const r = await unwrap(api.POST("/api/v1/projects/{project_id}/scaffold-reinspection-requests", { params: { path: { project_id: project.id } }, body: { site_id: site, zone_id: zone || null, reason, reason_text: text.trim() } }));
    await refresh();
    toast.warning(t("reinspectionDone", { n: r.affected.length }));
  }
  return (
    <StepDialog title={t("requestReinspection")} description={t("reinspectionHint")} confirmLabel={t("requestReinspection")} destructive onConfirm={save} onClose={onClose} disabled={!site || text.trim().length < 5} testId="reinspection-confirm">
      <FormField id="ri-site" label={tc("site")} required>
        <Select value={site} onChange={(e) => setSite(e.target.value)} data-testid="ri-site">
          <option value="">{tc("select")}</option>
          {opts.sites.map((x) => (
            <option key={x.value} value={x.value}>
              {x.label}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="ri-zone" label={t("zoneOptional")}>
        <Select value={zone} onChange={(e) => setZone(e.target.value)}>
          <option value="">{t("allZones")}</option>
          {opts.zones
            .filter((z) => z.siteId === site)
            .map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
        </Select>
      </FormField>
      <FormField id="ri-reason" label={tc("reason")} required>
        <Select value={reason} onChange={(e) => setReason(e.target.value as S["ReinspectionReason"])}>
          {REINSPECTION_REASONS.map((x) => (
            <option key={x} value={x}>
              {te(`reinspectionReason.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="ri-text" label={t("details")} required>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={300} data-testid="ri-text" />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── sticker ───────────── */

export function ScaffoldStickerPage({ id }: { id: string }) {
  const tc = useTranslations("common");
  const t = useTranslations("scaffolds");
  const locale = useLocale();
  const sc = useScaffold(id);
  const q = useScaffoldSticker(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data || !sc.data) return <LoadingState />;
  const s = q.data;
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex gap-2 print:hidden">
        <Button onClick={() => window.print()} data-testid="do-print">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={`/scaffolds/${id}`}>{tc("back")}</Link>
        </Button>
      </div>
      {/* Fixed LTR like every printed document (English left, Arabic right), whatever the screen language. */}
      <div className="paper flex w-[90mm] flex-col gap-2 rounded-xl border-4 border-black bg-white p-[4mm] text-black" data-testid="scaffold-sticker-print" lang={locale} dir="ltr">
        <AccessPrintHeader title="scaffoldTagTitle" projectId={sc.data.project_id} variant="narrow" />
        <div className="flex flex-col items-center gap-1">
          <QrImage payload={s.qr_payload} size={220} label={t("stickerQr", { tag: s.tag })} />
          <p className="ltr font-mono text-xl font-bold tracking-wider">{s.printed_ref}</p>
          <BiLabel k="scanToCheck" className="text-[8pt]" />
        </div>
        <dl className="grid w-full grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-t border-black pt-2 text-sm">
          <dt>
            <BiLabel k="scNo" className="text-[8pt]" />
          </dt>
          <dd className="text-end font-semibold">
            <Code>{sc.data.scaffold_no}</Code>
          </dd>
          <dt>
            <BiLabel k="scZone" className="text-[8pt]" />
          </dt>
          <dd className="text-end font-semibold">
            <Code>{sc.data.zone.code}</Code>
          </dd>
          <dt>
            <BiLabel k="scLoadClass" className="text-[8pt]" />
          </dt>
          <dd className="text-end font-semibold">
            <bdi className="ltr">
              {sc.data.load_class} · {sc.data.load_class_kn_m2} kN/m²
            </bdi>
          </dd>
          <dt>
            <BiLabel k="eqOwner" className="text-[8pt]" />
          </dt>
          <dd className="text-end font-semibold">
            <Code>{s.owner_short_code}</Code>
          </dd>
        </dl>
        <p className="border-t border-black pt-1 text-center text-[7pt]">
          <BiLabel k="scStickerNote" stack className="items-center text-center" />
        </p>
      </div>
    </div>
  );
}
