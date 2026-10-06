"use client";
import { CalendarPlus, Plus, Trash2 } from "lucide-react";
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
import { hk, useIncident, useInvestigation } from "@/lib/api/hse";
import { INVESTIGATION_LEVELS, INVESTIGATION_METHODS } from "@/lib/enums";
import { applyServerErrors } from "@/lib/forms";
import { useFieldErrorTranslator, useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { useRefLists } from "@/lib/reference";
import { useFormatters } from "@/lib/use-formatters";

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
  root_causes: { code: string; text: string; linked_ca_ids: string[]; no_action_justification: string }[];
}

export function InvestigationPage({ id }: { id: string }) {
  const t = useTranslations("investigation");
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
  if (inc.isError) return <ErrorState error={inc.error} onRetry={() => inc.refetch()} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (inc.data && !inc.data.investigation) return <Alert tone="info">{te(`investigationLevel.${inc.data.minimum_investigation_level}`)}</Alert>;
  if (!inc.data || !q.data) return <LoadingState />;
  const incident = inc.data;
  const v = q.data;
  const canEdit = canWrite(me, "investigation.edit", incident.project_id) && ["under_investigation", "reported"].includes(incident.status);
  const canExtend = canWrite(me, "investigation.approve", incident.project_id) && !["closed", "voided"].includes(incident.status);
  const caById = new Map(incident.corrective_actions.map((c) => [c.id, c]));

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
                <div className="flex gap-2">
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
                        <li key={m}>{t.has(`fields.${m as "level"}`) ? t(`fields.${m as "level"}`) : m}</li>
                      ))}
                    </ul>
                  </Alert>
                ) : null}
                <FieldList>
                  <FieldItem label={t("fields.level")}>
                    {te(`investigationLevel.${v.level}`)} (min {v.minimum_level})
                  </FieldItem>
                  <FieldItem label={t("fields.lead")}>{v.lead_investigator ? name(v.lead_investigator.full_name_en, v.lead_investigator.full_name_ar) : "—"}</FieldItem>
                  <FieldItem label={t("fields.team")}>{v.team_members.map((u) => name(u.full_name_en, u.full_name_ar)).join(", ") || "—"}</FieldItem>
                  <FieldItem label={t("fields.method")}>{v.method ? te(`investigationMethod.${v.method}`) : "—"}</FieldItem>
                  <FieldItem label={t("fields.due_date")}>{date(v.due_date)}</FieldItem>
                  {v.preliminary_report_due_at ? <FieldItem label={t("fields.preliminary_due")}>{dateTime(v.preliminary_report_due_at)}</FieldItem> : null}
                  <FieldItem label={t("fields.ptw_involved")}>
                    <YesNo value={v.ptw_involved} yes={tc("yes")} no={tc("no")} />
                    {v.ptw_ref ? <span className="ltr"> · {v.ptw_ref}</span> : null}
                  </FieldItem>
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
      root_causes: inv.root_causes.map((r) => ({ code: r.code, text: r.text, linked_ca_ids: r.linked_ca_ids, no_action_justification: r.no_action_justification ?? "" })),
    },
  });
  const rcs = useFieldArray({ control: form.control, name: "root_causes" });
  const { isSubmitting, errors } = form.formState;
  const caOptions = incident.corrective_actions.map((c) => ({ value: c.id, label: `${c.ref} — ${c.title}` }));
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
            ptw_involved: v.ptw_involved,
            ptw_ref: v.ptw_ref.trim() || null,
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
        <FormField id="inv-ptw-ref" label={t("fields.ptw_ref")}>
          <Input className="ltr" maxLength={40} {...form.register("ptw_ref")} />
        </FormField>
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
