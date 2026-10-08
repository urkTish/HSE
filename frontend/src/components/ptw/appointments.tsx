"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
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
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { DaysLeft, DeploymentPicker, StepDialog } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { pk, useAppointment, useAppointments } from "@/lib/api/ptw";
import { todayInZone } from "@/lib/datetime";
import { can, canWrite } from "@/lib/permissions";
import { APPOINTMENT_FUNCTIONS, APPOINTMENT_STATUSES, PERMIT_TYPES } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { PermitNo, WorkerRefLabel, userLabel } from "./common";

type S = Schemas;
type Appt = S["AppointmentRead"];
const PAGE_SIZE = 50;

const DISCIPLINES_BY_FUNCTION: Partial<Record<S["AppointmentFunction"], S["AppointmentDiscipline"][]>> = {
  isolation_authority: ["electrical_lv", "electrical_hv", "mechanical_process"],
  authorised_person: ["electrical_lv", "electrical_hv", "lifting_appointed_person", "lift_supervisor", "excavation_competent_person", "fall_protection_competent_person", "radiation_protection_officer", "cse_rescue_lead"],
};
const USER_ONLY: S["AppointmentFunction"][] = ["issuer", "area_authority", "isolation_authority"];

export function AppointmentHolder({ a }: { a: Pick<Appt, "holder_user" | "holder_worker"> }) {
  const locale = useLocale();
  if (a.holder_user) return <span>{userLabel(a.holder_user, locale)}</span>;
  return <WorkerRefLabel w={a.holder_worker} />;
}

/* ───────────── list ───────────── */

export function AppointmentListPage() {
  return <ProjectGate>{(p) => <AppointmentList project={p} />}</ProjectGate>;
}

function AppointmentList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("ptwAppointments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const opts = useProjectOptions(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const fn = s.getAll("function") as S["AppointmentFunction"][];
  const status = s.getAll("status") as S["AppointmentStatus"][];
  const [create, setCreate] = useState(false);
  const q = useAppointments(project.id, {
    function: fn.length ? fn : null,
    status: status.length ? status : null,
    site_id: s.get("site_id") || null,
    expiring_within_days: s.getInt("expiring", 0) || null,
    q: s.get("q") || null,
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
          canWrite(me, "ptw_appointment.manage", project.id) ? (
            <Button onClick={() => setCreate(true)} data-testid="new-appointment">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <ListToolbar actions={can(me, "export.ptw", project.id) ? <ExportButtons dataset="ptw_appointments" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="ap-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="ap-fn" label={t("function")} options={APPOINTMENT_FUNCTIONS.map((x) => ({ value: x, label: te(`appointmentFunction.${x}`) }))} value={fn} onChange={(v) => s.set({ function: v })} />
        <MultiSelect id="ap-status" label={tc("status")} options={APPOINTMENT_STATUSES.map((x) => ({ value: x, label: te(`appointmentStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="ap-site" label={tc("site")} value={s.get("site_id") ?? ""} onChange={(v) => s.set({ site_id: v })} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter
          id="ap-exp"
          label={t("expiring")}
          value={s.get("expiring") ?? ""}
          onChange={(v) => s.set({ expiring: v })}
          options={[
            { value: "14", label: t("withinDays", { n: 14 }) },
            { value: "30", label: t("withinDays", { n: 30 }) },
          ]}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="appointments-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("holder")}</TH>
                <TH>{t("function")}</TH>
                <TH>{t("types")}</TH>
                <TH>{t("scope")}</TH>
                <TH>{t("valid")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="appointment-row" data-no={a.appointment_no}>
                  <TD label={t("no")}>
                    <Link href={`/ptw-appointments/${a.id}`} className="ltr font-medium text-primary hover:underline">
                      {a.appointment_no}
                    </Link>
                  </TD>
                  <TD label={t("holder")}>
                    <AppointmentHolder a={a} />
                  </TD>
                  <TD label={t("function")}>
                    {te(`appointmentFunction.${a.function}`)}
                    {a.discipline ? <span className="block text-xs text-muted-foreground">{te(`appointmentDiscipline.${a.discipline}`)}</span> : null}
                  </TD>
                  <TD label={t("types")}>
                    <span className="text-xs">{a.permit_types.length === PERMIT_TYPES.length ? t("allTypes") : a.permit_types.map((x) => te(`permitType.${x}`)).join(" · ")}</span>
                  </TD>
                  <TD label={t("scope")}>
                    <bdi className="ltr text-xs">{[...a.sites.map((x) => x.code), ...a.zones.map((z) => z.code)].join(", ")}</bdi>
                  </TD>
                  <TD label={t("valid")}>
                    <span className="text-sm">
                      {date(a.valid_from)} – {date(a.valid_to)}
                    </span>{" "}
                    {a.status === "active" ? <DaysLeft days={a.days_left} /> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={a.status} label={te(`appointmentStatus.${a.status}`)} />
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
      {create ? <AppointmentDialog project={project} onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

/* ───────────── create / edit ───────────── */

function AppointmentDialog({ project, appt, onClose }: { project: S["ProjectRead"]; appt?: Appt; onClose: () => void }) {
  const t = useTranslations("ptwAppointments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const router = useRouter();
  const opts = useProjectOptions(project.id);
  const today = todayInZone();
  const [fn, setFn] = useState<S["AppointmentFunction"]>(appt?.function ?? "area_authority");
  const [disc, setDisc] = useState<S["AppointmentDiscipline"] | "">(appt?.discipline ?? "");
  const [holderKind, setHolderKind] = useState<"user" | "worker">(appt?.holder_worker ? "worker" : "user");
  const [userId, setUserId] = useState(appt?.holder_user?.id ?? "");
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [types, setTypes] = useState<S["PermitType"][]>(appt?.permit_types ?? []);
  const [sites, setSites] = useState<string[]>(appt?.sites.map((x) => x.id) ?? []);
  const [zones, setZones] = useState<string[]>(appt?.zones.map((x) => x.id) ?? []);
  const [basis, setBasis] = useState(appt?.basis ?? "");
  const [from, setFrom] = useState(appt?.valid_from ?? today);
  const [to, setTo] = useState(appt?.valid_to ?? "");
  const disciplines = DISCIPLINES_BY_FUNCTION[fn] ?? [];
  const userOnly = USER_ONLY.includes(fn);
  const kind = userOnly ? "user" : holderKind;
  // Issuer appointments are HSE Manager only (capability 100 note): officers do not see the option.
  const functions = APPOINTMENT_FUNCTIONS.filter((f) => f !== "issuer" || me.is_hse_manager || appt?.function === "issuer");
  const valid = types.length > 0 && sites.length > 0 && basis.trim().length > 0 && Boolean(to) && (appt || (kind === "user" ? Boolean(userId) : Boolean(dep))) && (!disciplines.length || Boolean(disc));
  async function save() {
    if (appt) {
      await unwrap(api.PATCH("/api/v1/ptw-appointments/{appointment_id}", { params: { path: { appointment_id: appt.id } }, body: { permit_types: types, site_ids: sites, zone_ids: zones, basis, valid_to: to } }));
      await qc.invalidateQueries({ queryKey: ["ptw-appointment"] });
      await qc.invalidateQueries({ queryKey: ["ptw-appointments"] });
      toast.success(tc("saved"));
      return;
    }
    const a = await unwrap(
      api.POST("/api/v1/projects/{project_id}/ptw-appointments", {
        params: { path: { project_id: project.id } },
        body: {
          function: fn,
          discipline: disc || null,
          holder_user_id: kind === "user" ? userId : null,
          holder_worker_id: kind === "worker" ? (dep?.worker_id ?? null) : null,
          permit_types: types,
          site_ids: sites,
          zone_ids: zones,
          basis,
          valid_from: from,
          valid_to: to,
        },
      }),
    );
    await qc.invalidateQueries({ queryKey: ["ptw-appointments"] });
    toast.success(t("created", { no: a.appointment_no }));
    router.push(`/ptw-appointments/${a.id}`);
  }
  return (
    <StepDialog title={appt ? t("edit") : t("new")} description={t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-appointment">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ap-function" label={t("function")} required>
          <Select value={fn} disabled={Boolean(appt)} onChange={(e) => { setFn(e.target.value as S["AppointmentFunction"]); setDisc(""); }} data-testid="ap-function">
            {functions.map((x) => (
              <option key={x} value={x}>
                {te(`appointmentFunction.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {disciplines.length ? (
          <FormField id="ap-disc" label={t("discipline")} required>
            <Select value={disc} disabled={Boolean(appt)} onChange={(e) => setDisc(e.target.value as S["AppointmentDiscipline"])} data-testid="ap-discipline">
              <option value="">{tc("select")}</option>
              {disciplines.map((x) => (
                <option key={x} value={x}>
                  {te(`appointmentDiscipline.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
      </div>
      {!appt ? (
        <>
          {!userOnly ? (
            <fieldset className="flex flex-wrap gap-4 text-sm">
              <legend className="mb-1 text-sm font-medium">{t("holderKind")}</legend>
              <label className="flex min-h-touch items-center gap-2">
                <input type="radio" checked={holderKind === "user"} onChange={() => setHolderKind("user")} />
                {t("holderUser")}
              </label>
              <label className="flex min-h-touch items-center gap-2">
                <input type="radio" checked={holderKind === "worker"} onChange={() => setHolderKind("worker")} data-testid="ap-holder-worker" />
                {t("holderWorker")}
              </label>
            </fieldset>
          ) : null}
          {kind === "user" ? (
            <FormField id="ap-user" label={t("holder")} required hint={userOnly ? t("userOnlyHint") : undefined}>
              <UserSelect projectId={project.id} value={userId} onChange={(e) => setUserId(e.target.value)} data-testid="ap-user" />
            </FormField>
          ) : (
            <DeploymentPicker id="ap-worker" projectId={project.id} value={dep} onChange={setDep} label={t("holder")} required status={["mobilised"]} />
          )}
        </>
      ) : null}
      <MultiSelect id="ap-types" label={t("types")} options={PERMIT_TYPES.map((x) => ({ value: x, label: te(`permitType.${x}`) }))} value={types} onChange={setTypes} testId="ap-types" />
      <div className="grid gap-3 sm:grid-cols-2">
        <MultiSelect id="ap-sites" label={tc("site")} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} value={sites} onChange={setSites} testId="ap-sites" />
        <MultiSelect id="ap-zones" label={t("zonesOptional")} options={opts.zones.filter((z) => sites.includes(z.siteId)).map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={setZones} />
      </div>
      <FormField id="ap-basis" label={t("basis")} required hint={t("basisHint")}>
        <Textarea value={basis} onChange={(e) => setBasis(e.target.value)} maxLength={300} data-testid="ap-basis" />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ap-from" label={t("validFrom")} required>
          <Input type="date" className="ltr" disabled={Boolean(appt)} value={from} onChange={(e) => setFrom(e.target.value)} />
        </FormField>
        <FormField id="ap-to" label={t("validTo")} required hint={t("validToHint")}>
          <Input type="date" className="ltr" value={to} onChange={(e) => setTo(e.target.value)} data-testid="ap-to" />
        </FormField>
      </div>
    </StepDialog>
  );
}

/* ───────────── detail ───────────── */

export function AppointmentDetail({ id }: { id: string }) {
  const q = useAppointment(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => <AppointmentView project={p} a={q.data} />}</ProjectById>;
}

function AppointmentView({ project, a }: { project: S["ProjectRead"]; a: Appt }) {
  const t = useTranslations("ptwAppointments");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const locale = useLocale();
  const { date } = useFormatters(project.id);
  const [step, setStep] = useState<"suspend" | "reinstate" | "revoke" | "edit" | null>(null);
  const [reason, setReason] = useState("");
  const manage = canWrite(me, "ptw_appointment.manage", project.id) && (a.function !== "issuer" || me.is_hse_manager);
  async function transition(to: S["AppointmentStatus"]) {
    const u = await unwrap(api.POST("/api/v1/ptw-appointments/{appointment_id}/transitions", { params: { path: { appointment_id: a.id } }, body: { to_status: to, reason: reason || null } }));
    qc.setQueryData(pk.appointment(a.id), u);
    await qc.invalidateQueries({ queryKey: ["ptw-appointments"] });
    toast.success(te(`appointmentStatus.${to}`));
  }
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/ptw-appointments" }, { label: a.appointment_no }]} />
        <PageHeader
          title={a.appointment_no}
          description={`${te(`appointmentFunction.${a.function}`)}${a.discipline ? ` · ${te(`appointmentDiscipline.${a.discipline}`)}` : ""}`}
          actions={
            <>
              <span data-testid="appointment-status" data-status={a.status}>
                <StatusBadge status={a.status} label={te(`appointmentStatus.${a.status}`)} />
              </span>
              {manage && (a.status === "active" || a.status === "suspended") ? (
                <Button variant="outline" onClick={() => setStep("edit")} data-testid="edit-appointment">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              {manage && a.status === "active" ? (
                <Button variant="outline" onClick={() => setStep("suspend")} data-testid="suspend-appointment">
                  {t("suspend")}
                </Button>
              ) : null}
              {manage && a.status === "suspended" ? (
                <Button onClick={() => setStep("reinstate")} data-testid="reinstate-appointment">
                  {t("reinstate")}
                </Button>
              ) : null}
              {manage && (a.status === "active" || a.status === "suspended") ? (
                <Button variant="destructive" onClick={() => setStep("revoke")} data-testid="revoke-appointment">
                  {t("revoke")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      <ApiWarnings warnings={a.warnings} />
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("holder")}>
              <AppointmentHolder a={a} />
            </FieldItem>
            <FieldItem label={t("types")}>{a.permit_types.map((x) => te(`permitType.${x}`)).join(" · ")}</FieldItem>
            <FieldItem label={tc("site")}>{a.sites.map((x) => x.code).join(", ")}</FieldItem>
            <FieldItem label={t("zonesOptional")}>{a.zones.length ? a.zones.map((x) => x.code).join(", ") : t("allZones")}</FieldItem>
            <FieldItem label={t("valid")}>
              {date(a.valid_from)} – {date(a.valid_to)} {a.status === "active" ? <DaysLeft days={a.days_left} /> : null}
            </FieldItem>
            <FieldItem label={t("appointedBy")}>{userLabel(a.appointed_by, locale)}</FieldItem>
            <FieldItem label={t("basis")} wide>
              {a.basis}
            </FieldItem>
            {a.status_reason ? (
              <FieldItem label={tc("reason")} wide>
                {a.status_reason}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("livePermits", { n: a.live_permits.length })}</CardTitle>
        </CardHeader>
        <CardContent>
          {a.live_permits.length ? (
            <ul className="flex flex-wrap gap-3" data-testid="appointment-permits">
              {a.live_permits.map((p) => (
                <li key={p.id} className="text-sm">
                  <PermitNo p={p} /> <span className="text-xs text-muted-foreground">{te(`permitStatus.${p.status}`)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noLivePermits")}</p>
          )}
        </CardContent>
      </Card>
      <HistoryPanel entityType="ptw_appointment" entityId={a.id} />
      {step === "edit" ? <AppointmentDialog project={project} appt={a} onClose={() => setStep(null)} /> : null}
      {step && step !== "edit" ? (
        <StepDialog
          title={t(`${step}Title`)}
          description={step === "reinstate" ? undefined : t("reevaluateHint")}
          confirmLabel={t(step)}
          destructive={step !== "reinstate"}
          disabled={step !== "reinstate" && reason.trim().length < 5}
          onClose={() => {
            setStep(null);
            setReason("");
          }}
          onConfirm={() => transition(step === "suspend" ? "suspended" : step === "revoke" ? "revoked" : "active")}
          testId="appointment-confirm"
        >
          {step !== "reinstate" ? (
            <FormField id="ap-reason" label={tc("reason")} required>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="ap-reason" />
            </FormField>
          ) : null}
        </StepDialog>
      ) : null}
    </div>
  );
}
