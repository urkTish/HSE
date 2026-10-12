"use client";
import { Ban, CheckCircle2, Pause, Play, Plus, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
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
import { Code, DeploymentPicker, StepDialog } from "@/components/access/common";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { RecordActions } from "@/components/common/record-actions";
import { StackedDate } from "@/components/medical/common";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { LICENCE_CLASSES, LICENCE_ISSUERS } from "@/lib/access-enums";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAuthPrefill, useDriverAuth, useDriverAuths, useSiteVehicles, useSvRefresh } from "@/lib/api/site-vehicles";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { AUTH_STATUSES, AuthStatusBadge, DriverText, GROUPS, PrototypeBadge, SvGate, SvSubNav, useSvCaps, useSvLabels } from "./common";

type S = Schemas;
type Auth = S["SiteVehAuthRead"];
const PAGE_SIZE = 50;
const ROAD: readonly S["SiteVehDriverGroup"][] = ["light", "bus", "heavy"];

/* ═════════════ register (§3.2, §4.2) ═════════════ */

export function AuthorisationsPage() {
  return <SvGate>{(p) => <Register project={p} />}</SvGate>;
}

function Register({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.auth");
  const tc = useTranslations("common");
  const l = useSvLabels();
  const caps = useSvCaps(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["SiteVehAuthStatus"] | "";
  const group = (s.get("group") ?? "") as S["SiteVehDriverGroup"] | "";
  const eng = s.get("engagement_id") ?? "";
  const expiring = s.get("expiring_within_days") ?? "";
  const q = useDriverAuths(
    project.id,
    {
      status: status ? [status] : null,
      group: group ? [group] : null,
      engagement_id: eng ? [eng] : null,
      expiring_within_days: expiring ? Number(expiring) : null,
      page,
      page_size: PAGE_SIZE,
    },
    { enabled: caps.view && !caps.aggregatesOnly },
  );
  const items = q.data?.items ?? [];
  if (caps.aggregatesOnly) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader
        title={t("title")}
        badge={<PrototypeBadge />}
        description={t("subtitle")}
        actions={
          caps.auth ? (
            <Button asChild>
              <Link href="/site-vehicles/authorisations/new" data-testid="sv-new-auth">
                <Plus aria-hidden />
                {caps.rep ? t("propose") : t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <SvSubNav projectId={project.id} />
      <ListToolbar>
        <SelectFilter id="da-status" label={t("status")} value={status} onChange={(v) => s.set({ status: v })} options={AUTH_STATUSES.map((x) => ({ value: x, label: l.authStatus(x) }))} />
        <SelectFilter id="da-group" label={t("groups")} value={group} onChange={(v) => s.set({ group: v })} options={GROUPS.map((g) => ({ value: g, label: l.group(g) }))} />
        <SelectFilter id="da-eng" label={tc("contractor")} value={eng} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements} allLabel={tc("anyContractor")} />
        <SelectFilter
          id="da-expiring"
          label={t("expiring")}
          value={expiring}
          onChange={(v) => s.set({ expiring_within_days: v })}
          options={[
            { value: "30", label: t("withinDays", { n: 30 }) },
            { value: "7", label: t("withinDays", { n: 7 }) },
          ]}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table compact data-testid="sv-auths">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("driver")}</TH>
                <TH>{t("groups")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("validUntil")}</TH>
                <TH>{t("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="sv-auth-row" data-no={a.auth_no} data-status={a.status} data-redacted={a.redacted}>
                  <TD label={t("no")}>
                    <Link href={`/site-vehicles/authorisations/${a.id}`} className="ltr font-medium whitespace-nowrap text-primary hover:underline">
                      {a.auth_no}
                    </Link>
                  </TD>
                  <TD label={t("driver")} data-full="" className="max-md:order-2">
                    <DriverText w={a.worker} />
                  </TD>
                  <TD label={t("groups")} className="max-md:order-3">{l.groups(a.groups).join(" · ")}</TD>
                  <TD label={tc("contractor")} className="max-md:order-3">{a.engagement ? <Code>{a.engagement.short_code}</Code> : "—"}</TD>
                  <TD label={t("validUntil")} data-keep-label="" className="max-md:order-4 max-md:text-xs">
                    {a.redacted ? <span className="text-xs text-muted-foreground">{t("statusOnly")}</span> : <StackedDate v={a.effective_valid_until} projectId={project.id} className="max-md:inline-flex max-md:flex-row max-md:gap-1" />}
                    {!a.redacted && a.limiting_factor && a.limiting_factor !== "own_validity" ? <span className="block text-xs text-muted-foreground">{l.limiting(a.limiting_factor)}</span> : null}
                  </TD>
                  <TD label={t("status")} className="max-md:order-1 max-md:ms-auto">
                    <AuthStatusBadge status={a.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}

/* ═════════════ create with ADP prefill (DA-1, DA-2) ═════════════ */

export function AuthorisationNewPage() {
  return <SvGate>{(p) => <AuthForm project={p} />}</SvGate>;
}

function AuthForm({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sv.auth");
  const tn = useTranslations("sv.nav");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const l = useSvLabels();
  const router = useRouter();
  const refresh = useSvRefresh();
  const warn = useWarningToasts();
  const caps = useSvCaps(project.id);
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [groups, setGroups] = useState<S["SiteVehDriverGroup"][]>([]);
  const [plantIds, setPlantIds] = useState<string[]>([]);
  const [f, setF] = useState({ licence_issuer: "ksa", licence_class: "", licence_expiry: "", assessment_date: "", assessor: "", issued_on: "", own_valid_until: "" });
  const [prefilled, setPrefilled] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const workerId = dep?.worker_id ?? "";
  const prefill = useAuthPrefill(project.id, workerId);
  const plant = useSiteVehicles(project.id, { driver_group: ["plant"], page_size: 200 }, { enabled: groups.includes("plant") });
  const road = groups.some((g) => ROAD.includes(g));

  // Prefill the licence from the worker's airside driving permit (ADP), once per worker (state adjusted while rendering).
  const pf = prefill.data;
  if (pf && prefilled !== pf.worker_id) {
    setPrefilled(pf.worker_id);
    if (pf.licence_class || pf.licence_expiry || pf.licence_issuer)
      setF((x) => ({ ...x, licence_issuer: pf.licence_issuer ?? x.licence_issuer, licence_class: pf.licence_class ?? x.licence_class, licence_expiry: pf.licence_expiry ?? x.licence_expiry }));
  }

  async function save() {
    const e: Record<string, string> = {};
    if (!workerId) e.worker = tv("required");
    if (!groups.length) e.groups = tv("required");
    if (!f.assessment_date) e.assessment_date = tv("required");
    if (f.assessor.trim().length < 2) e.assessor = tv("required");
    if (!f.issued_on) e.issued_on = tv("required");
    if (road && !f.licence_issuer) e.licence_issuer = tv("required");
    if (road && !f.licence_class) e.licence_class = tv("required");
    if (road && !f.licence_expiry) e.licence_expiry = tv("required");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    const body: S["SiteVehAuthCreate"] = {
      worker_id: workerId,
      groups,
      licence_issuer: road ? ((f.licence_issuer || null) as S["LicenceIssuer"] | null) : null,
      licence_class: road ? ((f.licence_class || null) as S["LicenceClass"] | null) : null,
      licence_expiry: road ? f.licence_expiry || null : null,
      assessment_date: f.assessment_date,
      assessor: f.assessor.trim(),
      issued_on: f.issued_on,
      own_valid_until: f.own_valid_until || null,
      plant_vehicle_ids: groups.includes("plant") ? plantIds : [],
    };
    try {
      const a = await unwrap(api.POST("/api/v1/projects/{project_id}/driver-authorisations", { params: { path: { project_id: project.id } }, body }));
      await refresh();
      warn(a.warnings);
      toast.success(t("created", { no: a.auth_no }));
      router.push(`/site-vehicles/authorisations/${a.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  if (!caps.auth) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const p = prefill.data;
  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      data-testid="sv-auth-form"
    >
      <div>
        <Breadcrumbs items={[{ label: tn("authorisations"), href: "/site-vehicles/authorisations" }, { label: caps.rep ? t("propose") : t("new") }]} />
        <PageHeader title={caps.rep ? t("propose") : t("new")} badge={<PrototypeBadge />} description={caps.rep ? t("proposeIntro") : t("intro")} />
      </div>
      <MutationError error={error} />
      <FormSection title={t("driverSection")}>
        <div className="sm:col-span-2">
          <DeploymentPicker id="da-worker" projectId={project.id} value={dep} onChange={setDep} status={["mobilised"]} label={t("driver")} required error={errors.worker} />
        </div>
        {p?.live_authorisation_no ? (
          <Alert tone="warning" className="sm:col-span-2" data-testid="da-live">
            {t("liveExists", { no: p.live_authorisation_no })}
          </Alert>
        ) : null}
        <div className="sm:col-span-2">
          <CheckboxGroup id="da-groups" legend={t("groups")} options={GROUPS.map((g) => ({ value: g, label: l.group(g) }))} value={groups} onChange={setGroups} required error={errors.groups} hint={t("groupsHint")} />
        </div>
        {groups.includes("plant") ? (
          <div className="sm:col-span-2">
            <CheckboxGroup
              id="da-plant"
              legend={t("plantVehicles")}
              options={(plant.data?.items ?? []).map((v) => ({ value: v.id, label: `${v.vehicle_no} · ${v.make_model}${v.phase4 ? ` · ${v.phase4.equipment_no}` : ""}` }))}
              value={plantIds}
              onChange={setPlantIds}
              hint={t("plantHint")}
              columns={1}
            />
          </div>
        ) : null}
      </FormSection>
      {road ? (
        <FormSection title={t("licenceSection")} description={p?.adp_no ? t("prefilledFrom", { adp: p.adp_no }) : t("licenceHint")}>
          <FormField id="da-issuer" label={t("licenceIssuer")} required error={errors.licence_issuer}>
            <Select value={f.licence_issuer} onChange={set("licence_issuer")} data-testid="da-issuer">
              <option value="">{tc("select")}</option>
              {LICENCE_ISSUERS.map((x) => (
                <option key={x} value={x}>
                  {te(`licenceIssuer.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="da-class" label={t("licenceClass")} required error={errors.licence_class}>
            <Select value={f.licence_class} onChange={set("licence_class")} data-testid="da-class">
              <option value="">{tc("select")}</option>
              {LICENCE_CLASSES.map((x) => (
                <option key={x} value={x}>
                  {te(`licenceClass.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="da-expiry" label={t("licenceExpiry")} required error={errors.licence_expiry}>
            <Input type="date" className="ltr" value={f.licence_expiry} onChange={set("licence_expiry")} data-testid="da-expiry" />
          </FormField>
          <p className="self-end text-xs text-muted-foreground sm:col-span-2">{t("noLicenceNo")}</p>
        </FormSection>
      ) : null}
      <FormSection title={t("assessmentSection")}>
        <FormField id="da-assess" label={t("assessmentDate")} required error={errors.assessment_date} hint={t("assessmentHint")}>
          <Input type="date" className="ltr" value={f.assessment_date} onChange={set("assessment_date")} data-testid="da-assess" />
        </FormField>
        <FormField id="da-assessor" label={t("assessor")} required error={errors.assessor}>
          <Input maxLength={120} value={f.assessor} onChange={set("assessor")} data-testid="da-assessor" />
        </FormField>
        <FormField id="da-issued" label={t("issuedOn")} required error={errors.issued_on}>
          <Input type="date" className="ltr" value={f.issued_on} onChange={set("issued_on")} data-testid="da-issued" />
        </FormField>
        <FormField id="da-own" label={t("ownValidUntil")} hint={t("ownValidHint")}>
          <Input type="date" className="ltr" value={f.own_valid_until} onChange={set("own_valid_until")} data-testid="da-own" />
        </FormField>
      </FormSection>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy} data-testid="da-save">
          {busy ? tc("saving") : t("saveDraft")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.push("/site-vehicles/authorisations")}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

/* ═════════════ one authorisation: hooks, effective validity, transitions ═════════════ */

export function AuthorisationDetailPage({ id }: { id: string }) {
  return <SvGate>{(p) => <Detail project={p} id={id} />}</SvGate>;
}

type Move = "active" | "suspended" | "reinstate" | "revoked" | null;

function Detail({ project, id }: { project: S["ProjectRead"]; id: string }) {
  const t = useTranslations("sv.auth");
  const tn = useTranslations("sv.nav");
  const te = useTranslations("enums");
  const l = useSvLabels();
  const caps = useSvCaps(project.id);
  const q = useDriverAuth(id);
  const { date, dateTime } = useFormatters(project.id);
  const [move, setMove] = useState<Move>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const a = q.data;
  const decide = caps.auth && !caps.rep;
  const final = a.status === "revoked" || a.status === "expired";
  return (
    <div className="flex flex-col gap-6" data-testid="sv-auth-detail" data-status={a.status}>
      <div>
        <Breadcrumbs items={[{ label: tn("authorisations"), href: "/site-vehicles/authorisations" }, { label: a.auth_no }]} />
        <PageHeader
          title={<bdi className="ltr">{a.auth_no}</bdi>}
          badge={
            <>
              <AuthStatusBadge status={a.status} />
              <PrototypeBadge />
            </>
          }
          description={l.groups(a.groups).join(" · ")}
          actions={
            decide ? (
              <>
                {a.status === "draft" ? (
                  <Button onClick={() => setMove("active")} data-testid="da-activate">
                    <ShieldCheck aria-hidden />
                    {t("activate")}
                  </Button>
                ) : null}
                {a.status === "active" ? (
                  <Button variant="outline" onClick={() => setMove("suspended")} data-testid="da-suspend">
                    <Pause aria-hidden />
                    {t("suspend")}
                  </Button>
                ) : null}
                {a.status === "suspended" ? (
                  <Button onClick={() => setMove("reinstate")} data-testid="da-reinstate">
                    <Play aria-hidden />
                    {t("reinstate")}
                  </Button>
                ) : null}
              </>
            ) : null
          }
        />
      </div>
      {a.status === "draft" && caps.rep ? <Alert tone="info">{t("proposedHint")}</Alert> : null}
      {a.status_reason ? (
        <Alert tone={a.status === "active" ? "info" : "warning"} data-testid="da-reason">
          {t("statusReason")} <span dir="auto">{a.status_reason}</span>
        </Alert>
      ) : null}
      <ApiWarnings warnings={a.warnings} />
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("driver")}>
              <DriverText w={a.worker} />
            </FieldItem>
            <FieldItem label={t("contractor")}>{a.engagement ? <Code>{a.engagement.short_code}</Code> : "—"}</FieldItem>
            <FieldItem label={t("groups")}>{l.groups(a.groups).join(" · ")}</FieldItem>
            <FieldItem label={t("issuedOn")}>{date(a.issued_on)}</FieldItem>
            {a.redacted ? null : (
              <>
                <FieldItem label={t("ownValidUntil")}>{date(a.own_valid_until)}</FieldItem>
                <FieldItem label={t("effectiveValidUntil")}>
                  <span data-testid="da-effective">{date(a.effective_valid_until)}</span>
                  {a.limiting_factor ? (
                    <span className="block text-xs text-muted-foreground" data-testid="da-limiting" data-factor={a.limiting_factor}>
                      {t("limitedBy", { factor: l.limiting(a.limiting_factor) })}
                    </span>
                  ) : null}
                </FieldItem>
              </>
            )}
          </FieldList>
        </CardContent>
      </Card>
      {a.redacted ? (
        <Alert tone="info" data-testid="da-redacted">
          {t("redacted")}
        </Alert>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("licenceSection")}</CardTitle>
            </CardHeader>
            <CardContent>
              <FieldList>
                <FieldItem label={t("licenceIssuer")}>{a.licence_issuer ? te(`licenceIssuer.${a.licence_issuer}`) : "—"}</FieldItem>
                <FieldItem label={t("licenceClass")}>{a.licence_class ? te(`licenceClass.${a.licence_class}`) : "—"}</FieldItem>
                <FieldItem label={t("licenceExpiry")}>{date(a.licence_expiry)}</FieldItem>
                <FieldItem label={t("assessmentDate")}>{date(a.assessment_date)}</FieldItem>
                <FieldItem label={t("assessor")}>{a.assessor}</FieldItem>
                {a.licence_prefilled_from_adp ? <FieldItem label={t("source")}>{t("fromAdp")}</FieldItem> : null}
              </FieldList>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("hooks")}</CardTitle>
              <p className="text-sm text-muted-foreground">{a.hooks_evaluated_at ? t("hooksAt", { at: dateTime(a.hooks_evaluated_at) }) : t("hooksHint")}</p>
            </CardHeader>
            <CardContent>
              {a.hook_results.length ? (
                <Table stack={false} data-testid="da-hooks">
                  <THead>
                    <TR>
                      <TH>{t("hookKind")}</TH>
                      <TH>{t("hookCode")}</TH>
                      <TH>{t("hookResult")}</TH>
                      <TH>{t("validUntil")}</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {a.hook_results.map((h, i) => (
                      <TR key={`${h.code}-${i}`} data-testid="da-hook" data-code={h.code} data-result={h.result}>
                        <TD>{te(`hookKind.${h.kind}`)}</TD>
                        <TD>
                          <Code>{h.code}</Code>
                        </TD>
                        <TD>
                          <HookBadge result={h.result} />
                        </TD>
                        <TD>{date(h.valid_until)}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground">{t("noHooks")}</p>
              )}
            </CardContent>
          </Card>
        </>
      )}
      <HistoryPanel entityType="driver_authorisation" entityId={a.id} />
      {decide && !final ? (
        <RecordActions testId="da-record-actions">
          <Button variant="destructive-outline" onClick={() => setMove("revoked")} data-testid="da-revoke">
            <Ban aria-hidden />
            {t("revoke")}
          </Button>
        </RecordActions>
      ) : null}
      {move ? <MoveDialog a={a} move={move} onClose={() => setMove(null)} /> : null}
    </div>
  );
}

function HookBadge({ result }: { result: S["SiteVehHookResult"] }) {
  const l = useSvLabels();
  return (
    <Badge tone={result === "met" ? "success" : result === "warn" ? "warning" : "danger"} className={cn("font-medium")}>
      {result === "met" ? <CheckCircle2 aria-hidden /> : result === "warn" ? <TriangleAlert aria-hidden /> : <XCircle aria-hidden />}
      {l.hook(result)}
    </Badge>
  );
}

function MoveDialog({ a, move, onClose }: { a: Auth; move: Exclude<Move, null>; onClose: () => void }) {
  const t = useTranslations("sv.auth");
  const tf = useTranslations("fu.common");
  const refresh = useSvRefresh();
  const warn = useWarningToasts();
  const [reason, setReason] = useState("");
  const min = move === "suspended" ? 20 : move === "reinstate" ? 5 : move === "revoked" ? 5 : 0;
  const n = reason.trim().length;
  const to: S["SiteVehAuthStatus"] = move === "reinstate" ? "active" : move;
  return (
    <StepDialog
      title={t(`move.${move}`)}
      description={t(`moveHint.${move}`)}
      confirmLabel={t(`move.${move}`)}
      destructive={move === "revoked"}
      testId="da-move-confirm"
      disabled={n < min}
      onConfirm={async () => {
        const u = await unwrap(api.POST("/api/v1/driver-authorisations/{auth_id}/transition", { params: { path: { auth_id: a.id } }, body: { to_status: to, reason: reason.trim() || null } }));
        await refresh();
        warn(u.warnings);
        toast.success(t("moved", { status: t(`move.${move}`) }));
      }}
      onClose={onClose}
    >
      {min > 0 || move === "active" ? (
        <FormField id="da-move-reason" label={tf("reason")} required={min > 0} hint={min > 0 ? tf("reasonMin", { min, n }) : undefined}>
          <Textarea maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="da-move-reason" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}
