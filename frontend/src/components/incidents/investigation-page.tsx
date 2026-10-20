"use client";
import { CalendarPlus, Plus, Printer, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Controller, useFieldArray, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { MultiSelect } from "@/components/common/multi-select";
import { UserSelect, useUserOptions } from "@/components/common/pickers";
import { PossibleIdHint } from "@/components/common/api-warnings";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useIncident, useIncidentPermitSuggestions, useInvestigation } from "@/lib/api/hse";
import { INVESTIGATION_LEVELS, INVESTIGATION_METHODS } from "@/lib/enums";
import { applyServerErrors } from "@/lib/forms";
import { joinList, useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { useRefLists } from "@/lib/reference";
import { useFormatters } from "@/lib/use-formatters";
import { IncidentTransitionDialog } from "./incident-detail";

const RANK: Record<Schemas["InvestigationLevel"], number> = { L1: 1, L2: 2, L3: 3 };

interface Values {
  level: Schemas["InvestigationLevel"];
  lead_investigator_id: string;
  team_member_ids: string[];
  method: string;
  preliminary_report: string;
  sequence_of_events: string;
  immediate_causes: string;
  lessons_learned: string;
  ptw_involved: boolean;
  ptw_ref: string;
  ptw_ids: string[];
  root_causes: { code: string; text: string; linked_ca_ids: string[]; no_action_justification: string }[];
}

export function InvestigationPage({ id }: { id: string }) {
  const t = useTranslations("investigation");
  const ti = useTranslations("incidents");
  const tn = useTranslations("nav");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const ref = useRefLists();
  const inc = useIncident(id);
  const q = useInvestigation(id, Boolean(inc.data?.investigation));
  const pid = inc.data?.project_id ?? null;
  const { date, dateTime } = useFormatters(pid);
  const [editing, setEditing] = useState(false);
  const [extending, setExtending] = useState(false);
  const [transitionTo, setTransitionTo] = useState<Schemas["IncidentStatus"] | null>(null);
  const qc = useQueryClient();
  if (inc.isError) return <ErrorState error={inc.error} onRetry={() => inc.refetch()} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (inc.data && !inc.data.investigation)
    return (
      <div>
        <Breadcrumbs items={[{ label: tn("incidents"), href: "/incidents" }, { label: inc.data.ref, href: `/incidents/${inc.data.id}` }, { label: t("title") }]} />
        <Alert tone="info">
          {t("notStartedBody", { level: te(`investigationLevel.${inc.data.minimum_investigation_level}`) })}{" "}
          <Link href={`/incidents/${inc.data.id}`} className="text-primary underline">
            {inc.data.ref}
          </Link>
        </Alert>
      </div>
    );
  if (!inc.data || !q.data) return <LoadingState />;
  const incident = inc.data;
  const v = q.data;
  const canEdit = canWrite(me, "investigation.edit", incident.project_id) && ["under_investigation", "reported"].includes(incident.status);
  const canExtend = canWrite(me, "investigation.approve", incident.project_id) && !["closed", "voided"].includes(incident.status);
  const caById = new Map(incident.corrective_actions.map((c) => [c.id, c]));
  // D-269: submit, approve and return straight from the report.
  const reportMoves = incident.allowed_transitions.filter(
    (to) => (incident.status === "under_investigation" && to === "pending_review") || (incident.status === "pending_review" && ["actions_pending", "closed", "under_investigation"].includes(to)),
  );
  async function refresh(next?: Schemas["IncidentRead"]) {
    if (next) qc.setQueryData(hk.incident(incident.id), next);
    await qc.invalidateQueries({ queryKey: ["incidents"] });
    await qc.invalidateQueries({ queryKey: ["history"] });
    await q.refetch();
  }
  const missingLabel = (m: string) =>
    m.startsWith("cases[") ? t("missingId") : m === "photos" ? t("missingPhotos") : t.has(`fields.${m as "level"}`) ? t(`fields.${m as "level"}`) : m;

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("incidents"), href: "/incidents" }, { label: incident.ref, href: `/incidents/${incident.id}` }, { label: t("title") }]} />
      {editing ? (
        <InvestigationForm incident={incident} inv={v} onDone={() => setEditing(false)} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="flex flex-col gap-6 lg:col-span-2">
            <Card>
              <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
                <CardTitle className="flex flex-wrap items-center gap-2">
                  <span data-testid="investigation-title">{t("title")}</span>
                  <span className="ltr text-sm font-normal text-muted-foreground">{incident.ref}</span>
                  {v.overdue ? <StatusBadge status="overdue" label={t("overdue")} /> : null}
                </CardTitle>
                <div className="flex gap-2 print:hidden">
                  <Button size="sm" variant="outline" onClick={() => window.print()} data-testid="print-investigation">
                    <Printer aria-hidden />
                    {t("print")}
                  </Button>
                  {canEdit ? (
                    <Button size="sm" variant="outline" onClick={() => setEditing(true)} data-testid="edit-investigation">
                      {t("edit")}
                    </Button>
                  ) : null}
                  {canExtend ? (
                    <Button size="sm" variant="outline" onClick={() => setExtending(true)} data-testid="extend-investigation">
                      <CalendarPlus aria-hidden />
                      {t("extend")}
                    </Button>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                {v.returned_comment ? (
                  <Alert tone="warning">
                    {t("returned")}: {v.returned_comment}
                  </Alert>
                ) : null}
                {v.missing_for_submit.length > 0 && incident.status === "under_investigation" ? (
                  <Alert tone="info" data-testid="missing-for-submit">
                    <p className="font-medium">{t("missing")}</p>
                    <ul className="ms-4 list-disc">
                      {v.missing_for_submit.map((m) => (
                        <li key={m}>{missingLabel(m)}</li>
                      ))}
                    </ul>
                  </Alert>
                ) : null}
                <FieldList>
                  <FieldItem label={t("fields.level")}>
                    {t("levelWithMin", { level: te(`investigationLevel.${v.level}`), min: v.minimum_level })}
                  </FieldItem>
                  <FieldItem label={t("fields.lead")}>{v.lead_investigator ? name(v.lead_investigator.full_name_en, v.lead_investigator.full_name_ar) : "—"}</FieldItem>
                  <FieldItem label={t("fields.team")}>{joinList(v.team_members.map((u) => name(u.full_name_en, u.full_name_ar))) || "—"}</FieldItem>
                  <FieldItem label={t("fields.method")}>{v.method ? te(`investigationMethod.${v.method}`) : "—"}</FieldItem>
                  <FieldItem label={t("fields.due_date")}>{date(v.due_date)}</FieldItem>
                  {v.preliminary_report_due_at ? <FieldItem label={t("fields.preliminary_due")}>{dateTime(v.preliminary_report_due_at)}</FieldItem> : null}
                  <FieldItem label={t("fields.ptw_involved")}>
                    <YesNo value={v.ptw_involved} yes={tc("yes")} no={tc("no")} />
                    {v.ptw_ref ? <span className="ltr"> · {v.ptw_ref}</span> : null}
                  </FieldItem>
                  {(v.ptws ?? []).length > 0 ? (
                    <FieldItem label={t("fields.ptws")}>
                      <span className="flex flex-wrap gap-x-3 gap-y-1" data-testid="inv-ptws">
                        {(v.ptws ?? []).map((p) => (
                          <Link key={p.id} href={`/permits/${p.id}`} className="ltr text-primary hover:underline">
                            {p.display_no}
                          </Link>
                        ))}
                      </span>
                    </FieldItem>
                  ) : null}
                  <FieldItem label={t("fields.submitted_at")}>{dateTime(v.submitted_at)}</FieldItem>
                  <FieldItem label={t("fields.approved")}>{v.approved_by ? `${name(v.approved_by.full_name_en, v.approved_by.full_name_ar)} · ${dateTime(v.approved_at)}` : "—"}</FieldItem>
                </FieldList>
                <FieldList>
                  {v.preliminary_report ? (
                    <FieldItem label={t("fields.preliminary_report")} wide>
                      <span className="whitespace-pre-wrap">{v.preliminary_report}</span>
                    </FieldItem>
                  ) : null}
                  <FieldItem label={t("fields.sequence_of_events")} wide>
                    <span className="whitespace-pre-wrap">{v.sequence_of_events ?? "—"}</span>
                  </FieldItem>
                  <FieldItem label={t("fields.immediate_causes")} wide>
                    <span className="whitespace-pre-wrap">{v.immediate_causes ?? "—"}</span>
                  </FieldItem>
                  <FieldItem label={t("fields.lessons_learned")} wide>
                    <span className="whitespace-pre-wrap">{v.lessons_learned ?? "—"}</span>
                  </FieldItem>
                </FieldList>
              </CardContent>
            </Card>
            <Card data-testid="report-incident">
              <CardHeader>
                <CardTitle>{t("incidentDetails")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <FieldList>
                  <FieldItem label={ti("fields.occurred_at")}>{dateTime(incident.occurred_at)}</FieldItem>
                  <FieldItem label={ti("fields.reported_at")}>{dateTime(incident.reported_at)}</FieldItem>
                  <FieldItem label={ti("fields.site")}>
                    <span className="ltr">{incident.site.code}</span> — {name(incident.site.name_en, incident.site.name_ar)}
                  </FieldItem>
                  <FieldItem label={ti("fields.zone")}>{incident.zone ? `${incident.zone.code} — ${name(incident.zone.name_en, incident.zone.name_ar)}` : "—"}</FieldItem>
                  <FieldItem label={ti("fields.responsible_engagement")}>
                    {incident.responsible_engagement ? name(incident.responsible_engagement.name_en, incident.responsible_engagement.name_ar) : "—"}
                  </FieldItem>
                  <FieldItem label={ti("fields.incident_types")}>{incident.incident_types.map((x) => te(`incidentType.${x}`)).join(" · ")}</FieldItem>
                  <FieldItem label={ti("fields.title")} wide>
                    {incident.title}
                  </FieldItem>
                  <FieldItem label={ti("fields.description")} wide>
                    <span className="whitespace-pre-wrap">{incident.description ?? "—"}</span>
                  </FieldItem>
                  <FieldItem label={ti("fields.immediate_actions")} wide>
                    <span className="whitespace-pre-wrap">{incident.immediate_actions ?? "—"}</span>
                  </FieldItem>
                </FieldList>
                <div>
                  <p className="mb-2 text-sm font-medium">{t("peopleInvolved")}</p>
                  {incident.cases.length === 0 ? (
                    <p className="text-sm text-muted-foreground">—</p>
                  ) : (
                    <ul className="flex flex-col gap-1 text-sm">
                      {incident.cases.map((c) => (
                        <li key={c.id}>
                          <Link href={`/injury-cases/${c.id}`} className="ltr text-primary hover:underline">
                            {c.case_no}
                          </Link>{" "}
                          · {c.display_label} · {c.case_category ? te(`caseCategory.${c.case_category}`) : "—"}
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="mt-1 text-xs text-muted-foreground">{t("idHint")}</p>
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium">{t("photos")}</p>
                  <Attachments ownerType="incident" ownerId={incident.id} canUpload={canEdit} canDelete={canEdit} hint={t("photosHint")} />
                </div>
              </CardContent>
            </Card>
            <Card data-testid="corrective-actions">
              <CardHeader>
                <CardTitle>{t("capa")}</CardTitle>
              </CardHeader>
              <CardContent>
                {incident.corrective_actions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">—</p>
                ) : (
                  <ul className="flex flex-col gap-1 text-sm">
                    {incident.corrective_actions.map((c) => (
                      <li key={c.id}>
                        <Link href={`/actions/${c.id}`} className="ltr text-primary hover:underline">
                          {c.ref}
                        </Link>{" "}
                        — {c.title} · {te(`caStatus.${c.status}`)}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card data-testid="root-causes">
              <CardHeader>
                <CardTitle>{t("rootCauses")}</CardTitle>
              </CardHeader>
              <CardContent>
                {v.root_causes.length === 0 ? (
                  <p className="text-sm text-muted-foreground">—</p>
                ) : (
                  <ul className="flex flex-col gap-3">
                    {v.root_causes.map((rc, i) => (
                      <li key={`${rc.code}-${i}`} className="rounded-md border p-3 text-sm">
                        <p className="font-medium">
                          <span className="ltr">{rc.code}</span> · {te(`icamLevel.${rc.icam_level}`)} — {ref.label("root_cause", rc.code)}
                        </p>
                        <p className="mt-1 whitespace-pre-wrap">{rc.text}</p>
                        {rc.linked_ca_ids.length > 0 ? (
                          <p className="mt-2 flex flex-wrap gap-2">
                            {rc.linked_ca_ids.map((cid) => (
                              <Link key={cid} href={`/actions/${cid}`} className="ltr text-primary hover:underline">
                                {caById.get(cid)?.ref ?? cid.slice(0, 8)}
                              </Link>
                            ))}
                          </p>
                        ) : rc.no_action_justification ? (
                          <p className="mt-2 text-muted-foreground">
                            {t("noAction")}: {rc.no_action_justification}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
          <div className="flex flex-col gap-6">
            {reportMoves.length > 0 ? (
              <Card className="print:hidden" data-testid="report-approval">
                <CardHeader>
                  <CardTitle>{incident.status === "pending_review" ? t("approvalTitle") : t("submitTitle")}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <p className="text-sm text-muted-foreground">{incident.status === "pending_review" ? t("approvalBody") : t("submitBody")}</p>
                  <div className="flex flex-wrap gap-2">
                    {reportMoves.map((to) => (
                      <Button key={to} size="sm" variant={to === "under_investigation" ? "outline" : "default"} onClick={() => setTransitionTo(to)} data-testid={`report-${to}`}>
                        {to === "pending_review" ? t("submitForApproval") : to === "under_investigation" ? t("returnForChanges") : t("approve", { status: te(`incidentStatus.${to}`) })}
                      </Button>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : null}
            <Card>
              <CardHeader>
                <CardTitle>{t("extensions")}</CardTitle>
              </CardHeader>
              <CardContent>
                {v.extensions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">—</p>
                ) : (
                  <ul className="flex flex-col gap-2 text-sm">
                    {v.extensions.map((x, i) => (
                      <li key={i}>
                        {date(x.previous_due_date)} → {date(x.new_due_date)} · {name(x.approved_by.full_name_en, x.approved_by.full_name_ar)}
                        <span className="block text-muted-foreground">{x.reason}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
      {extending ? <ExtendDialog incidentId={incident.id} onClose={() => setExtending(false)} /> : null}
      {transitionTo ? <IncidentTransitionDialog incident={incident} to={transitionTo} onClose={() => setTransitionTo(null)} onDone={refresh} /> : null}
    </div>
  );
}

function InvestigationForm({ incident, inv, onDone }: { incident: Schemas["IncidentRead"]; inv: Schemas["InvestigationRead"]; onDone: () => void }) {
  const t = useTranslations("investigation");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const fe = useFieldErrorTranslator();
  const qc = useQueryClient();
  const ref = useRefLists();
  const users = useUserOptions(incident.project_id);
  const suggestions = useIncidentPermitSuggestions(incident.id);
  const linked = inv.ptws ?? [];
  // D-69: the legacy free-text ref is read-only once permits are linked.
  const refLocked = linked.length > 0;
  const [error, setError] = useState<unknown>(null);
  const form = useForm<Values>({
    defaultValues: {
      level: inv.level,
      lead_investigator_id: inv.lead_investigator?.id ?? "",
      team_member_ids: inv.team_members.map((u) => u.id),
      method: inv.method ?? "",
      preliminary_report: inv.preliminary_report ?? "",
      sequence_of_events: inv.sequence_of_events ?? "",
      immediate_causes: inv.immediate_causes ?? "",
      lessons_learned: inv.lessons_learned ?? "",
      ptw_involved: inv.ptw_involved ?? false,
      ptw_ref: inv.ptw_ref ?? "",
      ptw_ids: linked.map((p) => p.id),
      root_causes: inv.root_causes.map((r) => ({ code: r.code, text: r.text, linked_ca_ids: r.linked_ca_ids, no_action_justification: r.no_action_justification ?? "" })),
    },
  });
  const rcs = useFieldArray({ control: form.control, name: "root_causes" });
  const { isSubmitting, errors } = form.formState;
  const caOptions = incident.corrective_actions.map((c) => ({ value: c.id, label: `${c.ref} — ${c.title}` }));
  // Candidates: permits live in the zone at the time (suggestions) plus whatever is already linked.
  const ptwOptions = [
    ...linked.map((p) => ({ value: p.id, label: p.display_no })),
    ...(suggestions.data?.items ?? []).filter((x) => !linked.some((p) => p.id === x.permit.id)).map((x) => ({ value: x.permit.id, label: `${x.permit.display_no} · ${te(`permitStatus.${x.status_at_occurrence}`)}` })),
  ];
  const watched = useWatch({ control: form.control });
  const watchedLevel = watched.level;
  const watchedRcs = watched.root_causes ?? [];
  const allText = Object.values(watched).filter((x) => typeof x === "string").join(" ");

  async function save(v: Values) {
    setError(null);
    try {
      const next = await unwrap(
        api.PATCH("/api/v1/incidents/{incident_id}/investigation", {
          params: { path: { incident_id: incident.id } },
          body: {
            level: v.level,
            lead_investigator_id: v.lead_investigator_id || null,
            team_member_ids: v.team_member_ids,
            method: (v.method || null) as Schemas["InvestigationMethod"] | null,
            preliminary_report: v.preliminary_report.trim() || null,
            sequence_of_events: v.sequence_of_events.trim() || null,
            immediate_causes: v.immediate_causes.trim() || null,
            lessons_learned: v.lessons_learned.trim() || null,
            ptw_involved: v.ptw_involved || v.ptw_ids.length > 0,
            ptw_ids: v.ptw_ids,
            ...(refLocked ? {} : { ptw_ref: v.ptw_ref.trim() || null }),
            root_causes: v.root_causes
              .filter((r) => r.code)
              .map((r) => ({
                code: r.code as Schemas["RootCauseCode"],
                text: r.text.trim(),
                linked_ca_ids: r.linked_ca_ids,
                no_action_justification: r.linked_ca_ids.length ? null : r.no_action_justification.trim() || null,
              })),
          },
        }),
      );
      qc.setQueryData(hk.investigation(incident.id), next);
      await qc.invalidateQueries({ queryKey: hk.incident(incident.id) });
      toast.success(tc("saved"));
      onDone();
    } catch (e) {
      setError(e);
      applyServerErrors(e, form.setError, fe);
    }
  }

  return (
    <form onSubmit={form.handleSubmit(save)} noValidate className="flex max-w-4xl flex-col gap-6" data-testid="investigation-form">
      <FormSection title={t("edit")}>
        <FormField id="inv-level" label={t("fields.level")} required>
          <Select {...form.register("level")}>
            {INVESTIGATION_LEVELS.filter((l) => RANK[l] >= RANK[inv.minimum_level]).map((l) => (
              <option key={l} value={l}>
                {te(`investigationLevel.${l}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="inv-method" label={t("fields.method")}>
          <Select {...form.register("method")}>
            <option value="">{tc("select")}</option>
            {INVESTIGATION_METHODS.map((m) => (
              <option key={m} value={m}>
                {te(`investigationMethod.${m}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="inv-lead" label={t("fields.lead")} required>
          <UserSelect projectId={incident.project_id} {...form.register("lead_investigator_id")} />
        </FormField>
        <Controller
          control={form.control}
          name="team_member_ids"
          render={({ field }) => <MultiSelect id="inv-team" label={t("fields.team")} options={users} value={field.value} onChange={field.onChange} />}
        />
        {inv.level === "L3" || watchedLevel === "L3" ? (
          <FormField id="inv-prelim" label={t("fields.preliminary_report")} className="sm:col-span-2">
            <Textarea rows={3} maxLength={4000} {...form.register("preliminary_report")} />
          </FormField>
        ) : null}
        <FormField id="inv-seq" label={t("fields.sequence_of_events")} className="sm:col-span-2" error={errors.sequence_of_events?.message}>
          <Textarea rows={5} maxLength={4000} {...form.register("sequence_of_events")} />
        </FormField>
        <FormField id="inv-imm" label={t("fields.immediate_causes")} className="sm:col-span-2" error={errors.immediate_causes?.message}>
          <Textarea rows={3} maxLength={2000} {...form.register("immediate_causes")} />
        </FormField>
        <FormField id="inv-lessons" label={t("fields.lessons_learned")} className="sm:col-span-2" error={errors.lessons_learned?.message}>
          <Textarea rows={3} maxLength={2000} {...form.register("lessons_learned")} />
        </FormField>
        <CheckboxField id="inv-ptw" label={t("fields.ptw_involved")}>
          <Checkbox {...form.register("ptw_involved")} />
        </CheckboxField>
        <FormField id="inv-ptw-ref" label={t("fields.ptw_ref")} hint={refLocked ? t("ptwRefLocked") : undefined}>
          <Input className="ltr" maxLength={40} disabled={refLocked} {...form.register("ptw_ref")} />
        </FormField>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Controller
            control={form.control}
            name="ptw_ids"
            render={({ field }) => <MultiSelect id="inv-ptw-ids" label={t("fields.ptws")} options={ptwOptions} value={field.value} onChange={field.onChange} allLabel={tc("none")} className="lg:w-auto" testId="inv-ptw-ids" />}
          />
          <p className="text-xs text-muted-foreground">{suggestions.data && ptwOptions.length === 0 ? t("noPermitSuggestions") : t("ptwIdsHint")}</p>
        </div>
        <div className="sm:col-span-2">
          <PossibleIdHint text={allText} />
        </div>
      </FormSection>
      <FormSection title={t("rootCauses")}>
        <div className="flex flex-col gap-4 sm:col-span-2">
          {rcs.fields.map((f, i) => (
            <div key={f.id} className="grid gap-3 rounded-md border p-3 sm:grid-cols-2" data-testid="root-cause-row">
              <FormField id={`rc-${i}-code`} label={t("fields.code")} required>
                <Select {...form.register(`root_causes.${i}.code`)}>
                  <option value="">{tc("select")}</option>
                  {ref.options("root_cause").map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.value} — {o.label}
                    </option>
                  ))}
                </Select>
              </FormField>
              <Controller
                control={form.control}
                name={`root_causes.${i}.linked_ca_ids`}
                render={({ field }) => <MultiSelect id={`rc-${i}-cas`} label={t("linkedCas")} options={caOptions} value={field.value} onChange={field.onChange} />}
              />
              <FormField id={`rc-${i}-text`} label={t("fields.text")} required className="sm:col-span-2">
                <Textarea rows={2} maxLength={1000} {...form.register(`root_causes.${i}.text`)} />
              </FormField>
              {(watchedRcs[i]?.linked_ca_ids ?? []).length === 0 ? (
                <FormField id={`rc-${i}-noaction`} label={t("noAction")} className="sm:col-span-2">
                  <Textarea rows={2} maxLength={1000} {...form.register(`root_causes.${i}.no_action_justification`)} />
                </FormField>
              ) : null}
              <div className="sm:col-span-2">
                <Button type="button" size="sm" variant="ghost" onClick={() => rcs.remove(i)}>
                  <Trash2 aria-hidden />
                  {tc("delete")}
                </Button>
              </div>
            </div>
          ))}
          <div>
            <Button type="button" size="sm" variant="outline" onClick={() => rcs.append({ code: "", text: "", linked_ca_ids: [], no_action_justification: "" })} data-testid="add-root-cause">
              <Plus aria-hidden />
              {t("addRootCause")}
            </Button>
          </div>
        </div>
      </FormSection>
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={isSubmitting} data-testid="save-investigation">
          {isSubmitting ? tc("saving") : tc("save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

function ExtendDialog({ incidentId, onClose }: { incidentId: string; onClose: () => void }) {
  const t = useTranslations("investigation");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [due, setDue] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.POST("/api/v1/incidents/{incident_id}/investigation/extensions", { params: { path: { incident_id: incidentId } }, body: { new_due_date: due, reason: reason.trim() } }));
      qc.setQueryData(hk.investigation(incidentId), next);
      await qc.invalidateQueries({ queryKey: hk.incident(incidentId) });
      toast.success(tc("saved"));
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
          <DialogTitle>{t("extend")}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField id="ext-due" label={t("newDueDate")} required>
            <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </FormField>
          <FormField id="ext-reason" label={tc("reason")} required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
          </FormField>
          <MutationError error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !due || !reason.trim()}>
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
