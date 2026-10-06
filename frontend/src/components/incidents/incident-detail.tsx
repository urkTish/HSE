"use client";
import { ClipboardCheck, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { MultiSelect } from "@/components/common/multi-select";
import { UserSelect, useUserOptions } from "@/components/common/pickers";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useIncident } from "@/lib/api/hse";
import { useProjectSettings } from "@/lib/api/queries";
import { DEFAULT_TIME_ZONE, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { useDisplay } from "@/lib/digits";
import { INVESTIGATION_LEVELS, INVESTIGATION_METHODS } from "@/lib/enums";
import { useErrorMessage, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useRefLists } from "@/lib/reference";
import { useFormatters } from "@/lib/use-formatters";

type Status = Schemas["IncidentStatus"];
const LEVEL_RANK: Record<Schemas["InvestigationLevel"], number> = { L1: 1, L2: 2, L3: 3 };

/** Which transitions need a reason (spec §4.2). */
function needsReason(from: Status, to: Status): boolean {
  return to === "voided" || (from === "reported" && to === "closed") || (from === "pending_review" && to === "under_investigation") || from === "closed" || from === "voided";
}

export function IncidentDetail({ id }: { id: string }) {
  const t = useTranslations("incidents");
  const tcs = useTranslations("cases");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const locale = useLocale();
  const me = useMeData();
  const qc = useQueryClient();
  const router = useRouter();
  const msg = useErrorMessage();
  const name = useLocalizedName();
  const ref = useRefLists();
  const q = useIncident(id);
  const pid = q.data?.project_id ?? null;
  const show = useDisplay(pid);
  const { date, dateTime } = useFormatters(pid);
  const [transitionTo, setTransitionTo] = useState<Status | null>(null);
  const [notifyBody, setNotifyBody] = useState<Schemas["ExternalBody"] | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const r = q.data;
  const editable = canWrite(me, "incident.report", r.project_id) && ["draft", "reported", "under_investigation"].includes(r.status);
  const canClassify = canWrite(me, "incident.classify", r.project_id);
  const canAddCase = canWrite(me, "incident.report", r.project_id) && r.incident_types.includes("injury_illness") && !["closed", "voided"].includes(r.status);

  async function refresh(next?: Schemas["IncidentRead"]) {
    if (next) qc.setQueryData(hk.incident(r.id), next);
    else await qc.invalidateQueries({ queryKey: hk.incident(r.id) });
    await qc.invalidateQueries({ queryKey: ["incidents"] });
    await qc.invalidateQueries({ queryKey: ["history"] });
  }

  async function remove() {
    if (!window.confirm(tc("confirmDelete"))) return;
    try {
      await unwrap(api.DELETE("/api/v1/incidents/{incident_id}", { params: { path: { incident_id: r.id } } }));
      await qc.invalidateQueries({ queryKey: ["incidents"] });
      toast.success(tc("deleted"));
      router.push("/incidents");
    } catch (e) {
      toast.error(msg(e));
    }
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("incidents"), href: "/incidents" }, { label: r.ref }]} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
              <div className="flex flex-col gap-1">
                <p className="ltr text-sm text-muted-foreground" data-testid="incident-ref">
                  {r.ref}
                </p>
                <CardTitle className="flex flex-wrap items-center gap-2">
                  <span data-testid="incident-title">{r.title}</span>
                  <StatusBadge status={r.status} label={te(`incidentStatus.${r.status}`)} />
                  {r.hipo ? <StatusBadge status="warning" label={t("hipo")} /> : null}
                  {r.late_report ? <StatusBadge status="late" label={t("late")} /> : null}
                </CardTitle>
              </div>
              <div className="flex gap-2">
                {editable ? (
                  <Button variant="outline" size="sm" asChild>
                    <Link href={`/incidents/${r.id}/edit`} data-testid="edit-incident">
                      <Pencil aria-hidden />
                      {tc("edit")}
                    </Link>
                  </Button>
                ) : null}
                {editable && r.status === "draft" ? (
                  <Button variant="outline" size="sm" onClick={() => void remove()}>
                    <Trash2 aria-hidden />
                    {tc("delete")}
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {r.status === "voided" ? (
                <Alert tone="warning">
                  {t("voidedNote")} {r.void_reason ? `${t("voidReason")}: ${r.void_reason}` : ""}
                </Alert>
              ) : null}
              <ApiWarnings warnings={r.warnings} />
              <FieldList>
                <FieldItem label={t("fields.incident_types")}>
                  {r.incident_types.map((x) => te(`incidentType.${x}`)).join(" · ")} ({t("fields.primary_type")}: {te(`incidentType.${r.primary_type}`)})
                </FieldItem>
                <FieldItem label={t("fields.occurred_at")}>{dateTime(r.occurred_at)}</FieldItem>
                <FieldItem label={t("fields.reported_at")}>
                  {r.reported_at ? `${dateTime(r.reported_at)}${r.reported_by ? ` · ${name(r.reported_by.full_name_en, r.reported_by.full_name_ar)}` : ""}` : "—"}
                </FieldItem>
                <FieldItem label={t("fields.shift")}>{r.shift ? te(`shift.${r.shift}`) : "—"}</FieldItem>
                <FieldItem label={t("fields.site")}>
                  <span className="ltr">{r.site.code}</span> — {name(r.site.name_en, r.site.name_ar)}
                </FieldItem>
                <FieldItem label={t("fields.zone")}>{r.zone ? `${r.zone.code} — ${name(r.zone.name_en, r.zone.name_ar)}` : "—"}</FieldItem>
                <FieldItem label={t("fields.location_detail")}>{r.location_detail}</FieldItem>
                <FieldItem label={t("fields.responsible_engagement")}>
                  {r.responsible_engagement ? (
                    <>
                      <span className="ltr">{r.responsible_engagement.short_code}</span> — {name(r.responsible_engagement.name_en, r.responsible_engagement.name_ar)}
                    </>
                  ) : (
                    "—"
                  )}
                </FieldItem>
                <FieldItem label={t("fields.activity")}>{ref.label("activity", r.activity)}</FieldItem>
                <FieldItem label={t("fields.actual_severity")}>
                  {r.actual_severity ? `${show(r.actual_severity)} — ${ref.label("severity", r.actual_severity)}` : "—"}
                </FieldItem>
                <FieldItem label={t("fields.potential_severity")}>
                  {r.potential_severity ? `${show(r.potential_severity)} — ${ref.label("severity", r.potential_severity)}` : "—"}
                </FieldItem>
                <FieldItem label={t("minLevel")}>
                  <span className="ltr">{te(`investigationLevel.${r.minimum_investigation_level}`)}</span>
                </FieldItem>
                <FieldItem label={t("fields.work_related")}>
                  <YesNo value={r.work_related} yes={tc("yes")} no={tc("no")} />
                  {!r.work_related && r.not_work_related_reason ? ` — ${te(`notWorkRelated.${r.not_work_related_reason}`)}` : ""}
                </FieldItem>
                <FieldItem label={t("fields.ambient_temp_c")}>{show(r.ambient_temp_c)}</FieldItem>
                {r.airside_flags.length > 0 ? <FieldItem label={t("fields.airside_flags")}>{r.airside_flags.map((x) => te(`airsideFlag.${x}`)).join(" · ")}</FieldItem> : null}
                {r.property_damage ? (
                  <FieldItem label={t("fields.pd")}>
                    {te(`assetType.${r.property_damage.asset_type}`)} · {show(r.property_damage.estimated_cost_sar)} SAR
                  </FieldItem>
                ) : null}
                {r.environmental ? (
                  <FieldItem label={t("fields.env")}>
                    {te(`envCategory.${r.environmental.category}`)}
                    {r.environmental.substance ? ` · ${r.environmental.substance}` : ""}
                    {r.environmental.quantity_l ? ` · ${show(r.environmental.quantity_l)} L` : ""} · {t("fields.reached")}: {te(`envReached.${r.environmental.reached}`)}
                  </FieldItem>
                ) : null}
                {r.dangerous_occurrence ? <FieldItem label={t("fields.do")}>{te(`doCategory.${r.dangerous_occurrence.category}`)}</FieldItem> : null}
              </FieldList>
              <FieldList>
                <FieldItem label={t("fields.description")} wide>
                  <span className="whitespace-pre-wrap">{r.description ?? "—"}</span>
                </FieldItem>
                <FieldItem label={t("fields.immediate_actions")} wide>
                  <span className="whitespace-pre-wrap">{r.immediate_actions ?? "—"}</span>
                </FieldItem>
              </FieldList>
            </CardContent>
          </Card>

          {r.incident_types.includes("injury_illness") ? (
            <Card data-testid="cases-card">
              <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
                <CardTitle>{t("cases")}</CardTitle>
                {canAddCase ? (
                  <Button size="sm" asChild>
                    <Link href={`/incidents/${r.id}/cases/new`} data-testid="add-case">
                      <Plus aria-hidden />
                      {t("addCase")}
                    </Link>
                  </Button>
                ) : null}
              </CardHeader>
              <CardContent>
                {r.cases.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t("noCases")}</p>
                ) : (
                  <Table data-testid="cases-table">
                    <THead>
                      <TR>
                        <TH>{tcs("fields.case_no")}</TH>
                        <TH>{tcs("title")}</TH>
                        <TH>{tcs("fields.mechanism")}</TH>
                        <TH>{tcs("fields.case_category")}</TH>
                        <TH>{tcs("fields.classification_status")}</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {r.cases.map((c) => (
                        <TR key={c.id} data-testid="case-row">
                          <TD label={tcs("fields.case_no")}>
                            <Link href={`/injury-cases/${c.id}`} className="ltr text-primary hover:underline">
                              {c.case_no}
                            </Link>
                          </TD>
                          <TD label={tcs("title")}>
                            <span data-testid="case-label">{locale === "ar" ? c.display_label_ar : c.display_label}</span>
                          </TD>
                          <TD label={tcs("fields.mechanism")}>{ref.label("mechanism", c.mechanism)}</TD>
                          <TD label={tcs("fields.case_category")}>
                            <span className="inline-flex flex-wrap gap-1">
                              {c.case_category ? te(`caseCategory.${c.case_category}`) : "—"}
                              {c.open_lti ? <StatusBadge status="warning" label={t("openLti")} /> : null}
                            </span>
                          </TD>
                          <TD label={tcs("fields.classification_status")}>
                            <span className="inline-flex flex-wrap gap-1">
                              <StatusBadge status={c.classification_status} label={te(`classificationStatus.${c.classification_status}`)} />
                              {c.excluded_from_rates ? (
                                <span className="text-xs text-muted-foreground" title={c.exclusion_reasons.map((x) => te(`rateExclusion.${x}`)).join(", ")}>
                                  {t("excludedFromRates")}: {c.exclusion_reasons.map((x) => te(`rateExclusion.${x}`)).join(", ")}
                                </span>
                              ) : null}
                            </span>
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          ) : null}

          <Card data-testid="notifications-card">
            <CardHeader>
              <CardTitle>{t("notifications")}</CardTitle>
              <p className="text-xs text-muted-foreground">{t("notificationsHint")}</p>
            </CardHeader>
            <CardContent>
              <Table>
                <THead>
                  <TR>
                    <TH>{tc("title")}</TH>
                    <TH>{t("fields.status")}</TH>
                    <TH>{t("dueAt")}</TH>
                    <TH>{t("notifiedAt")}</TH>
                    <TH>{t("referenceNo")}</TH>
                    <TH>{tc("actions")}</TH>
                  </TR>
                </THead>
                <TBody>
                  {r.external_notifications.map((n) => (
                    <TR key={n.body} data-testid="notification-row" data-body={n.body} data-state={n.state ?? "none"}>
                      <TD label={tc("title")}>
                        <span className="font-medium">{te(`externalBody.${n.body}`)}</span>
                        {n.required_reason ? <span className="block text-xs text-muted-foreground">{n.required_reason}</span> : null}
                      </TD>
                      <TD label={t("fields.status")}>{n.state ? <StatusBadge status={n.state} label={te(`notificationState.${n.state}`)} /> : <span className="text-muted-foreground">{t("notRequired")}</span>}</TD>
                      <TD label={t("dueAt")}>{dateTime(n.due_at)}</TD>
                      <TD label={t("notifiedAt")}>{dateTime(n.notified_at)}</TD>
                      <TD label={t("referenceNo")}>{n.reference_no ? <span className="ltr">{n.reference_no}</span> : "—"}</TD>
                      <TD label={tc("actions")}>
                        {canClassify && r.status !== "voided" ? (
                          <Button size="sm" variant="outline" onClick={() => setNotifyBody(n.body)} data-testid={`record-${n.body}`}>
                            {t("record")}
                          </Button>
                        ) : null}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle>{t("linkedActions")}</CardTitle>
              {canWrite(me, "ca.create", r.project_id) && !["voided", "draft"].includes(r.status) ? (
                <Button size="sm" variant="outline" asChild>
                  <Link href={`/actions/new?source_type=incident&source_id=${r.id}&source_ref=${encodeURIComponent(r.ref)}`} data-testid="raise-ca">
                    <ClipboardCheck aria-hidden />
                    {t("raiseAction")}
                  </Link>
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>
              {r.corrective_actions.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("noLinkedActions")}</p>
              ) : (
                <ul className="flex flex-col divide-y">
                  {r.corrective_actions.map((ca) => (
                    <li key={ca.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                      <Link href={`/actions/${ca.id}`} className="text-primary hover:underline">
                        <span className="ltr">{ca.ref}</span> — {ca.title}
                      </Link>
                      <span className="inline-flex flex-wrap items-center gap-1">
                        <span className="text-xs text-muted-foreground">{te(`controlLevel.${ca.control_level}`)}</span>
                        <span className="text-xs">{date(ca.due_date)}</span>
                        <StatusBadge status={ca.overdue ? "overdue" : ca.status} label={te(`caStatus.${ca.status}`)} />
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{tc("attachments")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Attachments ownerType="incident" ownerId={r.id} canUpload={editable} canDelete={editable} hint={t("attachHint")} />
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          {r.allowed_transitions.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("fields.status")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2" role="group">
                {r.allowed_transitions.map((to) => (
                  <Button key={to} size="sm" variant={to === "voided" ? "destructive" : "outline"} onClick={() => setTransitionTo(to)} data-testid={`transition-${to}`}>
                    {t("transitionTo", { status: te(`incidentStatus.${to}`) })}
                  </Button>
                ))}
              </CardContent>
            </Card>
          ) : null}
          <Card data-testid="investigation-card">
            <CardHeader>
              <CardTitle>{t("investigation")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              {r.investigation ? (
                <>
                  <FieldList>
                    <FieldItem label={t("minLevel")}>{te(`investigationLevel.${r.investigation.level}`)}</FieldItem>
                    <FieldItem label={tc("owner")}>{r.investigation.lead_investigator ? name(r.investigation.lead_investigator.full_name_en, r.investigation.lead_investigator.full_name_ar) : "—"}</FieldItem>
                    <FieldItem label={t("dueAt")}>
                      <span className="inline-flex items-center gap-1">
                        {date(r.investigation.due_date)}
                        {r.investigation.overdue ? <StatusBadge status="overdue" label={te("notificationState.overdue")} /> : null}
                      </span>
                    </FieldItem>
                  </FieldList>
                  <Button size="sm" variant="outline" asChild>
                    <Link href={`/incidents/${r.id}/investigation`} data-testid="open-investigation">
                      <Search aria-hidden />
                      {t("openInvestigation")}
                    </Link>
                  </Button>
                </>
              ) : (
                <p className="text-muted-foreground">{te(`investigationLevel.${r.minimum_investigation_level}`)} — {t("minLevel")}</p>
              )}
            </CardContent>
          </Card>
          {can(me, "history.view", r.project_id) ? <HistoryPanel entityType="incident" entityId={r.id} projectId={r.project_id} /> : null}
        </div>
      </div>
      {transitionTo ? <IncidentTransitionDialog incident={r} to={transitionTo} onClose={() => setTransitionTo(null)} onDone={refresh} /> : null}
      {notifyBody ? <NotificationDialog incident={r} body={notifyBody} onClose={() => setNotifyBody(null)} onDone={() => refresh()} /> : null}
    </div>
  );
}

function IncidentTransitionDialog({
  incident: r,
  to,
  onClose,
  onDone,
}: {
  incident: Schemas["IncidentRead"];
  to: Status;
  onClose: () => void;
  onDone: (next: Schemas["IncidentRead"]) => Promise<void>;
}) {
  const t = useTranslations("incidents");
  const tt = useTranslations("transitions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const ti = useTranslations("investigation");
  const users = useUserOptions(r.project_id);
  const assign = r.status === "reported" && to === "under_investigation";
  const approve = r.status === "pending_review" && (to === "actions_pending" || to === "closed");
  const reasonRequired = needsReason(r.status, to);
  const minRank = LEVEL_RANK[r.minimum_investigation_level];
  const [reason, setReason] = useState("");
  const [level, setLevel] = useState<Schemas["InvestigationLevel"]>(r.minimum_investigation_level);
  const [lead, setLead] = useState("");
  const [team, setTeam] = useState<string[]>([]);
  const [method, setMethod] = useState<Schemas["InvestigationMethod"] | "">(r.minimum_investigation_level === "L3" ? "icam" : r.minimum_investigation_level === "L1" ? "simple" : "five_why");
  const [justification, setJustification] = useState("");
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    const e: Record<string, string> = {};
    if (reasonRequired && !reason.trim()) e.reason = tt("reasonRequired");
    if (assign && !lead) e.lead = tv("required");
    setErrs(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(
        api.POST("/api/v1/incidents/{incident_id}/transitions", {
          params: { path: { incident_id: r.id } },
          body: {
            to_status: to,
            reason: reason.trim() || null,
            investigation: assign ? { level, lead_investigator_id: lead, team_member_ids: team, method: method || null } : null,
            higher_control_justification: approve ? justification.trim() || null : null,
          },
        }),
      );
      toast.success(tt("done", { status: te(`incidentStatus.${to}`) }));
      await onDone(next);
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{assign ? t("assignTitle") : tt("dialogTitle", { status: te(`incidentStatus.${to}`) })}</DialogTitle>
          <DialogDescription>{assign ? t("assignBody") : tt("dialogBody", { from: te(`incidentStatus.${r.status}`) })}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          {assign ? (
            <>
              <FormField id="inv-level" label={ti("fields.level")} required>
                <Select value={level} onChange={(e) => setLevel(e.target.value as Schemas["InvestigationLevel"])} data-testid="inv-level">
                  {INVESTIGATION_LEVELS.filter((l) => LEVEL_RANK[l] >= minRank).map((l) => (
                    <option key={l} value={l}>
                      {te(`investigationLevel.${l}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="inv-lead" label={ti("fields.lead")} required error={errs.lead}>
                <UserSelect projectId={r.project_id} value={lead} onChange={(e) => setLead(e.target.value)} data-testid="inv-lead" />
              </FormField>
              <MultiSelect id="inv-team" label={t("team")} options={users} value={team} onChange={setTeam} testId="inv-team" />
              <p className="-mt-2 text-xs text-muted-foreground">{t("teamHint")}</p>
              <FormField id="inv-method" label={ti("fields.method")}>
                <Select value={method} onChange={(e) => setMethod(e.target.value as Schemas["InvestigationMethod"])}>
                  {INVESTIGATION_METHODS.map((m) => (
                    <option key={m} value={m}>
                      {te(`investigationMethod.${m}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
            </>
          ) : null}
          {approve && r.hipo ? (
            <FormField id="higher-control" label={t("higherControl")} hint={t("higherControlHint")}>
              <Textarea value={justification} onChange={(e) => setJustification(e.target.value)} maxLength={1000} />
            </FormField>
          ) : null}
          <FormField id="transition-reason" label={reasonRequired ? tc("reason") : tt("reasonOptional")} required={reasonRequired} error={errs.reason}>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
          </FormField>
          <MutationError error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant={to === "voided" ? "destructive" : "default"} onClick={() => void submit()} disabled={busy} data-testid="transition-confirm">
            {busy ? tc("saving") : tt("submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NotificationDialog({
  incident: r,
  body,
  onClose,
  onDone,
}: {
  incident: Schemas["IncidentRead"];
  body: Schemas["ExternalBody"];
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const t = useTranslations("incidents");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const settings = useProjectSettings(r.project_id);
  const tz = settings.data?.timezone ?? DEFAULT_TIME_ZONE;
  const existing = r.external_notifications.find((n) => n.body === body);
  const [at, setAt] = useState(utcToZonedInput(existing?.notified_at ?? new Date().toISOString(), tz));
  const [refNo, setRefNo] = useState(existing?.reference_no ?? "");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PUT("/api/v1/incidents/{incident_id}/external-notifications/{body}", {
          params: { path: { incident_id: r.id, body } },
          body: { notified_at: zonedInputToUtc(at, tz), reference_no: refNo.trim() || null },
        }),
      );
      toast.success(tc("saved"));
      await onDone();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("recordNotification", { body: te(`externalBody.${body}`) })}</DialogTitle>
          <DialogDescription>{t("notificationsHint")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField id="notified-at" label={t("notifiedAt")} required>
            <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
          </FormField>
          <FormField id="notified-ref" label={t("referenceNo")}>
            <Input value={refNo} onChange={(e) => setRefNo(e.target.value)} maxLength={60} className="ltr" />
          </FormField>
          <MutationError error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !at} data-testid="notification-save">
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
