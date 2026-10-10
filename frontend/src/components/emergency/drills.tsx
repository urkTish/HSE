"use client";
import { CalendarPlus, CheckCircle2, MinusCircle, Play, Plus, Siren, Trash2, Users, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useRef, useState } from "react";
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
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions, UserSelect } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { Tick, UserName } from "@/components/cert/common";
import { FreeText, StackedDate } from "@/components/medical/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { useDrill, useDrillProgramme, useDrills, useEmergencyRefresh, useErps, useRescueTeams } from "@/lib/api/emergency";
import { useUsers } from "@/lib/api/queries";
import { CHECK_ANSWERS, DRILL_SHIFTS, DRILL_STATUSES, MUSTER_DRILLS, PROJECT_DRILLS, SEVERITIES, TEAM_DRILLS, TIMELINE_KEYS } from "@/lib/emergency-enums";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { RegistryExport } from "@/components/scorecard/exports";
import {
  AnswerButtons,
  DrillResultBadge,
  DrillStatusBadge,
  EmDrillSubNav,
  EmReasonDialog,
  fromLocalInput,
  LineStatusBadge,
  Minutes,
  NoNamesHint,
  nowLocal,
  SeverityBadge,
  toLocalInput,
  useEmCaps,
  useEmRef,
} from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Drill = S["DrillRead"];

/* ═════════════ drill programme (§3.4, DP-1…DP-6) ═════════════ */

export function DrillProgrammePage() {
  return <ProjectGate>{(p) => <Programme project={p} />}</ProjectGate>;
}

function Programme({ project }: { project: Project }) {
  const t = useTranslations("emergency.programme");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const { label } = useEmRef();
  const s = useSearchState();
  const status = s.get("status") ?? "";
  const q = useDrillProgramme(project.id, {}, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const lines = (q.data?.lines ?? []).filter((l) => !status || l.status === status);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EmDrillSubNav />
      <ListToolbar>
        <SelectFilter
          id="pg-status"
          label={tc("status")}
          value={status as S["LineStatus"] | ""}
          onChange={(v) => s.set({ status: v })}
          options={(["overdue", "due", "satisfied", "retired"] as const).map((x) => ({ value: x, label: te(`emLineStatus.${x}`) }))}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : lines.length ? (
        <Table data-testid="programme-table">
          <THead>
            <TR>
              <TH>{t("line")}</TH>
              <TH>{t("type")}</TH>
              <TH>{t("scope")}</TH>
              <TH>{t("requirement")}</TH>
              <TH>{t("dueBy")}</TH>
              <TH>{t("lastSatisfied")}</TH>
              <TH>{tc("status")}</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {lines.map((l) => (
              <TR key={l.line_no} data-testid="line-row" data-line={l.line_no} data-type={l.drill_type} data-status={l.status}>
                <TD label={t("line")}>
                  <Code>{l.line_no}</Code>
                  <span className="block text-xs text-muted-foreground">
                    {te(`emLineSource.${l.source}`)}
                    {l.source_drill_no ? (
                      <>
                        {" · "}
                        <Code>{l.source_drill_no}</Code>
                      </>
                    ) : null}
                  </span>
                </TD>
                <TD label={t("type")}>{label("drill_types", l.drill_type)}</TD>
                <TD label={t("scope")}>
                  <Code>{l.site_code ?? l.team_code ?? project.code}</Code>
                </TD>
                <TD label={t("requirement")}>
                  <span className="flex flex-wrap gap-1">
                    {l.frequency_months ? <span>{t("everyMonths", { n: l.frequency_months })}</span> : null}
                    {l.shift_requirement === "night" ? <Badge tone="info">{te("emShift.night")}</Badge> : null}
                    {l.announcement_requirement === "unannounced" ? <Badge tone="info">{te("emAnnounced.unannounced")}</Badge> : null}
                  </span>
                </TD>
                <TD label={t("dueBy")}>
                  <StackedDate v={l.due_by} projectId={project.id} />
                  {l.days_to_due !== null && l.status !== "satisfied" && l.status !== "retired" ? (
                    <span className="block text-xs text-muted-foreground">{l.days_to_due < 0 ? t("daysOver", { n: -l.days_to_due }) : t("daysLeft", { n: l.days_to_due })}</span>
                  ) : null}
                </TD>
                <TD label={t("lastSatisfied")}>
                  {l.last_satisfied_by ? <Code>{l.last_satisfied_by}</Code> : "—"}
                  {l.last_satisfied_on ? <StackedDate v={l.last_satisfied_on} projectId={project.id} /> : null}
                </TD>
                <TD label={tc("status")}>
                  <LineStatusBadge status={l.status} />
                </TD>
                <TD>
                  {caps.plan && l.status !== "retired" ? (
                    <Button size="sm" variant="outline" asChild>
                      <Link
                        href={`/drills?plan=1&ptype=${l.drill_type}${l.site_id ? `&psite=${l.site_id}` : ""}${l.team_id ? `&pteam=${l.team_id}` : ""}${l.shift_requirement === "night" ? "&pshift=night" : ""}${l.announcement_requirement === "unannounced" ? "&punann=1" : ""}`}
                        data-testid="line-plan"
                      >
                        <CalendarPlus aria-hidden />
                        {t("plan")}
                      </Link>
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
    </div>
  );
}

/* ═════════════ drills list + plan (§3.5, DR-1, DR-2) ═════════════ */

export function DrillsPage() {
  return <ProjectGate>{(p) => <Drills project={p} />}</ProjectGate>;
}

function Drills({ project }: { project: Project }) {
  const t = useTranslations("emergency.drills");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { label, items: refItems } = useEmRef();
  const s = useSearchState();
  const site = s.get("site") ?? "";
  const type = (s.get("type") ?? "") as S["DrillType"] | "";
  const status = (s.get("status") ?? "") as S["DrillStatus"] | "";
  const page = Number(s.get("page") ?? 1);
  const q = useDrills(project.id, { site_id: site || null, drill_type: type ? [type] : null, status: status ? [status] : null, page, page_size: 50 }, { enabled: caps.view });
  const planOpen = s.get("plan") === "1" && caps.plan;
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.plan ? (
            <Button onClick={() => s.set({ plan: "1" })} data-testid="drill-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EmDrillSubNav />
      <ListToolbar actions={<RegistryExport dataset="emergency_drills" projectId={project.id} />}>
        <SelectFilter id="dr-site" label={t("site")} value={site} onChange={(v) => s.set({ site: v, page: null })} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} />
        <SelectFilter id="dr-type" label={t("type")} value={type} onChange={(v) => s.set({ type: v, page: null })} options={refItems("drill_types").map((x) => ({ value: x.code as S["DrillType"], label: label("drill_types", x.code) }))} />
        <SelectFilter id="dr-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={DRILL_STATUSES.map((x) => ({ value: x, label: te(`emDrillStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="drills-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("type")}</TH>
                <TH>{t("where")}</TH>
                <TH>{t("planned")}</TH>
                <TH>{tc("status")}</TH>
                <TH>{t("result")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((d) => (
                <TR key={d.id} data-testid="drill-row" data-no={d.drill_no} data-status={d.status} data-type={d.drill_type}>
                  <TD label={t("no")}>
                    <Link href={`/drills/${d.id}`} className="font-medium text-primary hover:underline">
                      <Code>{d.drill_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("type")}>
                    {label("drill_types", d.drill_type)}
                    <span className="block text-xs text-muted-foreground">
                      <Code>{d.scenario_code}</Code>
                    </span>
                  </TD>
                  <TD label={t("where")}>
                    <Code>{d.site_code ?? d.team_code ?? project.code}</Code>
                    {d.team_code && d.site_code ? (
                      <>
                        {" · "}
                        <Code>{d.team_code}</Code>
                      </>
                    ) : null}
                  </TD>
                  <TD label={t("planned")}>
                    <StackedDate v={d.planned_at} projectId={project.id} time />
                    <span className="block text-xs text-muted-foreground">
                      {te(`emShift.${d.shift}`)}
                      {d.announced ? null : <> · {te("emAnnounced.unannounced")}</>}
                    </span>
                  </TD>
                  <TD label={tc("status")}>
                    <DrillStatusBadge status={d.status} />
                    {d.late_entry ? (
                      <Badge tone="warning" className="mt-1">
                        {t("lateEntry")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={t("result")}>
                    <DrillResultBadge result={d.result} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: String(p) })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {planOpen ? (
        <PlanDrillDialog
          project={project}
          initial={{ type: (s.get("ptype") ?? "") as S["DrillType"] | "", site: s.get("psite") ?? "", team: s.get("pteam") ?? "", shift: s.get("pshift") === "night" ? "night" : "day", unannounced: s.get("punann") === "1" }}
          onClose={() => s.set({ plan: null, ptype: null, psite: null, pteam: null, pshift: null, punann: null })}
        />
      ) : null}
    </div>
  );
}

function useUserOptions(projectId: string) {
  const name = useLocalizedName();
  const q = useUsers({ project_id: projectId, status: ["active"], page_size: 200, sort: "name" });
  return useMemo(() => (q.data?.items ?? []).map((u) => ({ value: u.id, label: name(u.full_name_en, u.full_name_ar) })), [q.data, name]);
}

function PlanDrillDialog({
  project,
  initial,
  onClose,
}: {
  project: Project;
  initial: { type: S["DrillType"] | ""; site: string; team: string; shift: S["DrillShift"]; unannounced: boolean };
  onClose: () => void;
}) {
  const t = useTranslations("emergency.drills");
  const te = useTranslations("enums");
  const me = useMeData();
  const router = useRouter();
  const refresh = useEmergencyRefresh();
  const opts = useProjectOptions(project.id);
  const users = useUserOptions(project.id);
  const { label, items } = useEmRef();
  const erps = useErps(project.id);
  const inForce = (erps.data?.items ?? []).find((e) => e.in_force) ?? null;
  // StepDialog closes after a successful confirm: open the new drill instead of clearing the ?plan URL.
  const goTo = useRef<string | null>(null);
  const [type, setType] = useState<S["DrillType"]>(initial.type || "evacuation_full");
  const teamType = TEAM_DRILLS[type];
  const teams = useRescueTeams(project.id, { team_type: teamType ?? null }, { enabled: Boolean(teamType) });
  const scenarios = (inForce?.scenarios ?? []).slice().sort((a, b) => Number(b.drill_type === type) - Number(a.drill_type === type));
  const [scenario, setScenario] = useState("");
  const [site, setSite] = useState(initial.site);
  const [zones, setZones] = useState<string[]>([]);
  const [team, setTeam] = useState(initial.team);
  const [at, setAt] = useState("");
  const [shift, setShift] = useState<S["DrillShift"]>(initial.shift);
  const [announced, setAnnounced] = useState(!initial.unannounced);
  const [suspend, setSuspend] = useState(true);
  const [conductor, setConductor] = useState(me.id);
  const [evaluators, setEvaluators] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [rescueRef, setRescueRef] = useState("");
  const [airportRef, setAirportRef] = useState("");
  const projectWide = PROJECT_DRILLS.includes(type);
  const muster = MUSTER_DRILLS.includes(type);
  const sc = scenarios.find((x) => x.scenario_code === scenario) ?? scenarios.find((x) => x.drill_type === type) ?? null;
  const scenarioCode = scenario || sc?.scenario_code || "";
  return (
    <StepDialog
      wide
      title={t("new")}
      description={t("newHint")}
      confirmLabel={t("planIt")}
      testId="drill-plan-confirm"
      disabled={!scenarioCode || !at || !conductor || !evaluators.length || (!projectWide && !teamType && !site) || (Boolean(teamType) && !team)}
      onConfirm={async () => {
        const d = await unwrap(
          api.POST("/api/v1/projects/{project_id}/drills", {
            params: { path: { project_id: project.id } },
            body: {
              drill_type: type,
              scenario_code: scenarioCode,
              site_id: projectWide ? null : site || null,
              zone_ids: projectWide ? [] : zones,
              team_id: teamType ? team || null : null,
              planned_at: fromLocalInput(at) ?? "",
              shift,
              announced,
              suspend_permits: muster ? suspend : null,
              conductor_user_id: conductor,
              evaluator_user_ids: evaluators,
              plan_note: note.trim() || null,
              rescue_plan_ref: teamType ? rescueRef.trim() || null : null,
              airport_exercise_ref: type === "airport_exercise" ? airportRef.trim() || null : null,
            },
          }),
        );
        await refresh();
        toast.success(t("planned_", { no: d.drill_no }));
        goTo.current = `/drills/${d.id}`;
      }}
      onClose={() => (goTo.current ? router.push(goTo.current) : onClose())}
    >
      {!inForce && !erps.isLoading ? (
        <Alert tone="danger" className="mb-3" data-testid="drill-no-erp">
          {t("noErp")}
        </Alert>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="dp-type" label={t("type")} required>
          <Select id="dp-type" value={type} onChange={(e) => setType(e.target.value as S["DrillType"])} data-testid="dp-type">
            {items("drill_types").map((x) => (
              <option key={x.code} value={x.code}>
                {label("drill_types", x.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="dp-scenario" label={t("scenario")} required hint={inForce ? t("scenarioHint", { erp: inForce.erp_no }) : undefined}>
          <Select id="dp-scenario" value={scenarioCode} onChange={(e) => setScenario(e.target.value)} data-testid="dp-scenario">
            <option value="" />
            {scenarios.map((x) => (
              <option key={x.scenario_code} value={x.scenario_code}>
                {x.scenario_code} — {label("scenarios", x.scenario_type)}
              </option>
            ))}
          </Select>
        </FormField>
        {!projectWide && !teamType ? (
          <>
            <FormField id="dp-site" label={t("site")} required>
              <Select id="dp-site" value={site} onChange={(e) => (setSite(e.target.value), setZones([]))} data-testid="dp-site">
                <option value="" />
                {opts.sites.map((x) => (
                  <option key={x.value} value={x.value}>
                    {x.label}
                  </option>
                ))}
              </Select>
            </FormField>
            <MultiSelect id="dp-zones" label={type === "evacuation_partial" ? `${t("zones")} *` : t("zones")} options={opts.zones.filter((z) => z.siteId === site)} value={zones} onChange={setZones} testId="dp-zones" />
          </>
        ) : null}
        {teamType ? (
          <>
            <FormField id="dp-team" label={t("team")} required>
              <Select id="dp-team" value={team} onChange={(e) => setTeam(e.target.value)} data-testid="dp-team">
                <option value="" />
                {(teams.data?.items ?? []).map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.team_code}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="dp-rescue-ref" label={t("rescuePlanRef")} hint={t("rescuePlanHint")}>
              <Input className="ltr" value={rescueRef} onChange={(e) => setRescueRef(e.target.value)} maxLength={40} data-testid="dp-rescue-ref" />
            </FormField>
          </>
        ) : null}
        <FormField id="dp-at" label={t("plannedAt")} required>
          <Input id="dp-at" type="datetime-local" value={at} min={nowLocal()} onChange={(e) => setAt(e.target.value)} data-testid="dp-at" />
        </FormField>
        <FormField id="dp-shift" label={t("shift")} required>
          <Select id="dp-shift" value={shift} onChange={(e) => setShift(e.target.value as S["DrillShift"])} data-testid="dp-shift">
            {DRILL_SHIFTS.map((x) => (
              <option key={x} value={x}>
                {te(`emShift.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="dp-conductor" label={t("conductor")} required>
          <UserSelect id="dp-conductor" projectId={project.id} value={conductor} onChange={(e) => setConductor(e.target.value)} data-testid="dp-conductor" />
        </FormField>
        <MultiSelect id="dp-evaluators" label={`${t("evaluators")} *`} options={users} value={evaluators} onChange={setEvaluators} testId="dp-evaluators" />
        {type === "airport_exercise" && project.is_airport ? (
          <FormField id="dp-airport" label={t("airportRef")}>
            <Input className="ltr" value={airportRef} onChange={(e) => setAirportRef(e.target.value)} maxLength={40} data-testid="dp-airport" />
          </FormField>
        ) : null}
      </div>
      <div className="mt-3 flex flex-col gap-2">
        <Tick id="dp-announced" label={t("announced")} checked={announced} onChange={setAnnounced} />
        {muster ? <Tick id="dp-suspend" label={t("suspendPermits")} checked={suspend} onChange={setSuspend} /> : null}
      </div>
      <FormField id="dp-note" label={t("planNote")} hint={project.is_airport ? t("planNoteAirport") : <NoNamesHint />} className="mt-3">
        <Textarea id="dp-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} data-testid="dp-note" />
      </FormField>
    </StepDialog>
  );
}

/* ═════════════ drill detail: plan → run → evaluation (§4.4, DR-3…DR-9) ═════════════ */

export function DrillDetailPage({ id }: { id: string }) {
  const q = useDrill(id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  const d = q.data;
  return <ProjectById id={d.project_id}>{(p) => <DrillDetail project={p} d={d} />}</ProjectById>;
}

function DrillDetail({ project, d }: { project: Project; d: Drill }) {
  const t = useTranslations("emergency.drill");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { label } = useEmRef();
  const refresh = useEmergencyRefresh();
  const [act, setAct] = useState<"start" | "conduct" | "cancel" | "void" | null>(null);
  const path = { params: { path: { drill_id: d.id } } };
  const evaluator = d.evaluators.some((u) => u.id === me.id);
  const zoneCodes = d.zone_ids.map((z) => opts.zoneById.get(z)?.code ?? "").filter(Boolean);
  const target = (k: string) => (d.targets as Record<string, number | null>)[k] ?? null;
  const running = d.status === "in_progress" || d.status === "conducted";
  return (
    <div>
      <Breadcrumbs items={[{ href: "/drills", label: t("drills") }, { label: d.drill_no }]} />
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <Code>{d.drill_no}</Code>
            <DrillStatusBadge status={d.status} />
            <DrillResultBadge result={d.result} />
            {d.late_entry ? <Badge tone="warning">{t("lateEntry")}</Badge> : null}
          </span>
        }
        description={`${label("drill_types", d.drill_type)} · ${d.scenario_code}`}
        actions={
          <div className="flex flex-wrap gap-2" data-testid="drill-actions">
            {d.status === "planned" && caps.run ? (
              <Button onClick={() => setAct("start")} data-testid="drill-start">
                <Play aria-hidden />
                {t("start")}
              </Button>
            ) : null}
            {d.status === "in_progress" && caps.run ? (
              <Button onClick={() => setAct("conduct")} data-testid="drill-conduct">
                {t("conduct")}
              </Button>
            ) : null}
            {(d.status === "planned" || d.status === "in_progress") && caps.plan ? (
              <Button variant="destructive-outline" onClick={() => setAct("cancel")} data-testid="drill-cancel">
                {t("cancel")}
              </Button>
            ) : null}
            {d.status !== "voided" && d.status !== "cancelled" && caps.void ? (
              <Button variant="destructive-outline" onClick={() => setAct("void")} data-testid="drill-void">
                {t("void")}
              </Button>
            ) : null}
          </div>
        }
      />
      <ApiWarnings warnings={d.warnings} />
      {d.muster_id ? (
        <Alert tone={d.status === "in_progress" ? "warning" : "info"} className="mb-3" data-testid="drill-muster">
          <span className="flex flex-wrap items-center gap-2">
            <Users aria-hidden className="size-4" />
            {t("muster")} <Code>{d.muster_no}</Code>
            <Button size="sm" asChild>
              <Link href={`/musters/${d.muster_id}`} data-testid="drill-muster-open">
                {t("openMuster")}
              </Link>
            </Button>
          </span>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="p-4">
            <FieldList>
              <FieldItem label={t("where")}>
                <Code>{d.site_code ?? project.code}</Code>
                {zoneCodes.length ? <> · {zoneCodes.join(", ")}</> : null}
                {d.team_code ? (
                  <>
                    {" · "}
                    <Code>{d.team_code}</Code>
                  </>
                ) : null}
              </FieldItem>
              <FieldItem label={t("planned")}>
                <StackedDate v={d.planned_at} projectId={project.id} time />
                <span className="block text-xs text-muted-foreground">
                  {te(`emShift.${d.shift}`)} · {d.announced ? t("announced") : te("emAnnounced.unannounced")}
                </span>
              </FieldItem>
              <FieldItem label={t("conductor")}>
                <UserName u={d.conductor} />
              </FieldItem>
              <FieldItem label={t("evaluators")}>
                {d.evaluators.map((u, i) => (
                  <span key={u.id}>
                    {i ? ", " : null}
                    <UserName u={u} />
                  </span>
                ))}
              </FieldItem>
              {MUSTER_DRILLS.includes(d.drill_type) ? <FieldItem label={t("suspendPermits")}>{d.suspend_permits ? tc("yes") : tc("no")}</FieldItem> : null}
              {d.rescue_plan_ref ? (
                <FieldItem label={t("rescuePlanRef")} ltr>
                  {d.rescue_plan_ref}
                </FieldItem>
              ) : null}
              {d.airport_exercise_ref ? (
                <FieldItem label={t("airportRef")} ltr>
                  {d.airport_exercise_ref}
                </FieldItem>
              ) : null}
              {d.plan_note ? (
                <FieldItem label={t("planNote")} wide>
                  <FreeText>{d.plan_note}</FreeText>
                </FieldItem>
              ) : null}
              {d.status_reason ? (
                <FieldItem label={t("statusReason")} wide>
                  <FreeText>{d.status_reason}</FreeText>
                </FieldItem>
              ) : null}
            </FieldList>
          </CardContent>
        </Card>
        {d.status !== "planned" && d.status !== "cancelled" ? (
          <Card data-testid="drill-measures">
            <CardHeader>
              <CardTitle>{t("measures")}</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3 p-4 pt-0 sm:grid-cols-4">
              {(
                [
                  ["evac_min", "evacuation_min"],
                  ["headcount_min", "headcount_min"],
                  ["response_min", "response_min"],
                  ["rescue_min", "rescue_min"],
                ] as const
              ).map(([m, tk]) =>
                d.measures[m] !== null || target(tk) !== null ? (
                  <div key={m} className="rounded-md border p-3" data-testid="measure" data-key={m}>
                    <p className="text-xs text-muted-foreground">{t(`m_${m}`)}</p>
                    <Minutes v={d.measures[m]} target={target(tk)} testId={`measure-${m}`} />
                  </div>
                ) : null,
              )}
            </CardContent>
          </Card>
        ) : null}
        {running ? <TimingsCard project={project} d={d} editable={caps.run && running && !d.evaluation} /> : null}
        {d.evaluation ? (
          <EvaluationView project={project} d={d} />
        ) : d.status === "conducted" && caps.evaluate && evaluator ? (
          <EvaluationForm project={project} d={d} />
        ) : d.status === "conducted" ? (
          <Alert tone="info" data-testid="eval-waiting">
            {t("evalWaiting")}
          </Alert>
        ) : null}
      </div>
      {act === "start" ? (
        <StartDialog d={d} onClose={() => setAct(null)} />
      ) : act === "conduct" ? (
        <StepDialog
          title={t("conductTitle")}
          description={t("conductHint")}
          confirmLabel={t("conduct")}
          testId="drill-conduct-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/drills/{drill_id}/transitions", { ...path, body: { action: "conduct" } }));
            await refresh();
            toast.success(t("conducted"));
          }}
          onClose={() => setAct(null)}
        />
      ) : act ? (
        <EmReasonDialog
          title={t(act === "cancel" ? "cancelTitle" : "voidTitle")}
          confirmLabel={t(act)}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/drills/{drill_id}/transitions", { ...path, body: { action: act, reason } }))}
          onClose={() => setAct(null)}
        />
      ) : null}
    </div>
  );
}

function StartDialog({ d, onClose }: { d: Drill; onClose: () => void }) {
  const t = useTranslations("emergency.drill");
  const refresh = useEmergencyRefresh();
  const [past, setPast] = useState(false);
  const [alarm, setAlarm] = useState(nowLocal());
  return (
    <StepDialog
      title={t("startTitle")}
      description={MUSTER_DRILLS.includes(d.drill_type) ? (d.suspend_permits ? t("startHintSuspend") : t("startHintMuster")) : t("startHint")}
      confirmLabel={t("start")}
      testId="drill-start-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/drills/{drill_id}/transitions", { params: { path: { drill_id: d.id } }, body: { action: "start", alarm_at: past ? fromLocalInput(alarm) : null } }));
        await refresh();
        toast.success(t("started"));
      }}
      onClose={onClose}
    >
      <Tick id="ds-past" label={t("alarmEarlier")} checked={past} onChange={setPast} />
      {past ? (
        <FormField id="ds-alarm" label={t("alarmAt")} hint={t("alarmLateHint")} className="mt-2">
          <Input id="ds-alarm" type="datetime-local" value={alarm} max={nowLocal()} onChange={(e) => setAlarm(e.target.value)} data-testid="ds-alarm" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}

/** DR-5: the timings this drill type records (reference DT applies_to) and the outside agencies that took part. */
function TimingsCard({ project, d, editable }: { project: Project; d: Drill; editable: boolean }) {
  const t = useTranslations("emergency.drill");
  const { items, label } = useEmRef();
  const { dateTime } = useFormatters(project.id);
  const refresh = useEmergencyRefresh();
  const keys = (items("drill_types").find((x) => x.code === d.drill_type)?.applies_to ?? []) as string[];
  const typed = TIMELINE_KEYS.filter((k) => keys.includes(k));
  const tl = d.timeline as Record<string, string | null | undefined>;
  // Only edited fields live in state: the reference list (and so `typed`) may load after the first render.
  const [edits, setV] = useState<Record<string, string>>({});
  const v: Record<string, string> = Object.fromEntries(typed.map((k) => [k, edits[k] ?? toLocalInput(tl[k])]));
  const [ext, setExt] = useState<S["ExternalParticipation"][]>((d.external_participation as S["ExternalParticipation"][]) ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const timeline: S["Timeline"] = Object.fromEntries(typed.filter((k) => k in edits).map((k) => [k, fromLocalInput(edits[k] ?? "")]));
      await unwrap(
        api.PATCH("/api/v1/drills/{drill_id}", {
          params: { path: { drill_id: d.id } },
          body: { timeline, external_participation: ext.map((x) => ({ agency: x.agency, ref: x.ref || null, arrived_at: x.arrived_at || null })) },
        }),
      );
      await refresh();
      toast.success(t("timingsSaved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card data-testid="drill-timings">
      <CardHeader>
        <CardTitle>{t("timings")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-4 pt-0">
        <div className="grid gap-3 sm:grid-cols-2">
          {typed.map((k) => (
            <FormField key={k} id={`tl-${k}`} label={t(`tl_${k}`)}>
              {editable ? (
                <Input id={`tl-${k}`} type="datetime-local" step={1} value={v[k] ?? ""} onChange={(e) => setV({ ...edits, [k]: e.target.value })} data-testid={`tl-${k}`} />
              ) : (
                <span data-testid={`tl-${k}`}>{tl[k] ? dateTime(tl[k]) : "—"}</span>
              )}
            </FormField>
          ))}
          {keys.includes("headcount_complete_at") ? (
            <FormField id="tl-headcount" label={t("tl_headcount_complete_at")} hint={t("headcountAuto")}>
              <span data-testid="tl-headcount_complete_at">{tl.headcount_complete_at ? dateTime(tl.headcount_complete_at) : "—"}</span>
            </FormField>
          ) : null}
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">{t("external")}</p>
          {ext.length ? (
            <ul className="flex flex-col gap-2">
              {ext.map((x, i) => (
                <li key={i} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[1fr_1fr_1fr_auto]" data-testid="ext-row">
                  {editable ? (
                    <>
                      <Select aria-label={t("agency")} value={x.agency} onChange={(e) => setExt(ext.map((y, j) => (j === i ? { ...y, agency: e.target.value as S["app__core__emergency_enums__Agency"] } : y)))} data-testid="ext-agency">
                        {items("agencies").map((a) => (
                          <option key={a.code} value={a.code}>
                            {label("agencies", a.code)}
                          </option>
                        ))}
                      </Select>
                      <Input aria-label={t("extRef")} className="ltr" placeholder={t("extRef")} value={x.ref ?? ""} onChange={(e) => setExt(ext.map((y, j) => (j === i ? { ...y, ref: e.target.value } : y)))} maxLength={40} />
                      <Input
                        aria-label={t("arrivedAt")}
                        type="datetime-local"
                        value={toLocalInput(x.arrived_at)}
                        onChange={(e) => setExt(ext.map((y, j) => (j === i ? { ...y, arrived_at: fromLocalInput(e.target.value) } : y)))}
                      />
                      <Button variant="ghost" size="sm" aria-label={t("remove")} onClick={() => setExt(ext.filter((_, j) => j !== i))}>
                        <Trash2 aria-hidden />
                      </Button>
                    </>
                  ) : (
                    <span>
                      {label("agencies", x.agency)}
                      {x.ref ? <> · <bdi className="ltr">{x.ref}</bdi></> : null}
                      {x.arrived_at ? <> · {dateTime(x.arrived_at)}</> : null}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noExternal")}</p>
          )}
          {editable ? (
            <Button variant="outline" size="sm" className="mt-2" onClick={() => setExt([...ext, { agency: "civil_defense", ref: null, arrived_at: null }])} data-testid="ext-add">
              <Plus aria-hidden />
              {t("addAgency")}
            </Button>
          ) : null}
        </div>
        {editable ? (
          <div className="flex flex-col gap-2">
            <MutationError error={error} />
            <Button className="w-fit" onClick={() => void save()} disabled={busy} data-testid="timings-save">
              {t("saveTimings")}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

type FindingDraft = S["app__schemas__emergency__FindingInput"];

/** Criterion code and label as two flex items: a real gap in both directions (the code is an LTR isolate). */
function CriterionLabel({ code, label, className }: { code: string; label: string; className?: string }) {
  return (
    <span className={cn("flex min-w-0 items-baseline gap-2", className)}>
      <Code className="shrink-0 text-xs font-semibold text-muted-foreground">{code}</Code>
      <span className="min-w-0">{label}</span>
    </span>
  );
}

function EvaluationForm({ project, d }: { project: Project; d: Drill }) {
  const t = useTranslations("emergency.eval");
  const te = useTranslations("enums");
  const { items, label } = useEmRef();
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const criteria = items("criteria").filter((c) => (c.applies_to ?? []).includes(d.drill_type));
  const [answers, setAnswers] = useState<Record<string, S["CheckAnswer"]>>({});
  const [findings, setFindings] = useState<FindingDraft[]>([]);
  const [sumEn, setSumEn] = useState("");
  const [sumAr, setSumAr] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const done = criteria.every((c) => answers[c.code]);
  const fails = criteria.filter((c) => answers[c.code] === "fail");
  const setF = (i: number, p: Partial<FindingDraft>) => setFindings(findings.map((f, j) => (j === i ? { ...f, ...p } : f)));
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.POST("/api/v1/drills/{drill_id}/evaluation", {
          params: { path: { drill_id: d.id } },
          body: {
            criteria: criteria.map((c) => ({ criterion: c.code as S["Criterion"], answer: answers[c.code] as S["CheckAnswer"] })),
            findings: findings.map((f) => ({ ...f, description_en: f.description_en.trim(), description_ar: f.description_ar?.trim() || null, engagement_id: f.engagement_id || null })),
            summary_en: sumEn.trim() || null,
            summary_ar: sumAr.trim() || null,
          },
        }),
      );
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card data-testid="eval-form">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 p-4 pt-0">
        <ol className="flex flex-col gap-3">
          {criteria.map((c) => (
            <li key={c.code} className="flex flex-col gap-2" data-testid="eval-criterion" data-code={c.code}>
              <CriterionLabel code={c.code} label={label("criteria", c.code)} className="text-sm font-medium" />
              <AnswerButtons
                value={answers[c.code]}
                options={CHECK_ANSWERS.map((a) => ({ value: a, label: te(`checkAnswer.${a}`) }))}
                onChange={(a) => setAnswers({ ...answers, [c.code]: a })}
                danger={["fail"]}
                testId={`ev-${c.code}`}
              />
            </li>
          ))}
        </ol>
        {fails.length ? (
          <Alert tone="warning" data-testid="eval-fail-note">
            {t("failNote", { n: fails.length })}
          </Alert>
        ) : null}
        <div>
          <p className="mb-2 text-sm font-medium">{t("findings")}</p>
          <ul className="flex flex-col gap-3">
            {findings.map((f, i) => (
              <li key={i} className="flex flex-col gap-2 rounded-md border p-3" data-testid="ev-finding">
                <div className="grid gap-2 sm:grid-cols-3">
                  <FormField id={`ef-cat-${i}`} label={t("category")}>
                    <Select id={`ef-cat-${i}`} value={f.category} onChange={(e) => setF(i, { category: e.target.value as S["FindingCategory"] })} data-testid="ef-category">
                      {items("finding_categories").map((x) => (
                        <option key={x.code} value={x.code}>
                          {label("finding_categories", x.code)}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  <FormField id={`ef-sev-${i}`} label={t("severity")}>
                    <Select id={`ef-sev-${i}`} value={f.severity} onChange={(e) => setF(i, { severity: e.target.value as FindingDraft["severity"], create_ca: e.target.value !== "minor" || f.create_ca })} data-testid="ef-severity">
                      {SEVERITIES.map((x) => (
                        <option key={x} value={x}>
                          {te(`emSeverity.${x}`)}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  <FormField id={`ef-eng-${i}`} label={t("engagement")}>
                    <Select id={`ef-eng-${i}`} value={f.engagement_id ?? ""} onChange={(e) => setF(i, { engagement_id: e.target.value || null })} data-testid="ef-engagement">
                      <option value="" />
                      {opts.engagements.map((x) => (
                        <option key={x.value} value={x.value}>
                          {x.label}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                </div>
                <FormField id={`ef-en-${i}`} label={t("descriptionEn")} required hint={<NoNamesHint />}>
                  <Textarea id={`ef-en-${i}`} value={f.description_en} onChange={(e) => setF(i, { description_en: e.target.value })} maxLength={500} data-testid="ef-description" />
                </FormField>
                <FormField id={`ef-ar-${i}`} label={t("descriptionAr")}>
                  <Textarea id={`ef-ar-${i}`} dir="rtl" value={f.description_ar ?? ""} onChange={(e) => setF(i, { description_ar: e.target.value })} maxLength={500} />
                </FormField>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Tick id={`ef-ca-${i}`} label={f.severity === "minor" ? t("createCa") : t("caAuto")} checked={f.severity !== "minor" || Boolean(f.create_ca)} disabled={f.severity !== "minor"} onChange={(v) => setF(i, { create_ca: v })} />
                  <Button variant="ghost" size="sm" onClick={() => setFindings(findings.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                    {t("remove")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <Button variant="outline" size="sm" className="mt-2" onClick={() => setFindings([...findings, { category: "plan_deficiency", severity: "major", description_en: "", description_ar: null, engagement_id: null, create_ca: true }])} data-testid="ev-finding-add">
            <Plus aria-hidden />
            {t("addFinding")}
          </Button>
          <p className="mt-2 text-xs text-muted-foreground">{t("autoHint")}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="ev-sum-en" label={t("summaryEn")}>
            <Textarea id="ev-sum-en" value={sumEn} onChange={(e) => setSumEn(e.target.value)} maxLength={2000} data-testid="ev-summary" />
          </FormField>
          <FormField id="ev-sum-ar" label={t("summaryAr")}>
            <Textarea id="ev-sum-ar" dir="rtl" value={sumAr} onChange={(e) => setSumAr(e.target.value)} maxLength={2000} />
          </FormField>
        </div>
        <MutationError error={error} />
        <Button className="w-fit" onClick={() => void submit()} disabled={busy || !done || findings.some((f) => f.description_en.trim().length < 5)} data-testid="ev-submit">
          {t("submit")}
        </Button>
      </CardContent>
    </Card>
  );
}

type EvalFinding = { category: string; severity: string; description_en: string; description_ar?: string | null; ca_id?: string | null; ca_ref?: string | null; auto?: boolean; ref?: string | null };
type Evaluation = { criteria?: { criterion: string; answer: S["CheckAnswer"] }[]; findings?: EvalFinding[]; summary_en?: string | null; summary_ar?: string | null; evaluated_at?: string | null };

function EvaluationView({ project, d }: { project: Project; d: Drill }) {
  const t = useTranslations("emergency.eval");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const { label } = useEmRef();
  const { dateTime } = useFormatters(project.id);
  const ev = (d.evaluation ?? {}) as Evaluation;
  const fails = (ev.criteria ?? []).filter((c) => c.answer === "fail");
  const summary = ar ? ev.summary_ar || ev.summary_en : ev.summary_en || ev.summary_ar;
  return (
    <Card data-testid="eval-view">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {t("result")} <DrillResultBadge result={d.result} />
        </CardTitle>
        {ev.evaluated_at ? <p className="text-xs text-muted-foreground">{t("evaluatedAt", { at: dateTime(ev.evaluated_at) })}</p> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4 p-4 pt-0">
        <ul className="grid gap-x-6 gap-y-2 text-sm lg:grid-cols-2">
          {(ev.criteria ?? []).map((c) => (
            <li key={c.criterion} className="flex items-start gap-2" data-testid="eval-answer" data-code={c.criterion} data-answer={c.answer}>
              <Badge tone={c.answer === "fail" ? "danger" : c.answer === "pass" ? "success" : "neutral"} className="min-w-16 shrink-0 justify-center">
                {c.answer === "fail" ? <XCircle aria-hidden /> : c.answer === "pass" ? <CheckCircle2 aria-hidden /> : <MinusCircle aria-hidden />}
                {te(`checkAnswer.${c.answer}`)}
              </Badge>
              <CriterionLabel code={c.criterion} label={label("criteria", c.criterion)} />
            </li>
          ))}
        </ul>
        {fails.length ? (
          <p className="flex items-center gap-1.5 text-sm font-medium text-danger">
            <XCircle aria-hidden className="size-4 shrink-0" />
            {t("failNote", { n: fails.length })}
          </p>
        ) : null}
        <div>
          <p className="mb-2 text-sm font-medium">{t("findings")}</p>
          {ev.findings?.length ? (
            <ul className="flex flex-col gap-2">
              {ev.findings.map((f, i) => (
                <li key={i} className="flex flex-col gap-1 rounded-md border p-3" data-testid="eval-finding" data-severity={f.severity}>
                  <span className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={f.severity} />
                    <span className="text-xs text-muted-foreground">{label("finding_categories", f.category)}</span>
                    {f.auto ? <Badge tone="neutral">{t("auto")}</Badge> : null}
                    {f.ref ? <Code className="text-xs">{f.ref}</Code> : null}
                  </span>
                  <span dir={ar && f.description_ar ? "rtl" : "auto"}>{ar ? f.description_ar || f.description_en : f.description_en}</span>
                  {f.ca_id ? (
                    <Link href={`/actions/${f.ca_id}`} className="w-fit text-sm text-primary hover:underline" data-testid="finding-ca">
                      <Code>{f.ca_ref ?? t("ca")}</Code>
                    </Link>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noFindings")}</p>
          )}
        </div>
        {summary ? (
          <FieldList>
            <FieldItem label={t("summary")} wide>
              <FreeText>{summary}</FreeText>
            </FieldItem>
          </FieldList>
        ) : null}
        {d.result === "unsatisfactory" ? (
          <Alert tone="warning" data-testid="eval-repeat-note">
            <Siren aria-hidden className="me-1 inline size-4" />
            {t("repeatNote")}
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
