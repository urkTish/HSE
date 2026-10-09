"use client";
import { Pencil, Plus, QrCode, Radio, Trash2 } from "lucide-react";
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
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, QrImage, StepDialog } from "@/components/access/common";
import { Tick, UserName } from "@/components/cert/common";
import { FreeText, StackedDate } from "@/components/medical/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAssemblyPoints, useEmergencyContacts, useEmergencyRefresh, useEmergencySettings, useErp, useErps, useZoneProfiles } from "@/lib/api/emergency";
import { AP_KINDS } from "@/lib/emergency-enums";
import { useFormatters } from "@/lib/use-formatters";
import { ActiveBadge, Codes, EmPlanSubNav, EmReasonDialog, ErpStatusBadge, useEmCaps, useEmRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ ERP revisions (§3.1, §4.1, ER-3…ER-8) ═════════════ */

export function ErpListPage() {
  return <ProjectGate>{(p) => <ErpList project={p} />}</ProjectGate>;
}

function ErpList({ project }: { project: Project }) {
  const t = useTranslations("emergency.erp");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const router = useRouter();
  const refresh = useEmergencyRefresh();
  const { date } = useFormatters(project.id);
  const q = useErps(project.id, { enabled: caps.view });
  const [create, setCreate] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.prepare ? (
            <Button onClick={() => setCreate(true)} data-testid="erp-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EmPlanSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="erps-table">
          <THead>
            <TR>
              <TH>{t("no")}</TH>
              <TH>{t("titleCol")}</TH>
              <TH>{t("approved")}</TH>
              <TH>{t("reviewDue")}</TH>
              <TH>{tc("status")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((e) => (
              <TR key={e.id} data-testid="erp-row" data-no={e.erp_no} data-status={e.status}>
                <TD label={t("no")}>
                  <Link href={`/emergency-plans/${e.id}`} className="font-medium text-primary hover:underline">
                    <Code>{e.erp_no}</Code>
                  </Link>
                </TD>
                <TD label={t("titleCol")}>
                  <ErpTitle e={e} />
                </TD>
                <TD label={t("approved")}>{e.approved_at ? date(e.approved_at) : "—"}</TD>
                <TD label={t("reviewDue")}>
                  <StackedDate v={e.review_due_on} projectId={project.id} />
                </TD>
                <TD label={tc("status")}>
                  <span className="flex flex-wrap gap-1">
                    <ErpStatusBadge status={e.status} />
                    {e.in_force ? <Badge tone="success">{t("inForce")}</Badge> : null}
                    {e.overdue ? <Badge tone="danger">{t("overdue")}</Badge> : null}
                    {e.review_required ? <Badge tone="warning">{t("reviewRequired")}</Badge> : null}
                  </span>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {create ? (
        <StepDialog
          title={t("new")}
          description={t("newHint")}
          confirmLabel={t("create")}
          testId="erp-create-confirm"
          onConfirm={async () => {
            const e = await unwrap(api.POST("/api/v1/projects/{project_id}/erps", { params: { path: { project_id: project.id } }, body: {} }));
            await refresh();
            toast.success(t("created", { no: e.erp_no }));
            router.push(`/emergency-plans/${e.id}`);
          }}
          onClose={() => setCreate(false)}
        />
      ) : null}
    </div>
  );
}

function ErpTitle({ e }: { e: S["ErpRead"] }) {
  const ar = useLocale() === "ar";
  return <span>{ar ? e.title_ar : e.title_en}</span>;
}

export function ErpDetailPage({ id }: { id: string }) {
  const q = useErp(id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  const e = q.data;
  return <ProjectById id={e.project_id}>{(p) => <ErpDetail project={p} e={e} />}</ProjectById>;
}

function ErpDetail({ project, e }: { project: Project; e: S["ErpRead"] }) {
  const t = useTranslations("emergency.erp");
  const tc = useTranslations("common");
  const { dateTime, date } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const { label } = useEmRef();
  const caps = useEmCaps(project.id);
  const refresh = useEmergencyRefresh();
  const [edit, setEdit] = useState(false);
  const [scenario, setScenario] = useState<{ i: number | null } | null>(null);
  const [act, setAct] = useState<"submit" | "approve" | "return" | null>(null);
  const draft = e.status === "draft";
  const siteCode = (id: string) => opts.sites.find((s) => s.value === id)?.code ?? "";
  const path = { params: { path: { erp_id: e.id } } };
  const saveScenarios = async (list: S["Scenario"][]) => {
    await unwrap(api.PATCH("/api/v1/erps/{erp_id}", { ...path, body: { scenarios: list } }));
    await refresh();
  };
  const asInput = (s: S["ScenarioRead"]): S["Scenario"] => ({ ...s, rescue_plan_refs: s.rescue_plan_refs ?? [], no_such_work: s.no_such_work });
  return (
    <div>
      <Breadcrumbs items={[{ href: "/emergency-plans", label: t("title") }, { label: e.erp_no }]} />
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <Code>{e.erp_no}</Code>
            <ErpStatusBadge status={e.status} />
          </span>
        }
        description={<ErpTitle e={e} />}
        actions={
          <div className="flex flex-wrap gap-2" data-testid="erp-actions">
            {draft && caps.prepare ? (
              <>
                <Button variant="outline" onClick={() => setEdit(true)} data-testid="erp-edit">
                  <Pencil aria-hidden />
                  {t("edit")}
                </Button>
                <Button onClick={() => setAct("submit")} data-testid="erp-submit">
                  {t("submit")}
                </Button>
              </>
            ) : null}
            {e.status === "submitted" && caps.approve ? (
              <>
                <Button onClick={() => setAct("approve")} data-testid="erp-approve">
                  {t("approve")}
                </Button>
                <Button variant="outline" onClick={() => setAct("return")} data-testid="erp-return">
                  {t("return")}
                </Button>
              </>
            ) : null}
          </div>
        }
      />
      {e.overdue ? (
        <Alert tone="danger" className="mb-3" data-testid="erp-overdue-note">
          {t("overdueNote", { date: date(e.review_due_on) })}
        </Alert>
      ) : null}
      {e.review_required ? (
        <Alert tone="warning" className="mb-3" data-testid="erp-review-note">
          {t("reviewRequiredNote")}{" "}
          <Codes items={e.review_triggers.map((x) => `${x.kind}${x.ref ? ` ${x.ref}` : ""}`)} />
        </Alert>
      ) : null}
      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="p-4">
            <FieldList>
              <FieldItem label={t("document")} ltr>
                {e.document_ref}
              </FieldItem>
              <FieldItem label={t("sites")}>
                <Codes items={e.site_ids.map(siteCode)} />
              </FieldItem>
              <FieldItem label={t("clientAcceptance")}>
                {e.client_acceptance_ref ? (
                  <>
                    <Code>{e.client_acceptance_ref}</Code> · {date(e.accepted_on)}
                  </>
                ) : (
                  "—"
                )}
              </FieldItem>
              <FieldItem label={t("airportInterface")} ltr>
                {e.airport_interface_ref ?? "—"}
              </FieldItem>
              <FieldItem label={t("preparedBy")}>
                <UserName u={e.prepared_by} />
              </FieldItem>
              <FieldItem label={t("approvedBy")}>
                {e.approved_by ? (
                  <>
                    <UserName u={e.approved_by} /> · {dateTime(e.approved_at)}
                  </>
                ) : (
                  "—"
                )}
              </FieldItem>
              <FieldItem label={t("reviewDue")}>{e.review_due_on ? date(e.review_due_on) : "—"}</FieldItem>
              {e.status_reason ? (
                <FieldItem label={t("statusReason")} wide>
                  <FreeText>{e.status_reason}</FreeText>
                </FieldItem>
              ) : null}
            </FieldList>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">{t("scenarios")}</CardTitle>
            {draft && caps.prepare ? (
              <Button size="sm" variant="outline" onClick={() => setScenario({ i: null })} data-testid="scenario-add">
                <Plus aria-hidden />
                {t("addScenario")}
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            {e.scenarios.length ? (
              <Table data-testid="scenarios-table">
                <THead>
                  <TR>
                    <TH>{t("scenarioCode")}</TH>
                    <TH>{t("scenarioType")}</TH>
                    <TH>{t("sites")}</TH>
                    <TH>{t("response")}</TH>
                    <TH>{t("agencies")}</TH>
                    <TH>{t("drill")}</TH>
                    <TH />
                  </TR>
                </THead>
                <TBody>
                  {e.scenarios.map((s, i) => (
                    <TR key={s.scenario_code} data-testid="scenario-row" data-code={s.scenario_code} data-type={s.scenario_type}>
                      <TD label={t("scenarioCode")}>
                        <Code className="font-medium">{s.scenario_code}</Code>
                      </TD>
                      <TD label={t("scenarioType")}>{label("scenarios", s.scenario_type)}</TD>
                      <TD label={t("sites")}>
                        <Codes items={s.site_ids.map(siteCode)} />
                      </TD>
                      <TD label={t("response")}>{label("response_types", s.response_type)}</TD>
                      <TD label={t("agencies")}>{s.agencies.map((a) => label("agencies", a)).join(" · ")}</TD>
                      <TD label={t("drill")}>
                        {label("drill_types", s.drill_type)} · {t("everyMonths", { n: s.drill_frequency_months })}
                      </TD>
                      <TD>
                        {draft && caps.prepare ? (
                          <span className="flex gap-1">
                            <Button size="sm" variant="ghost" onClick={() => setScenario({ i })} aria-label={t("editScenario")} data-testid="scenario-edit">
                              <Pencil aria-hidden />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-danger"
                              aria-label={t("removeScenario")}
                              onClick={() => void saveScenarios(e.scenarios.filter((_, j) => j !== i).map(asInput)).catch((err) => toast.error(String(err)))}
                              data-testid="scenario-remove"
                            >
                              <Trash2 aria-hidden />
                            </Button>
                          </span>
                        ) : null}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : (
              <EmptyState message={t("noScenarios")} />
            )}
          </CardContent>
        </Card>
      </div>
      {edit ? <ErpEditDialog project={project} e={e} onClose={() => setEdit(false)} /> : null}
      {scenario ? (
        <ScenarioDialog
          project={project}
          erpSites={e.site_ids}
          initial={scenario.i === null ? null : (e.scenarios[scenario.i] ?? null)}
          onSave={async (s) => {
            const list = e.scenarios.map(asInput);
            if (scenario.i === null) list.push(s);
            else list[scenario.i] = s;
            await saveScenarios(list);
          }}
          onClose={() => setScenario(null)}
        />
      ) : null}
      {act === "return" ? (
        <EmReasonDialog
          title={t("returnTitle")}
          confirmLabel={t("return")}
          destructive={false}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/erps/{erp_id}/transitions", { ...path, body: { action: "return", reason } }))}
          onClose={() => setAct(null)}
        />
      ) : act ? (
        <StepDialog
          title={t(`${act}Title`)}
          description={t(`${act}Hint`)}
          confirmLabel={t(act)}
          testId="erp-transition-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/erps/{erp_id}/transitions", { ...path, body: { action: act } }));
            await refresh();
            toast.success(t(`${act}Done`));
          }}
          onClose={() => setAct(null)}
        />
      ) : null}
      {!caps.prepare && !caps.approve ? <p className="mt-4 text-xs text-muted-foreground">{tc("readOnly")}</p> : null}
    </div>
  );
}

function ErpEditDialog({ project, e, onClose }: { project: Project; e: S["ErpRead"]; onClose: () => void }) {
  const t = useTranslations("emergency.erp");
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const [v, setV] = useState({
    title_en: e.title_en,
    title_ar: e.title_ar,
    document_ref: e.document_ref,
    client_acceptance_ref: e.client_acceptance_ref ?? "",
    accepted_on: e.accepted_on ?? "",
    airport_interface_ref: e.airport_interface_ref ?? "",
  });
  const [sites, setSites] = useState<string[]>(e.site_ids);
  const set = (k: keyof typeof v) => (x: React.ChangeEvent<HTMLInputElement>) => setV({ ...v, [k]: x.target.value });
  return (
    <StepDialog
      wide
      title={t("edit")}
      confirmLabel={t("save")}
      testId="erp-edit-confirm"
      onConfirm={async () => {
        await unwrap(
          api.PATCH("/api/v1/erps/{erp_id}", {
            params: { path: { erp_id: e.id } },
            body: { ...v, client_acceptance_ref: v.client_acceptance_ref || null, accepted_on: v.accepted_on || null, airport_interface_ref: v.airport_interface_ref || null, site_ids: sites },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="erp-title-en" label={t("titleEn")} required>
          <Input value={v.title_en} onChange={set("title_en")} maxLength={150} />
        </FormField>
        <FormField id="erp-title-ar" label={t("titleAr")} required>
          <Input dir="rtl" value={v.title_ar} onChange={set("title_ar")} maxLength={150} />
        </FormField>
        <FormField id="erp-doc" label={t("document")} required>
          <Input className="ltr" value={v.document_ref} onChange={set("document_ref")} maxLength={40} data-testid="erp-doc" />
        </FormField>
        <MultiSelect id="erp-sites" label={t("sites")} options={opts.sites} value={sites} onChange={setSites} testId="erp-sites" />
        <FormField id="erp-client" label={t("clientAcceptanceRef")}>
          <Input className="ltr" value={v.client_acceptance_ref} onChange={set("client_acceptance_ref")} maxLength={40} />
        </FormField>
        <FormField id="erp-accepted" label={t("acceptedOn")}>
          <Input type="date" value={v.accepted_on} onChange={set("accepted_on")} />
        </FormField>
        {project.is_airport ? (
          <FormField id="erp-airport" label={t("airportInterface")} hint={t("airportHint")}>
            <Input className="ltr" value={v.airport_interface_ref} onChange={set("airport_interface_ref")} maxLength={40} />
          </FormField>
        ) : null}
      </div>
    </StepDialog>
  );
}

function ScenarioDialog({
  project,
  erpSites,
  initial,
  onSave,
  onClose,
}: {
  project: Project;
  erpSites: string[];
  initial: S["ScenarioRead"] | null;
  onSave: (s: S["Scenario"]) => Promise<void>;
  onClose: () => void;
}) {
  const t = useTranslations("emergency.erp");
  const { items, label } = useEmRef();
  const opts = useProjectOptions(project.id);
  const [code, setCode] = useState(initial?.scenario_code ?? "");
  const [type, setType] = useState<S["ScenarioType"]>(initial?.scenario_type ?? "fire_explosion");
  const [sites, setSites] = useState<string[]>(initial?.site_ids ?? erpSites);
  const [alarmEn, setAlarmEn] = useState(initial?.alarm_signal_en ?? "");
  const [alarmAr, setAlarmAr] = useState(initial?.alarm_signal_ar ?? "");
  const [response, setResponse] = useState<S["ResponseType"]>(initial?.response_type ?? "site_evacuation");
  const [sumEn, setSumEn] = useState(initial?.response_summary_en ?? "");
  const [sumAr, setSumAr] = useState(initial?.response_summary_ar ?? "");
  const [agencies, setAgencies] = useState<string[]>(initial?.agencies ?? []);
  const [drill, setDrill] = useState<S["DrillType"]>(initial?.drill_type ?? "evacuation_full");
  const [freq, setFreq] = useState(String(initial?.drill_frequency_months ?? 6));
  const [refs, setRefs] = useState((initial?.rescue_plan_refs ?? []).join(", "));
  const [noWork, setNoWork] = useState(initial?.no_such_work ?? false);
  const rescue = type === "confined_space_rescue" || type === "height_rescue";
  return (
    <StepDialog
      wide
      title={initial ? t("editScenario") : t("addScenario")}
      description={t("scenarioHint")}
      confirmLabel={t("save")}
      disabled={!code || !alarmEn || !alarmAr || !(sumEn || sumAr) || !agencies.length || !sites.length || !freq}
      testId="scenario-save"
      onConfirm={() =>
        onSave({
          scenario_code: code.trim(),
          scenario_type: type,
          site_ids: sites,
          alarm_signal_en: alarmEn,
          alarm_signal_ar: alarmAr,
          response_type: response,
          response_summary_en: sumEn || null,
          response_summary_ar: sumAr || null,
          agencies: agencies as S["app__core__emergency_enums__Agency"][],
          drill_type: drill,
          drill_frequency_months: Number(freq),
          rescue_plan_refs: refs
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          no_such_work: noWork,
        })
      }
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="sc-code" label={t("scenarioCode")} required>
          <Input className="ltr" value={code} onChange={(x) => setCode(x.target.value.toUpperCase())} maxLength={16} data-testid="sc-code" />
        </FormField>
        <FormField id="sc-type" label={t("scenarioType")} required>
          <Select value={type} onChange={(x) => setType(x.target.value as S["ScenarioType"])} data-testid="sc-type">
            {items("scenarios").map((i) => (
              <option key={i.code} value={i.code}>
                {label("scenarios", i.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <MultiSelect id="sc-sites" label={t("sites")} options={opts.sites.filter((s) => erpSites.includes(s.value))} value={sites} onChange={setSites} testId="sc-sites" />
        <FormField id="sc-response" label={t("response")} required>
          <Select value={response} onChange={(x) => setResponse(x.target.value as S["ResponseType"])} data-testid="sc-response">
            {items("response_types")
              .filter((i) => i.code !== "none")
              .map((i) => (
                <option key={i.code} value={i.code}>
                  {label("response_types", i.code)}
                </option>
              ))}
          </Select>
        </FormField>
        <FormField id="sc-alarm-en" label={t("alarmEn")} required>
          <Input value={alarmEn} onChange={(x) => setAlarmEn(x.target.value)} maxLength={150} data-testid="sc-alarm-en" />
        </FormField>
        <FormField id="sc-alarm-ar" label={t("alarmAr")} required>
          <Input dir="rtl" value={alarmAr} onChange={(x) => setAlarmAr(x.target.value)} maxLength={150} data-testid="sc-alarm-ar" />
        </FormField>
        <FormField id="sc-sum-en" label={t("summaryEn")} hint={t("summaryHint")}>
          <Textarea value={sumEn} onChange={(x) => setSumEn(x.target.value)} maxLength={2000} data-testid="sc-sum-en" />
        </FormField>
        <FormField id="sc-sum-ar" label={t("summaryAr")}>
          <Textarea dir="rtl" value={sumAr} onChange={(x) => setSumAr(x.target.value)} maxLength={2000} />
        </FormField>
        <MultiSelect id="sc-agencies" label={t("agencies")} options={items("agencies").map((i) => ({ value: i.code, label: label("agencies", i.code) }))} value={agencies} onChange={setAgencies} testId="sc-agencies" />
        <FormField id="sc-drill" label={t("drill")} required>
          <Select value={drill} onChange={(x) => setDrill(x.target.value as S["DrillType"])} data-testid="sc-drill">
            {items("drill_types").map((i) => (
              <option key={i.code} value={i.code}>
                {label("drill_types", i.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="sc-freq" label={t("frequency")} required hint={t("frequencyHint")}>
          <Input type="number" min={1} max={24} value={freq} onChange={(x) => setFreq(x.target.value)} data-testid="sc-freq" />
        </FormField>
        {rescue ? (
          <>
            <FormField id="sc-refs" label={t("rescuePlanRefs")} hint={t("rescuePlanHint")}>
              <Input className="ltr" value={refs} onChange={(x) => setRefs(x.target.value)} />
            </FormField>
            <Tick id="sc-no-work" label={t("noSuchWork")} checked={noWork} onChange={setNoWork} />
          </>
        ) : null}
      </div>
    </StepDialog>
  );
}

/* ═════════════ assembly points (§3.3, ER-6, MP QR) ═════════════ */

export function AssemblyPointsPage() {
  return <ProjectGate>{(p) => <Aps project={p} />}</ProjectGate>;
}

function Aps({ project }: { project: Project }) {
  const t = useTranslations("emergency.aps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useEmCaps(project.id);
  const q = useAssemblyPoints(project.id, {}, { enabled: caps.view });
  const [create, setCreate] = useState(false);
  const [edit, setEdit] = useState<S["ApRead"] | null>(null);
  const [qr, setQr] = useState<S["ApRead"] | null>(null);
  const [toggle, setToggle] = useState<S["ApRead"] | null>(null);
  const refresh = useEmergencyRefresh();
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.prepare ? (
            <Button onClick={() => setCreate(true)} data-testid="ap-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EmPlanSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="aps-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("site")}</TH>
              <TH>{t("location")}</TH>
              <TH>{t("capacity")}</TH>
              <TH>{t("served")}</TH>
              <TH>{t("kind")}</TH>
              <TH>{tc("status")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {items.map((a) => (
              <TR key={a.id} data-testid="ap-row" data-code={a.ap_code} data-status={a.status}>
                <TD label={t("code")}>
                  <Code className="font-medium">{a.ap_code}</Code>
                </TD>
                <TD label={t("site")}>
                  <Code>{a.site_code}</Code>
                  {a.zone_code ? (
                    <>
                      {" · "}
                      <Code>{a.zone_code}</Code>
                    </>
                  ) : null}
                </TD>
                <TD label={t("location")}>{ar ? a.location_ar : a.location_en}</TD>
                <TD label={t("capacity")} className="tabular-nums">
                  {a.capacity_persons}
                </TD>
                <TD label={t("served")}>
                  <Codes items={a.zones_served_codes} />
                </TD>
                <TD label={t("kind")}>{te(`emApKind.${a.kind}`)}</TD>
                <TD label={tc("status")}>
                  <ActiveBadge active={a.status === "active"} />
                </TD>
                <TD>
                  <span className="flex flex-wrap gap-1">
                    {a.sticker_payload ? (
                      <Button size="sm" variant="outline" onClick={() => setQr(a)} data-testid="ap-qr">
                        <QrCode aria-hidden />
                        {t("qr")}
                      </Button>
                    ) : null}
                    {caps.prepare ? (
                      <>
                        <Button size="sm" variant="outline" onClick={() => setEdit(a)} data-testid="ap-edit">
                          {t("edit")}
                        </Button>
                        <Button size="sm" variant={a.status === "active" ? "destructive-outline" : "outline"} onClick={() => setToggle(a)} data-testid="ap-toggle">
                          {a.status === "active" ? t("deactivate") : t("activate")}
                        </Button>
                      </>
                    ) : null}
                  </span>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {create || edit ? <ApDialog project={project} ap={edit} onClose={() => (setCreate(false), setEdit(null))} /> : null}
      {qr?.sticker_payload ? (
        <StepDialog title={t("qrTitle", { code: qr.ap_code })} description={t("qrHint")} confirmLabel={t("print")} onConfirm={async () => window.print()} onClose={() => setQr(null)}>
          <div className="flex flex-col items-center gap-2" data-testid="ap-sticker">
            <QrImage payload={qr.sticker_payload} size={220} label={qr.ap_code} />
            <Code className="text-lg font-semibold">{qr.ap_code}</Code>
          </div>
        </StepDialog>
      ) : null}
      {toggle ? (
        <StepDialog
          title={toggle.status === "active" ? t("deactivateTitle", { code: toggle.ap_code }) : t("activateTitle", { code: toggle.ap_code })}
          description={toggle.status === "active" ? t("deactivateHint") : undefined}
          confirmLabel={toggle.status === "active" ? t("deactivate") : t("activate")}
          destructive={toggle.status === "active"}
          testId="ap-toggle-confirm"
          onConfirm={async () => {
            await unwrap(api.PATCH("/api/v1/assembly-points/{ap_id}", { params: { path: { ap_id: toggle.id } }, body: { status: toggle.status === "active" ? "inactive" : "active" } }));
            await refresh();
          }}
          onClose={() => setToggle(null)}
        />
      ) : null}
    </div>
  );
}

function ApDialog({ project, ap, onClose }: { project: Project; ap: S["ApRead"] | null; onClose: () => void }) {
  const t = useTranslations("emergency.aps");
  const te = useTranslations("enums");
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const [code, setCode] = useState(ap?.ap_code ?? "");
  const [site, setSite] = useState(ap?.site_id ?? "");
  const [zone, setZone] = useState(ap?.zone_id ?? "");
  const [locEn, setLocEn] = useState(ap?.location_en ?? "");
  const [locAr, setLocAr] = useState(ap?.location_ar ?? "");
  const [lat, setLat] = useState(ap?.gps_lat ?? "");
  const [lng, setLng] = useState(ap?.gps_lng ?? "");
  const [cap, setCap] = useState(String(ap?.capacity_persons ?? ""));
  const [served, setServed] = useState<string[]>(ap?.zones_served ?? []);
  const [kind, setKind] = useState<S["ApKind"]>(ap?.kind ?? "primary");
  const siteZones = opts.zones.filter((z) => z.siteId === site);
  return (
    <StepDialog
      wide
      title={ap ? t("editTitle", { code: ap.ap_code }) : t("new")}
      description={t("restrictedHint")}
      confirmLabel={t("save")}
      disabled={!code || !site || !locEn || !locAr || !cap || !served.length}
      testId="ap-save"
      onConfirm={async () => {
        if (ap) {
          await unwrap(api.PATCH("/api/v1/assembly-points/{ap_id}", { params: { path: { ap_id: ap.id } }, body: { location_en: locEn, location_ar: locAr, capacity_persons: Number(cap), zones_served: served, kind } }));
        } else {
          const r = await unwrap(
            api.POST("/api/v1/projects/{project_id}/assembly-points", {
              params: { path: { project_id: project.id } },
              body: { ap_code: code.trim(), site_id: site, zone_id: zone || null, location_en: locEn, location_ar: locAr, gps_lat: lat || null, gps_lng: lng || null, capacity_persons: Number(cap), zones_served: served, kind },
            }),
          );
          toast.success(t("created", { code: r.ap_code }));
        }
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ap-code" label={t("code")} required>
          <Input className="ltr" value={code} disabled={Boolean(ap)} onChange={(x) => setCode(x.target.value.toUpperCase())} maxLength={16} data-testid="ap-code" />
        </FormField>
        <FormField id="ap-kind" label={t("kind")} required>
          <Select value={kind} onChange={(x) => setKind(x.target.value as S["ApKind"])}>
            {AP_KINDS.map((k) => (
              <option key={k} value={k}>
                {te(`emApKind.${k}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ap-site" label={t("site")} required>
          <Select value={site} disabled={Boolean(ap)} onChange={(x) => (setSite(x.target.value), setZone(""), setServed([]))} data-testid="ap-site">
            <option value="">—</option>
            {opts.sites.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ap-zone" label={t("zone")}>
          <Select value={zone} disabled={Boolean(ap)} onChange={(x) => setZone(x.target.value)} data-testid="ap-zone">
            <option value="">{t("noZone")}</option>
            {siteZones.map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ap-loc-en" label={t("locationEn")} required>
          <Input value={locEn} onChange={(x) => setLocEn(x.target.value)} maxLength={200} data-testid="ap-loc-en" />
        </FormField>
        <FormField id="ap-loc-ar" label={t("locationAr")} required>
          <Input dir="rtl" value={locAr} onChange={(x) => setLocAr(x.target.value)} maxLength={200} data-testid="ap-loc-ar" />
        </FormField>
        {!ap ? (
          <>
            <FormField id="ap-lat" label={t("lat")}>
              <Input className="ltr" inputMode="decimal" value={lat} onChange={(x) => setLat(x.target.value)} />
            </FormField>
            <FormField id="ap-lng" label={t("lng")}>
              <Input className="ltr" inputMode="decimal" value={lng} onChange={(x) => setLng(x.target.value)} />
            </FormField>
          </>
        ) : null}
        <FormField id="ap-cap" label={t("capacity")} required hint={t("capacityHint")}>
          <Input type="number" min={10} max={10000} value={cap} onChange={(x) => setCap(x.target.value)} data-testid="ap-cap" />
        </FormField>
        <MultiSelect id="ap-served" label={t("served")} options={siteZones} value={served} onChange={setServed} testId="ap-served" />
      </div>
    </StepDialog>
  );
}

/* ═════════════ emergency contacts (§3.4, P6c-2) ═════════════ */

export function EmergencyContactsPage() {
  return <ProjectGate>{(p) => <Contacts project={p} />}</ProjectGate>;
}

function Contacts({ project }: { project: Project }) {
  const t = useTranslations("emergency.contacts");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useEmCaps(project.id);
  const { label } = useEmRef();
  const opts = useProjectOptions(project.id);
  const q = useEmergencyContacts(project.id, { enabled: caps.view });
  const [edit, setEdit] = useState<S["ContactRead"] | "new" | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = [...(q.data?.items ?? [])].sort((a, b) => a.agency.localeCompare(b.agency) || a.priority - b.priority);
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.prepare ? (
            <Button onClick={() => setEdit("new")} data-testid="contact-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EmPlanSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="contacts-table">
          <THead>
            <TR>
              <TH>{t("agency")}</TH>
              <TH>{t("name")}</TH>
              <TH>{t("phone")}</TH>
              <TH>{t("sites")}</TH>
              <TH>{t("priority")}</TH>
              <TH>{tc("status")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {items.map((c) => (
              <TR key={c.id} data-testid="contact-row" data-agency={c.agency} data-active={c.active ? "yes" : "no"}>
                <TD label={t("agency")}>{label("agencies", c.agency)}</TD>
                <TD label={t("name")}>
                  {ar ? c.display_name_ar : c.display_name_en}
                  {c.person_name ? <span className="block text-xs text-muted-foreground">{c.person_name}</span> : null}
                </TD>
                <TD label={t("phone")}>
                  <a href={`tel:${c.phone}`} className="font-semibold text-primary hover:underline">
                    <bdi className="ltr">{c.phone}</bdi>
                  </a>
                  {c.available_24h ? <Badge tone="info" className="ms-1">{t("h24")}</Badge> : null}
                </TD>
                <TD label={t("sites")}>{c.site_ids.length ? <Codes items={c.site_ids.map((id) => opts.sites.find((s) => s.value === id)?.code ?? "")} /> : t("wholeProject")}</TD>
                <TD label={t("priority")}>{c.priority}</TD>
                <TD label={tc("status")}>
                  <ActiveBadge active={c.active} />
                </TD>
                <TD>
                  {caps.prepare ? (
                    <Button size="sm" variant="outline" onClick={() => setEdit(c)} data-testid="contact-edit">
                      {t("edit")}
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
      {edit ? <ContactDialog project={project} c={edit === "new" ? null : edit} onClose={() => setEdit(null)} /> : null}
    </div>
  );
}

function ContactDialog({ project, c, onClose }: { project: Project; c: S["ContactRead"] | null; onClose: () => void }) {
  const t = useTranslations("emergency.contacts");
  const { items, label } = useEmRef();
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const [agency, setAgency] = useState<string>(c?.agency ?? "civil_defense");
  const [nameEn, setNameEn] = useState(c?.display_name_en ?? "");
  const [nameAr, setNameAr] = useState(c?.display_name_ar ?? "");
  const [phone, setPhone] = useState(c?.phone ?? "");
  const [person, setPerson] = useState(c?.person_name ?? "");
  const [h24, setH24] = useState(c?.available_24h ?? true);
  const [prio, setPrio] = useState(String(c?.priority ?? 1));
  const [sites, setSites] = useState<string[]>(c?.site_ids ?? []);
  const [active, setActive] = useState(c?.active ?? true);
  return (
    <StepDialog
      wide
      title={c ? t("edit") : t("new")}
      confirmLabel={t("save")}
      disabled={!nameEn || !nameAr || !phone}
      testId="contact-save"
      onConfirm={async () => {
        const common = { display_name_en: nameEn, display_name_ar: nameAr, phone: phone.trim(), person_name: person || null, available_24h: h24, priority: Number(prio), site_ids: sites };
        if (c) await unwrap(api.PATCH("/api/v1/emergency-contacts/{contact_id}", { params: { path: { contact_id: c.id } }, body: { ...common, active } }));
        else await unwrap(api.POST("/api/v1/projects/{project_id}/emergency-contacts", { params: { path: { project_id: project.id } }, body: { ...common, agency: agency as S["app__core__emergency_enums__Agency"] } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ct-agency" label={t("agency")} required>
          <Select value={agency} disabled={Boolean(c)} onChange={(x) => setAgency(x.target.value)} data-testid="ct-agency">
            {items("agencies").map((i) => (
              <option key={i.code} value={i.code}>
                {label("agencies", i.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ct-phone" label={t("phone")} required hint={t("phoneHint")}>
          <Input className="ltr" inputMode="tel" value={phone} onChange={(x) => setPhone(x.target.value)} data-testid="ct-phone" />
        </FormField>
        <FormField id="ct-name-en" label={t("nameEn")} required>
          <Input value={nameEn} onChange={(x) => setNameEn(x.target.value)} maxLength={150} data-testid="ct-name-en" />
        </FormField>
        <FormField id="ct-name-ar" label={t("nameAr")} required>
          <Input dir="rtl" value={nameAr} onChange={(x) => setNameAr(x.target.value)} maxLength={150} data-testid="ct-name-ar" />
        </FormField>
        <FormField id="ct-person" label={t("person")} hint={t("personHint")}>
          <Input value={person} onChange={(x) => setPerson(x.target.value)} maxLength={120} />
        </FormField>
        <FormField id="ct-prio" label={t("priority")} hint={t("priorityHint")}>
          <Input type="number" min={1} max={9} value={prio} onChange={(x) => setPrio(x.target.value)} />
        </FormField>
        <MultiSelect id="ct-sites" label={t("sites")} options={opts.sites} value={sites} onChange={setSites} allLabel={t("wholeProject")} />
        <div className="flex flex-col gap-1">
          <Tick id="ct-24h" label={t("h24")} checked={h24} onChange={setH24} />
          {c ? <Tick id="ct-active" label={t("active")} checked={active} onChange={setActive} /> : null}
        </div>
      </div>
    </StepDialog>
  );
}

/* ═════════════ zone emergency profiles (§3.5) ═════════════ */

export function ZoneProfilesPage() {
  return <ProjectGate>{(p) => <Profiles project={p} />}</ProjectGate>;
}

function Profiles({ project }: { project: Project }) {
  const t = useTranslations("emergency.profiles");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const q = useZoneProfiles(project.id, { enabled: caps.view });
  const [edit, setEdit] = useState<S["ZoneProfileRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  const yes = (v: boolean) => (v ? tc("yes") : tc("no"));
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EmPlanSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="profiles-table">
          <THead>
            <TR>
              <TH>{t("zone")}</TH>
              <TH>{t("site")}</TH>
              <TH>{t("eyewash")}</TH>
              <TH>{t("extinguishers")}</TH>
              <TH>{t("kits")}</TH>
              <TH>{t("warden")}</TH>
              <TH>{t("notes")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {items.map((z) => (
              <TR key={z.zone_id} data-testid="profile-row" data-zone={z.zone_code}>
                <TD label={t("zone")}>
                  <Code className="font-medium">{z.zone_code}</Code>
                  {!z.stored ? <span className="block text-xs text-muted-foreground">{t("defaults")}</span> : null}
                </TD>
                <TD label={t("site")}>
                  <Code>{opts.sites.find((s) => s.value === z.site_id)?.code ?? ""}</Code>
                </TD>
                <TD label={t("eyewash")}>{yes(z.eyewash_required)}</TD>
                <TD label={t("extinguishers")} className="tabular-nums" data-testid="profile-ext">
                  {z.min_extinguishers}
                </TD>
                <TD label={t("kits")} className="tabular-nums">
                  {z.min_first_aid_kits}
                </TD>
                <TD label={t("warden")}>{yes(z.warden_required)}</TD>
                <TD label={t("notes")}>
                  <FreeText>{z.notes}</FreeText>
                </TD>
                <TD>
                  {caps.prepare ? (
                    <Button size="sm" variant="outline" onClick={() => setEdit(z)} data-testid="profile-edit">
                      {t("edit")}
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
      {edit ? <ProfileDialog z={edit} onClose={() => setEdit(null)} /> : null}
    </div>
  );
}

function ProfileDialog({ z, onClose }: { z: S["ZoneProfileRead"]; onClose: () => void }) {
  const t = useTranslations("emergency.profiles");
  const refresh = useEmergencyRefresh();
  const [eyewash, setEyewash] = useState(z.eyewash_required);
  const [ext, setExt] = useState(String(z.min_extinguishers));
  const [kits, setKits] = useState(String(z.min_first_aid_kits));
  const [warden, setWarden] = useState(z.warden_required);
  const [notes, setNotes] = useState(z.notes ?? "");
  return (
    <StepDialog
      title={t("editTitle", { zone: z.zone_code })}
      description={t("raiseOnly")}
      confirmLabel={t("save")}
      testId="profile-save"
      onConfirm={async () => {
        await unwrap(api.PUT("/api/v1/zones/{zone_id}/emergency-profile", { params: { path: { zone_id: z.zone_id } }, body: { eyewash_required: eyewash, min_extinguishers: Number(ext), min_first_aid_kits: Number(kits), warden_required: warden, notes: notes || null } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <Tick id="pf-eyewash" label={t("eyewash")} checked={eyewash} onChange={setEyewash} />
      <Tick id="pf-warden" label={t("warden")} checked={warden} onChange={setWarden} />
      <div className="grid grid-cols-2 gap-3">
        <FormField id="pf-ext" label={t("extinguishers")}>
          <Input type="number" min={1} max={20} value={ext} onChange={(x) => setExt(x.target.value)} data-testid="pf-ext" />
        </FormField>
        <FormField id="pf-kits" label={t("kits")}>
          <Input type="number" min={1} max={10} value={kits} onChange={(x) => setKits(x.target.value)} />
        </FormField>
      </div>
      <FormField id="pf-notes" label={t("notes")}>
        <Textarea value={notes} onChange={(x) => setNotes(x.target.value)} maxLength={500} />
      </FormField>
    </StepDialog>
  );
}

/* ═════════════ muster-reader devices (§11.3, MU-4) ═════════════ */

export function MusterDevicesPage() {
  return <ProjectGate>{(p) => <Devices project={p} />}</ProjectGate>;
}

function Devices({ project }: { project: Project }) {
  const t = useTranslations("emergency.devices");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const aps = useAssemblyPoints(project.id, {}, { enabled: caps.view });
  const [ap, setAp] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [made, setMade] = useState<S["MusterDeviceRegistered"][]>([]);
  const [revoke, setRevoke] = useState<S["MusterDeviceRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const apCode = (id: string) => aps.data?.items.find((a) => a.id === id)?.ap_code ?? "";
  async function register() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(api.POST("/api/v1/projects/{project_id}/muster-devices", { params: { path: { project_id: project.id } }, body: { ap_id: ap, device_id: deviceId.trim(), label: label.trim() } }));
      setMade((m) => [r, ...m]);
      setDeviceId("");
      setLabel("");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EmPlanSubNav />
      <Alert tone="info" className="mb-4" data-testid="devices-note">
        {t("listNote")}
      </Alert>
      {caps.prepare || caps.assets ? (
        <Card className="mb-4 max-w-2xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Radio aria-hidden className="size-4" />
              {t("register")}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <FormField id="md-ap" label={t("ap")} required>
              <Select value={ap} onChange={(x) => setAp(x.target.value)} data-testid="md-ap">
                <option value="">—</option>
                {(aps.data?.items ?? [])
                  .filter((a) => a.status === "active")
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.ap_code} · {a.site_code}
                    </option>
                  ))}
              </Select>
            </FormField>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField id="md-device" label={t("deviceId")} required>
                <Input className="ltr" value={deviceId} onChange={(x) => setDeviceId(x.target.value)} maxLength={60} data-testid="md-device" />
              </FormField>
              <FormField id="md-label" label={t("label")} required>
                <Input value={label} onChange={(x) => setLabel(x.target.value)} maxLength={100} data-testid="md-label" />
              </FormField>
            </div>
            <MutationError error={error} />
            <Button className="min-h-12 sm:w-fit" disabled={busy || !ap || !deviceId.trim() || !label.trim()} onClick={() => void register()} data-testid="md-register">
              {t("registerBtn")}
            </Button>
          </CardContent>
        </Card>
      ) : null}
      {made.length ? (
        <ul className="flex flex-col gap-3" data-testid="md-list">
          {made.map((r) => (
            <li key={r.device.id} className="rounded-md border p-3 text-sm" data-testid="md-row" data-revoked={r.device.revoked_at ? "yes" : "no"}>
              <p className="flex flex-wrap items-center gap-2">
                <Code className="font-semibold">{r.device.device_id}</Code> · {r.device.label} · <Code>{apCode(r.device.ap_id)}</Code>
                <span className="text-xs text-muted-foreground">{dateTime(r.device.registered_at)}</span>
                {r.device.revoked_at ? <Badge tone="neutral">{t("revoked")}</Badge> : null}
              </p>
              {!r.device.revoked_at ? (
                <>
                  <p className="mt-2 text-xs text-muted-foreground">{t("tokenOnce")}</p>
                  <Code className="block rounded bg-surface p-2 text-xs break-all" data-testid="md-token">
                    {r.device_token}
                  </Code>
                  <Button size="sm" variant="destructive-outline" className="mt-2" onClick={() => setRevoke(r.device)} data-testid="md-revoke">
                    {t("revoke")}
                  </Button>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {revoke ? (
        <StepDialog
          title={t("revokeTitle", { device: revoke.device_id })}
          description={t("revokeHint")}
          confirmLabel={t("revoke")}
          destructive
          testId="md-revoke-confirm"
          onConfirm={async () => {
            const d = await unwrap(api.POST("/api/v1/muster-devices/{device_pk}/revoke", { params: { path: { device_pk: revoke.id } } }));
            setMade((m) => m.map((x) => (x.device.id === d.id ? { ...x, device: d } : x)));
          }}
          onClose={() => setRevoke(null)}
        />
      ) : null}
    </div>
  );
}

/* ═════════════ emergency settings (§3.15, ER-9: tighten-only) ═════════════ */

type IntKey =
  | "erp_review_months"
  | "first_aider_ratio"
  | "warden_ratio"
  | "coverage_check_offset_minutes"
  | "first_drill_grace_days"
  | "repeat_drill_days"
  | "evacuation_target_minutes"
  | "headcount_target_minutes"
  | "response_target_minutes"
  | "drill_evaluation_days"
  | "event_review_days"
  | "muster_roll_window_hours"
  | "min_extinguishers_per_zone"
  | "min_first_aid_kits_per_zone"
  | "min_aed_per_site"
  | "muster_detail_retention_months"
  | "emergency_record_retention_years";
type Field = { k: IntKey | "emergency_register_from" | "emergency_ptw_enforcement_from" | "erp_client_acceptance_required" | "coordinator_required_per_shift" | "drill_compliance_warning_pct" | "coverage_warning_pct" | "equipment_readiness_warning_pct"; kind: "int" | "dec" | "date" | "bool"; range?: string };

const GROUPS: { title: "groupRegister" | "groupCoverage" | "groupDrills" | "groupAssets" | "groupReporting"; fields: Field[] }[] = [
  {
    title: "groupRegister",
    fields: [
      { k: "emergency_register_from", kind: "date" },
      { k: "emergency_ptw_enforcement_from", kind: "date" },
      { k: "erp_review_months", kind: "int", range: "3–12" },
      { k: "erp_client_acceptance_required", kind: "bool" },
    ],
  },
  {
    title: "groupCoverage",
    fields: [
      { k: "first_aider_ratio", kind: "int", range: "10–50" },
      { k: "warden_ratio", kind: "int", range: "10–50" },
      { k: "coordinator_required_per_shift", kind: "bool" },
      { k: "coverage_check_offset_minutes", kind: "int", range: "30–120" },
    ],
  },
  {
    title: "groupDrills",
    fields: [
      { k: "first_drill_grace_days", kind: "int", range: "0–60" },
      { k: "repeat_drill_days", kind: "int", range: "7–30" },
      { k: "evacuation_target_minutes", kind: "int", range: "3–15" },
      { k: "headcount_target_minutes", kind: "int", range: "5–30" },
      { k: "response_target_minutes", kind: "int", range: "2–4" },
      { k: "drill_evaluation_days", kind: "int", range: "1–7" },
      { k: "event_review_days", kind: "int", range: "1–14" },
      { k: "muster_roll_window_hours", kind: "int", range: "12–24" },
    ],
  },
  {
    title: "groupAssets",
    fields: [
      { k: "min_extinguishers_per_zone", kind: "int", range: "1–20" },
      { k: "min_first_aid_kits_per_zone", kind: "int", range: "1–10" },
      { k: "min_aed_per_site", kind: "int", range: "0–10" },
    ],
  },
  {
    title: "groupReporting",
    fields: [
      { k: "drill_compliance_warning_pct", kind: "dec", range: "80.0–100.0" },
      { k: "coverage_warning_pct", kind: "dec", range: "80.0–100.0" },
      { k: "equipment_readiness_warning_pct", kind: "dec", range: "80.0–100.0" },
      { k: "muster_detail_retention_months", kind: "int", range: "3–24" },
      { k: "emergency_record_retention_years", kind: "int", range: "2–10" },
    ],
  },
];

export function EmergencySettingsPage() {
  return <ProjectGate>{(p) => <Settings project={p} />}</ProjectGate>;
}

function Settings({ project }: { project: Project }) {
  const t = useTranslations("emergency.settings");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const q = useEmergencySettings(project.id, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EmPlanSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <div className="flex flex-col gap-4">
          {!caps.approve ? (
            <Alert tone="info" data-testid="settings-readonly">
              {t("readOnly")}
            </Alert>
          ) : null}
          <SettingsForm key={JSON.stringify(q.data)} project={project} s={q.data} editable={caps.approve} />
        </div>
      ) : null}
    </div>
  );
}

function SettingsForm({ project, s, editable }: { project: Project; s: S["EmergencySettingsRead"]; editable: boolean }) {
  const t = useTranslations("emergency.settings");
  const { label } = useEmRef();
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const flat = GROUPS.flatMap((g) => g.fields);
  const init = Object.fromEntries(flat.map((f) => [f.k, String((s as Record<string, unknown>)[f.k] ?? "")]));
  const [v, setV] = useState<Record<string, string>>(init);
  const [shifts, setShifts] = useState({ day: s.shift_start_times.day.slice(0, 5), night: s.shift_start_times.night.slice(0, 5) });
  const [rescueT, setRescueT] = useState(s.rescue_target_minutes);
  const [rescueM, setRescueM] = useState(s.rescue_team_min_members);
  const [drillMin, setDrillMin] = useState<Record<string, number>>(s.drill_minimums);
  const [intervals, setIntervals] = useState<Record<string, number>>(s.asset_check_intervals);
  const [excluded, setExcluded] = useState<string[]>(s.gate_presence_excluded_site_ids);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      for (const f of flat) {
        if (v[f.k] === init[f.k]) continue;
        body[f.k] = f.kind === "bool" ? v[f.k] === "true" : f.kind === "int" ? (v[f.k] === "" ? null : Number(v[f.k])) : v[f.k] || null;
      }
      if (shifts.day !== s.shift_start_times.day.slice(0, 5) || shifts.night !== s.shift_start_times.night.slice(0, 5)) body.shift_start_times = shifts;
      if (!same(rescueT, s.rescue_target_minutes)) body.rescue_target_minutes = rescueT;
      if (!same(rescueM, s.rescue_team_min_members)) body.rescue_team_min_members = rescueM;
      if (!same(drillMin, s.drill_minimums)) body.drill_minimums = drillMin;
      if (!same(intervals, s.asset_check_intervals)) body.asset_check_intervals = intervals;
      if (!same(excluded, s.gate_presence_excluded_site_ids)) body.gate_presence_excluded_site_ids = excluded;
      await unwrap(api.PATCH("/api/v1/projects/{project_id}/emergency-settings", { params: { path: { project_id: project.id } }, body: body as S["EmergencySettingsUpdate"] }));
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const num = (val: number, set: (n: number) => void, id: string) => <Input id={id} type="number" disabled={!editable} value={String(val)} onChange={(x) => set(Number(x.target.value))} className="w-24" data-testid={id} />;
  return (
    <div className="flex flex-col gap-4" data-testid="em-settings">
      <p className="text-sm text-muted-foreground">{t("tightenOnly")}</p>
      {GROUPS.map((g) => (
        <Card key={g.title}>
          <CardHeader>
            <CardTitle className="text-base">{t(g.title)}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {g.fields.map((f) =>
              f.kind === "bool" ? (
                <Tick key={f.k} id={`es-${f.k}`} label={t(`f.${f.k}`)} checked={v[f.k] === "true"} disabled={!editable} onChange={(b) => setV({ ...v, [f.k]: String(b) })} />
              ) : (
                <FormField key={f.k} id={`es-${f.k}`} label={t(`f.${f.k}`)} hint={f.range ? t("allowed", { range: f.range }) : undefined}>
                  <Input
                    type={f.kind === "date" ? "date" : f.kind === "int" ? "number" : "text"}
                    inputMode={f.kind === "dec" ? "decimal" : undefined}
                    disabled={!editable}
                    value={v[f.k]}
                    onChange={(x) => setV({ ...v, [f.k]: x.target.value })}
                    data-testid={`es-${f.k}`}
                  />
                </FormField>
              ),
            )}
            {g.title === "groupCoverage" ? (
              <>
                <FormField id="es-shift-day" label={t("shiftDay")}>
                  <Input type="time" disabled={!editable} value={shifts.day} onChange={(x) => setShifts({ ...shifts, day: x.target.value })} />
                </FormField>
                <FormField id="es-shift-night" label={t("shiftNight")}>
                  <Input type="time" disabled={!editable} value={shifts.night} onChange={(x) => setShifts({ ...shifts, night: x.target.value })} />
                </FormField>
                <MultiSelect id="es-excluded" label={t("excludedSites")} options={opts.sites} value={excluded} onChange={editable ? setExcluded : () => undefined} allLabel={t("none")} />
              </>
            ) : null}
            {g.title === "groupDrills" ? (
              <div className="sm:col-span-2 lg:col-span-3">
                <p className="mb-2 text-sm font-medium">{t("rescue")}</p>
                <div className="flex flex-wrap gap-4 text-sm">
                  <label className="flex items-center gap-2">
                    {t("rescueTargetCs")} {num(rescueT.confined_space, (n) => setRescueT({ ...rescueT, confined_space: n }), "es-rt-cs")}
                  </label>
                  <label className="flex items-center gap-2">
                    {t("rescueTargetH")} {num(rescueT.height, (n) => setRescueT({ ...rescueT, height: n }), "es-rt-h")}
                  </label>
                  <label className="flex items-center gap-2">
                    {t("rescueMinCs")} {num(rescueM.confined_space, (n) => setRescueM({ ...rescueM, confined_space: n }), "es-rm-cs")}
                  </label>
                  <label className="flex items-center gap-2">
                    {t("rescueMinH")} {num(rescueM.height, (n) => setRescueM({ ...rescueM, height: n }), "es-rm-h")}
                  </label>
                </div>
                <p className="mt-4 mb-2 text-sm font-medium">{t("drillMinimums")}</p>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.keys(drillMin).map((k) => (
                    <label key={k} className="flex items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-sm">
                      <span>{label("drill_types", k)}</span>
                      {num(drillMin[k] ?? 0, (n) => setDrillMin({ ...drillMin, [k]: n }), `es-dm-${k}`)}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
            {g.title === "groupAssets" ? (
              <div className="sm:col-span-2 lg:col-span-3">
                <p className="mb-2 text-sm font-medium">{t("intervals")}</p>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.keys(intervals).map((k) => (
                    <label key={k} className="flex items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-sm">
                      <span>{label("asset_types", k)}</span>
                      {num(intervals[k] ?? 0, (n) => setIntervals({ ...intervals, [k]: n }), `es-ci-${k}`)}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ))}
      {editable ? (
        <div className="flex flex-col gap-2">
          <MutationError error={error} />
          <Button className="w-fit" disabled={busy} onClick={() => void save()} data-testid="es-save">
            {t("save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
