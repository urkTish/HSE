"use client";
import { CheckCircle2, Crown, HeartPulse, Plus, X, XCircle } from "lucide-react";
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
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions, UserSelect } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, DeploymentPicker, StepDialog, WorkerLabel } from "@/components/access/common";
import { Tick, UserName } from "@/components/cert/common";
import { StackedDate } from "@/components/medical/common";
import { DateFilter, isOn } from "@/components/training/common";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useEquipmentList } from "@/lib/api/cert";
import { useCoverage, useEmergencyAssets, useEmergencyRefresh, useRescueTeams, useRoster } from "@/lib/api/emergency";
import { todayInZone } from "@/lib/datetime";
import { DRILL_SHIFTS, ROSTER_SHIFTS, TEAM_TYPES } from "@/lib/emergency-enums";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { ActiveBadge, Codes, CoverageBadge, EmOrgSubNav, PrivacyNote, useEmCaps, useEmRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ emergency roster (§3.6, EO-1…EO-3, P6c-2) ═════════════ */

export function RosterPage() {
  return <ProjectGate>{(p) => <Roster project={p} />}</ProjectGate>;
}

function Roster({ project }: { project: Project }) {
  const t = useTranslations("emergency.roster");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { label, items: refItems } = useEmRef();
  const s = useSearchState();
  const site = s.get("site") ?? "";
  const role = (s.get("role") ?? "") as S["EmergencyRole"] | "";
  const all = isOn(s.get("all"));
  const page = Number(s.get("page") ?? 1);
  const q = useRoster(project.id, { site_id: site || null, role: role || null, active_only: !all, page, page_size: 50 }, { enabled: caps.view });
  const [create, setCreate] = useState(false);
  const [end, setEnd] = useState<S["RosterRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.roster ? (
            <Button onClick={() => setCreate(true)} data-testid="roster-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EmOrgSubNav />
      <PrivacyNote>{t("privacy")}</PrivacyNote>
      <ListToolbar>
        <SelectFilter id="ro-site" label={t("site")} value={site} onChange={(v) => s.set({ site: v, page: null })} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} />
        <SelectFilter id="ro-role" label={t("role")} value={role} onChange={(v) => s.set({ role: v, page: null })} options={refItems("roles").map((r) => ({ value: r.code as S["EmergencyRole"], label: label("roles", r.code) }))} />
        <div className="flex items-end">
          <Tick id="ro-all" label={t("includeEnded")} checked={all} onChange={(v) => s.set({ all: v ? "1" : null, page: null })} />
        </div>
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="roster-table">
            <THead>
              <TR>
                <TH>{t("person")}</TH>
                <TH>{t("role")}</TH>
                <TH>{t("site")}</TH>
                <TH>{t("shift")}</TH>
                <TH>{t("valid")}</TH>
                <TH>{t("qualified")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="roster-row" data-no={r.assignment_no} data-worker={r.worker?.worker_no ?? ""} data-qualified={r.qualified_today === null ? "na" : r.qualified_today ? "yes" : "no"}>
                  <TD label={t("person")}>
                    {r.worker ? <WorkerLabel w={r.worker} /> : <UserName u={r.user} />}
                    <span className="block text-xs text-muted-foreground">
                      <Code>{r.assignment_no}</Code>
                      {r.engagement_code ? <> · {r.engagement_code}</> : null}
                    </span>
                  </TD>
                  <TD label={t("role")}>{label("roles", r.role)}</TD>
                  <TD label={t("site")}>
                    <Code>{r.site_code}</Code>
                    {r.zone_codes.length ? (
                      <span className="block">
                        <Codes items={r.zone_codes} />
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("shift")}>{te(`emShift.${r.shift}`)}</TD>
                  <TD label={t("valid")}>
                    <StackedDate v={r.valid_from} projectId={project.id} />
                    {r.valid_to ? (
                      <span className="block text-xs text-muted-foreground">
                        {t("until")} <StackedDate v={r.valid_to} projectId={project.id} />
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("qualified")}>
                    <Qualified r={r} />
                  </TD>
                  <TD>
                    {caps.roster && r.active ? (
                      <Button size="sm" variant="outline" onClick={() => setEnd(r)} data-testid="roster-end">
                        {t("end")}
                      </Button>
                    ) : !r.active ? (
                      <ActiveBadge active={false} />
                    ) : null}
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
      {create ? <RosterDialog project={project} onClose={() => setCreate(false)} /> : null}
      {end ? <EndDialog r={end} onClose={() => setEnd(null)} /> : null}
    </div>
  );
}

/** EO-3: qualified today from the Phase 5 training check; coordinators and marshals need no code (null). */
function Qualified({ r }: { r: S["RosterRead"] }) {
  const t = useTranslations("emergency.roster");
  if (r.qualified_today === null) return <span className="text-xs text-muted-foreground">{t("noCode")}</span>;
  return (
    <span className="inline-flex flex-col gap-0.5">
      <Badge tone={r.qualified_today ? "success" : "danger"} data-testid="qualified">
        {r.qualified_today ? <CheckCircle2 aria-hidden /> : <XCircle aria-hidden />}
        {r.qualified_today ? t("yes") : t("no")}
        {r.qualification_code ? <Code className="ms-1 text-xs">{r.qualification_code}</Code> : null}
      </Badge>
      {r.qualification_reason ? <span className="text-xs text-muted-foreground">{r.qualification_reason}</span> : null}
    </span>
  );
}

function RosterDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("emergency.roster");
  const te = useTranslations("enums");
  const { label, items } = useEmRef();
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const [role, setRole] = useState<S["EmergencyRole"]>("first_aider");
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [user, setUser] = useState("");
  const [site, setSite] = useState("");
  const [zones, setZones] = useState<string[]>([]);
  const [shift, setShift] = useState<S["RosterShift"]>("day");
  const [from, setFrom] = useState(todayInZone());
  const [to, setTo] = useState("");
  const coordinator = role === "emergency_coordinator";
  const warden = role === "fire_warden";
  const person = coordinator ? Boolean(user || dep) : Boolean(dep);
  return (
    <StepDialog
      wide
      title={t("new")}
      description={t("newHint")}
      confirmLabel={t("assign")}
      disabled={!person || !site || !from || (warden && !zones.length)}
      testId="roster-save"
      onConfirm={async () => {
        const r = await unwrap(
          api.POST("/api/v1/projects/{project_id}/emergency-roster", {
            params: { path: { project_id: project.id } },
            body: { role, deployment_id: dep?.id ?? null, user_id: coordinator && user ? user : null, site_id: site, zone_ids: zones, shift, valid_from: from, valid_to: to || null },
          }),
        );
        await refresh();
        toast.success(r.matrix_role_added ? t("assignedMatrix", { no: r.assignment.assignment_no }) : t("assigned", { no: r.assignment.assignment_no }));
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="rf-role" label={t("role")} required>
          <Select value={role} onChange={(x) => setRole(x.target.value as S["EmergencyRole"])} data-testid="rf-role">
            {items("roles").map((r) => (
              <option key={r.code} value={r.code}>
                {label("roles", r.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="rf-shift" label={t("shift")} required>
          <Select value={shift} onChange={(x) => setShift(x.target.value as S["RosterShift"])} data-testid="rf-shift">
            {ROSTER_SHIFTS.map((x) => (
              <option key={x} value={x}>
                {te(`emShift.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      {coordinator ? (
        <FormField id="rf-user" label={t("user")} hint={t("userHint")}>
          <UserSelect projectId={project.id} value={user} onChange={(x) => setUser(x.target.value)} data-testid="rf-user" />
        </FormField>
      ) : null}
      {!coordinator || !user ? <DeploymentPicker id="rf-worker" projectId={project.id} value={dep} onChange={setDep} status={["mobilised"]} label={t("worker")} required={!coordinator} /> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="rf-site" label={t("site")} required>
          <Select value={site} onChange={(x) => (setSite(x.target.value), setZones([]))} data-testid="rf-site">
            <option value="">—</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <MultiSelect id="rf-zones" label={warden ? `${t("zones")} *` : t("zones")} options={opts.zones.filter((z) => z.siteId === site)} value={zones} onChange={setZones} testId="rf-zones" />
        <FormField id="rf-from" label={t("from")} required>
          <Input type="date" value={from} onChange={(x) => setFrom(x.target.value)} />
        </FormField>
        <FormField id="rf-to" label={t("to")}>
          <Input type="date" value={to} onChange={(x) => setTo(x.target.value)} />
        </FormField>
      </div>
      {role === "first_aider" || warden ? <p className="text-xs text-muted-foreground">{t("matrixHint")}</p> : null}
    </StepDialog>
  );
}

function EndDialog({ r, onClose }: { r: S["RosterRead"]; onClose: () => void }) {
  const t = useTranslations("emergency.roster");
  const refresh = useEmergencyRefresh();
  const [to, setTo] = useState(todayInZone());
  return (
    <StepDialog
      title={t("endTitle", { no: r.assignment_no })}
      description={t("endHint")}
      confirmLabel={t("end")}
      destructive
      disabled={!to}
      testId="roster-end-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/emergency-roster/{assignment_id}/end", { params: { path: { assignment_id: r.id } }, body: { valid_to: to } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="re-to" label={t("to")} required>
        <Input type="date" value={to} onChange={(x) => setTo(x.target.value)} />
      </FormField>
    </StepDialog>
  );
}

/* ═════════════ coverage per site, shift and day (§6.2, EO-4…EO-6) ═════════════ */

export function CoveragePage() {
  return <ProjectGate>{(p) => <Coverage project={p} />}</ProjectGate>;
}

function Coverage({ project }: { project: Project }) {
  const t = useTranslations("emergency.coverage");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const today = todayInZone();
  const from = s.get("from") ?? today;
  const to = s.get("to") ?? "";
  const site = s.get("site") ?? "";
  const shift = (s.get("shift") ?? "") as S["DrillShift"] | "";
  const q = useCoverage(project.id, { date_from: from, date_to: to || null, site_id: site || null, shift: shift || null }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const rows = q.data?.rows ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EmOrgSubNav />
      <ListToolbar>
        <DateFilter id="cv-from" label={t("from")} value={from} onChange={(v) => s.set({ from: v || null })} />
        <DateFilter id="cv-to" label={t("to")} value={to} onChange={(v) => s.set({ to: v || null })} />
        <SelectFilter id="cv-site" label={t("site")} value={site} onChange={(v) => s.set({ site: v })} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} />
        <SelectFilter id="cv-shift" label={t("shift")} value={shift} onChange={(v) => s.set({ shift: v })} options={DRILL_SHIFTS.map((x) => ({ value: x, label: te(`emShift.${x}`) }))} />
      </ListToolbar>
      <p className="mb-3 text-xs text-muted-foreground">{t("rule")}</p>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : rows.length ? (
        <Table data-testid="coverage-table">
          <THead>
            <TR>
              <TH>{t("day")}</TH>
              <TH>{t("site")}</TH>
              <TH>{t("shift")}</TH>
              <TH className="text-end">{t("headcount")}</TH>
              <TH className="text-end">{t("firstAiders")}</TH>
              <TH className="text-end">{t("wardens")}</TH>
              <TH>{t("zonesWithoutWarden")}</TH>
              <TH>{t("state")}</TH>
            </TR>
          </THead>
          <TBody>
            {rows.map((r) => (
              <TR key={`${r.site_id}-${r.day}-${r.shift}`} data-testid="coverage-row" data-site={r.site_code} data-day={r.day} data-shift={r.shift} data-state={r.state}>
                <TD label={t("day")}>
                  <StackedDate v={r.day} projectId={project.id} />
                </TD>
                <TD label={t("site")}>
                  <Code>{r.site_code}</Code>
                </TD>
                <TD label={t("shift")}>{te(`emShift.${r.shift}`)}</TD>
                <TD label={t("headcount")} className="text-end tabular-nums">
                  {r.headcount}
                </TD>
                <TD label={t("firstAiders")} className="text-end">
                  <Ratio have={r.first_aiders_counted} need={r.first_aiders_required} testId="cv-fa" />
                </TD>
                <TD label={t("wardens")} className="text-end">
                  <Ratio have={r.wardens_counted} need={r.wardens_required} testId="cv-fw" />
                </TD>
                <TD label={t("zonesWithoutWarden")}>
                  <Codes items={r.zones_without_warden} />
                  {!r.coordinator_ok ? <span className="block text-xs text-danger">{t("noCoordinator")}</span> : null}
                </TD>
                <TD label={t("state")}>
                  <CoverageBadge state={r.state} />
                  {r.rostered_not_qualified?.length ? (
                    <details className="mt-1 text-xs">
                      <summary className="cursor-pointer text-muted-foreground">{t("notQualified", { n: r.rostered_not_qualified.length })}</summary>
                      <Codes items={r.rostered_not_qualified} />
                    </details>
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

function Ratio({ have, need, testId }: { have: number; need: number; testId: string }) {
  const short = have < need;
  return (
    <bdi className={cn("ltr tabular-nums", short && "font-semibold text-danger")} data-testid={testId} data-short={short ? "yes" : "no"}>
      {have} / {need}
    </bdi>
  );
}

/* ═════════════ rescue teams (§3.7, RT-1…RT-3) ═════════════ */

export function RescueTeamsPage() {
  return <ProjectGate>{(p) => <Teams project={p} />}</ProjectGate>;
}

function Teams({ project }: { project: Project }) {
  const t = useTranslations("emergency.teams");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const q = useRescueTeams(project.id, { page_size: 100 }, { enabled: caps.view });
  const [edit, setEdit] = useState<S["TeamRead"] | "new" | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.roster ? (
            <Button onClick={() => setEdit("new")} data-testid="team-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <EmOrgSubNav />
      <PrivacyNote>{t("privacy")}</PrivacyNote>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <div className="grid gap-3 lg:grid-cols-2" data-testid="teams">
          {items.map((tm) => (
            <Card key={tm.id} className={cn("border-s-8", tm.readiness.current ? "border-s-success" : "border-s-danger")} data-testid="team-card" data-code={tm.team_code} data-current={tm.readiness.current ? "yes" : "no"}>
              <CardHeader className="pb-2">
                <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                  <Code>{tm.team_code}</Code>
                  <span className="text-sm font-normal">{te(`emTeamType.${tm.team_type}`)}</span>
                  <Codes items={tm.site_ids.map((id) => opts.sites.find((x) => x.value === id)?.code ?? "")} />
                  {tm.status !== "active" ? <ActiveBadge active={false} /> : null}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                <div className={cn("rounded-md border-2 px-3 py-2", tm.readiness.current ? "border-success/40 bg-success-bg text-success" : "border-danger/50 bg-danger-bg text-danger")} data-testid="team-readiness">
                  <p className="flex items-center gap-2 font-semibold">
                    {tm.readiness.current ? <CheckCircle2 aria-hidden className="size-5" /> : <XCircle aria-hidden className="size-5" />}
                    {tm.readiness.current ? t("current") : t("notCurrent")}
                  </p>
                  <p className="text-xs">
                    {t("lastDrill")} <StackedDate v={tm.readiness.last_drill_on} projectId={project.id} />
                    {tm.readiness.current_until ? (
                      <>
                        {" · "}
                        {t("until")} <StackedDate v={tm.readiness.current_until} projectId={project.id} />
                      </>
                    ) : null}
                  </p>
                  {tm.readiness.reasons.length ? (
                    <ul className="mt-1 list-inside list-disc text-xs">
                      {tm.readiness.reasons.map((r) => (
                        <li key={r} data-testid="team-reason" data-code={r}>
                          {te(`emTeamReason.${r}`)}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
                <ul className="flex flex-col divide-y rounded-md border" data-testid="team-members">
                  {tm.members.map((m) => (
                    <li key={m.deployment_id} className="flex flex-wrap items-center gap-2 px-3 py-1.5">
                      {m.lead ? <Crown aria-label={t("lead")} className="size-4 text-warning" /> : null}
                      {m.worker ? <WorkerLabel w={m.worker} /> : "—"}
                      <span className="ms-auto flex gap-1">
                        <Badge tone={m.qualified ? "success" : "danger"}>{m.qualified ? t("qualified") : t("notQualified")}</Badge>
                        {m.first_aider ? (
                          <Badge tone="info">
                            <HeartPulse aria-hidden />
                            {t("firstAider")}
                          </Badge>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="text-xs">
                  {t("equipment")} <Codes items={[...tm.equipment_nos, ...tm.asset_tags]} />
                </p>
                {caps.roster ? (
                  <Button size="sm" variant="outline" className="w-fit" onClick={() => setEdit(tm)} data-testid="team-edit">
                    {t("edit")}
                  </Button>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {edit ? <TeamDialog project={project} team={edit === "new" ? null : edit} onClose={() => setEdit(null)} /> : null}
    </div>
  );
}

function TeamDialog({ project, team, onClose }: { project: Project; team: S["TeamRead"] | null; onClose: () => void }) {
  const t = useTranslations("emergency.teams");
  const te = useTranslations("enums");
  const locale = useLocale();
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const [code, setCode] = useState(team?.team_code ?? "");
  const [type, setType] = useState<S["TeamType"]>(team?.team_type ?? "confined_space");
  const [sites, setSites] = useState<string[]>(team?.site_ids ?? []);
  const leadM = team?.members.find((m) => m.lead);
  const asDep = (m: S["TeamMember"]): S["DeploymentRead"] => ({ id: m.deployment_id, worker_no: m.worker?.worker_no ?? "", full_name_en: m.worker?.full_name_en ?? "", full_name_ar: m.worker?.full_name_ar ?? null }) as unknown as S["DeploymentRead"];
  const [lead, setLead] = useState<S["DeploymentRead"] | null>(leadM ? asDep(leadM) : null);
  const [members, setMembers] = useState<S["DeploymentRead"][]>((team?.members ?? []).filter((m) => !m.lead).map(asDep));
  const [pick, setPick] = useState<S["DeploymentRead"] | null>(null);
  const [equip, setEquip] = useState<string[]>(team?.equipment_item_ids ?? []);
  const [assets, setAssets] = useState<string[]>(team?.asset_ids ?? []);
  const [active, setActive] = useState(team ? team.status === "active" : true);
  const tw = useEquipmentList({ project_id: project.id, category: ["tripod_winch"], page_size: 100 });
  const kits = useEmergencyAssets(project.id, { asset_type: ["rescue_kit_height"], page_size: 100 });
  return (
    <StepDialog
      wide
      title={team ? t("editTitle", { code: team.team_code }) : t("new")}
      description={t("newHint")}
      confirmLabel={t("save")}
      disabled={!code || !sites.length || !lead}
      testId="team-save"
      onConfirm={async () => {
        const body = { site_ids: sites, lead_deployment_id: lead?.id ?? "", member_deployment_ids: members.map((m) => m.id), equipment_item_ids: equip, asset_ids: assets };
        if (team) await unwrap(api.PATCH("/api/v1/rescue-teams/{team_id}", { params: { path: { team_id: team.id } }, body: { ...body, status: active ? "active" : "inactive" } }));
        else await unwrap(api.POST("/api/v1/projects/{project_id}/rescue-teams", { params: { path: { project_id: project.id } }, body: { ...body, team_code: code.trim(), team_type: type } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="tm-code" label={t("code")} required>
          <Input className="ltr" disabled={Boolean(team)} value={code} onChange={(x) => setCode(x.target.value.toUpperCase())} maxLength={16} data-testid="tm-code" />
        </FormField>
        <FormField id="tm-type" label={t("type")} required>
          <Select disabled={Boolean(team)} value={type} onChange={(x) => setType(x.target.value as S["TeamType"])} data-testid="tm-type">
            {TEAM_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`emTeamType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <MultiSelect id="tm-sites" label={t("sites")} options={opts.sites} value={sites} onChange={setSites} testId="tm-sites" />
        {team ? <Tick id="tm-active" label={t("active")} checked={active} onChange={setActive} /> : null}
      </div>
      <DeploymentPicker id="tm-lead" projectId={project.id} value={lead} onChange={setLead} status={["mobilised"]} label={t("lead")} required />
      <div className="flex flex-col gap-2">
        <DeploymentPicker id="tm-member" projectId={project.id} value={pick} onChange={setPick} status={["mobilised"]} label={t("addMember")} />
        <Button
          size="sm"
          variant="outline"
          className="w-fit"
          disabled={!pick || members.some((m) => m.id === pick.id) || pick.id === lead?.id}
          onClick={() => {
            if (pick) setMembers([...members, pick]);
            setPick(null);
          }}
          data-testid="tm-member-add"
        >
          <Plus aria-hidden />
          {t("addMember")}
        </Button>
        {members.length ? (
          <ul className="flex flex-wrap gap-2" data-testid="tm-members">
            {members.map((m) => (
              <li key={m.id}>
                <Badge tone="neutral" className="gap-1">
                  <Code>{m.worker_no}</Code> {locale === "ar" && m.full_name_ar ? m.full_name_ar : m.full_name_en}
                  <button type="button" aria-label={t("removeMember")} onClick={() => setMembers(members.filter((x) => x.id !== m.id))} className="ms-1">
                    <X aria-hidden className="size-3.5" />
                  </button>
                </Badge>
              </li>
            ))}
          </ul>
        ) : null}
        <p className="text-xs text-muted-foreground">{t("minHint")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <MultiSelect id="tm-equip" label={t("tripods")} options={(tw.data?.items ?? []).map((e) => ({ value: e.id, label: e.equipment_no }))} value={equip} onChange={setEquip} />
        <MultiSelect id="tm-kits" label={t("kits")} options={(kits.data?.items ?? []).map((a) => ({ value: a.id, label: a.asset_tag }))} value={assets} onChange={setAssets} />
      </div>
    </StepDialog>
  );
}
