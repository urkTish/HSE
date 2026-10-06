"use client";
import { Eye, EyeOff, Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useIncident, useInjuryCase } from "@/lib/api/hse";
import { useDisplay } from "@/lib/digits";
import { CASE_CATEGORIES } from "@/lib/enums";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useRefLists } from "@/lib/reference";
import { useFormatters } from "@/lib/use-formatters";

export function CaseDetail({ id }: { id: string }) {
  const t = useTranslations("cases");
  const ti = useTranslations("incidents");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const locale = useLocale();
  const me = useMeData();
  const qc = useQueryClient();
  const router = useRouter();
  const msg = useErrorMessage();
  const ref = useRefLists();
  const q = useInjuryCase(id);
  const inc = useIncident(q.data?.incident_id ?? "");
  const pid = inc.data?.project_id ?? null;
  const show = useDisplay(pid);
  const { date } = useFormatters(pid);
  const [fullId, setFullId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data || !inc.data) return <LoadingState />;
  const c = q.data;
  const incident = inc.data;
  const identity = !c.redacted_groups.includes("identity");
  const medical = !c.redacted_groups.includes("medical");
  const editable = canWrite(me, "incident.report", incident.project_id) && !["closed", "voided"].includes(incident.status);
  const canClassify = canWrite(me, "incident.classify", incident.project_id) && !["voided"].includes(incident.status);

  async function reveal() {
    try {
      const r = await unwrap(api.GET("/api/v1/injury-cases/{case_id}/id-number", { params: { path: { case_id: c.id } } }));
      setFullId(r.id_number ?? "—");
    } catch (e) {
      toast.error(msg(e));
    }
  }

  async function remove() {
    if (!window.confirm(tc("confirmDelete"))) return;
    try {
      await unwrap(api.DELETE("/api/v1/injury-cases/{case_id}", { params: { path: { case_id: c.id } } }));
      await qc.invalidateQueries({ queryKey: hk.incident(incident.id) });
      toast.success(tc("deleted"));
      router.push(`/incidents/${incident.id}`);
    } catch (e) {
      toast.error(msg(e));
    }
  }

  const label = locale === "ar" ? c.display_label_ar : c.display_label;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("incidents"), href: "/incidents" }, { label: incident.ref, href: `/incidents/${incident.id}` }, { label: c.case_no }]} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
              <div>
                <p className="ltr text-sm text-muted-foreground">{c.case_no}</p>
                <CardTitle data-testid="case-title">{label}</CardTitle>
              </div>
              <div className="flex gap-2">
                {editable ? (
                  <Button variant="outline" size="sm" asChild>
                    <Link href={`/injury-cases/${c.id}/edit`} data-testid="edit-case">
                      <Pencil aria-hidden />
                      {tc("edit")}
                    </Link>
                  </Button>
                ) : null}
                {editable && incident.status === "draft" ? (
                  <Button variant="outline" size="sm" onClick={() => void remove()}>
                    <Trash2 aria-hidden />
                    {tc("delete")}
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {c.redacted_groups.length > 0 ? (
                <Alert tone="info" data-testid="redaction-note">
                  {t("redacted", { groups: c.redacted_groups.map((g) => t(`groups.${g as "identity"}`)).join(", ") })}
                </Alert>
              ) : (
                <Alert tone="warning">{t("sensitiveNote")}</Alert>
              )}
              <ApiWarnings warnings={c.warnings} />
              <FieldList>
                <FieldItem label={t("fields.person_type")}>{te(`personType.${c.person_type}`)}</FieldItem>
                <FieldItem label={t("fields.employer")}>{c.employer ? <span className="ltr">{c.employer.short_code}</span> : "—"}</FieldItem>
                <FieldItem label={t("fields.trade")}>{ref.label("trade", c.trade)}</FieldItem>
                <FieldItem label={t("fields.mechanism")}>{ref.label("mechanism", c.mechanism)}</FieldItem>
                <FieldItem label={t("fields.agency")}>{ref.label("agency", c.agency)}</FieldItem>
                <FieldItem label={t("fields.commuting")}>
                  <YesNo value={c.commuting} yes={tc("yes")} no={tc("no")} />
                </FieldItem>
              </FieldList>
            </CardContent>
          </Card>
          {identity ? (
            <Card data-testid="identity-card">
              <CardHeader>
                <CardTitle>{t("identity")}</CardTitle>
              </CardHeader>
              <CardContent>
                <FieldList>
                  <FieldItem label={t("fields.person_name")}>
                    <span data-testid="person-name">{c.person_name}</span>
                  </FieldItem>
                  <FieldItem label={t("fields.id_number")}>
                    <span className="inline-flex flex-wrap items-center gap-2">
                      <span className="ltr" data-testid="id-number">
                        {c.id_type ? `${te(`idType.${c.id_type}`)} · ` : ""}
                        {fullId ?? c.id_number_masked ?? "—"}
                      </span>
                      {c.id_number_masked ? (
                        fullId ? (
                          <Button size="sm" variant="ghost" onClick={() => setFullId(null)}>
                            <EyeOff aria-hidden />
                            {t("hideId")}
                          </Button>
                        ) : (
                          <Button size="sm" variant="ghost" onClick={() => void reveal()} data-testid="reveal-id">
                            <Eye aria-hidden />
                            {t("revealId")}
                          </Button>
                        )
                      ) : null}
                    </span>
                  </FieldItem>
                  <FieldItem label={t("fields.employee_no")} ltr>
                    {c.employee_no}
                  </FieldItem>
                  <FieldItem label={t("fields.nationality")} ltr>
                    {c.nationality}
                  </FieldItem>
                  <FieldItem label={t("fields.age_band")}>{c.age_band ? te(`ageBand.${c.age_band}`) : "—"}</FieldItem>
                  <FieldItem label={t("fields.site_start_date")}>{date(c.site_start_date)}</FieldItem>
                  <FieldItem label={t("fields.days_on_site")}>{show(c.days_on_site)}</FieldItem>
                  <FieldItem label={t("fields.hours_into_shift")}>{show(c.hours_into_shift)}</FieldItem>
                  <FieldItem label={t("fields.gosi_case_ref")} ltr>
                    {c.gosi_case_ref}
                  </FieldItem>
                </FieldList>
              </CardContent>
            </Card>
          ) : null}
          {medical ? (
            <Card data-testid="medical-card">
              <CardHeader>
                <CardTitle>{t("medical")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <FieldList>
                  <FieldItem label={t("fields.body_part")}>
                    {ref.label("body_part", c.body_part)}
                    {c.body_side ? ` (${te(`bodySide.${c.body_side}`)})` : ""}
                  </FieldItem>
                  <FieldItem label={t("fields.nature")}>{ref.label("nature", c.nature)}</FieldItem>
                  <FieldItem label={t("fields.treated_at")}>{c.treated_at ? te(`treatedAt.${c.treated_at}`) : "—"}</FieldItem>
                  <FieldItem label={t("fields.treatments")} wide>
                    {(c.treatments ?? []).map((x) => ref.label("treatment", x)).join(" · ") || "—"}
                  </FieldItem>
                  <FieldItem label={t("fields.illness")}>
                    <YesNo value={c.illness} yes={tc("yes")} no={tc("no")} />
                  </FieldItem>
                  <FieldItem label={t("fields.loss_of_consciousness")}>
                    <YesNo value={c.loss_of_consciousness} yes={tc("yes")} no={tc("no")} />
                  </FieldItem>
                  <FieldItem label={t("fields.fatal")}>
                    <YesNo value={c.fatal} yes={tc("yes")} no={tc("no")} />
                    {c.fatal && c.date_of_death ? ` · ${date(c.date_of_death)}` : ""}
                  </FieldItem>
                  <FieldItem label={t("fields.permanent_disability")}>{c.permanent_disability ? te(`permanentDisability.${c.permanent_disability}`) : "—"}</FieldItem>
                  <FieldItem label={t("fields.privacy_case")}>
                    <YesNo value={c.privacy_case} yes={tc("yes")} no={tc("no")} />
                    {c.privacy_case && c.privacy_reason ? ` · ${te(`privacyReason.${c.privacy_reason}`)}` : ""}
                  </FieldItem>
                  <FieldItem label={t("fields.away_start_date")}>{date(c.away_start_date)}</FieldItem>
                  <FieldItem label={t("fields.rtw_date")}>{date(c.rtw_date)}</FieldItem>
                  <FieldItem label={t("fields.restricted_start")}>
                    {c.restricted_start ? `${date(c.restricted_start)} – ${date(c.restricted_end)}` : "—"}
                  </FieldItem>
                  <FieldItem label={t("fields.transfer_start")}>{c.transfer_start ? `${date(c.transfer_start)} – ${date(c.transfer_end)}` : "—"}</FieldItem>
                  <FieldItem label={t("fields.medical_notes")} wide>
                    <span className="whitespace-pre-wrap">{c.medical_notes ?? "—"}</span>
                  </FieldItem>
                </FieldList>
                {c.day_counts ? (
                  <div className="rounded-md border p-3" data-testid="day-counts">
                    <p className="mb-2 text-sm font-medium">{t("dayCounts", { date: date(c.day_counts.as_of) })}</p>
                    <FieldList>
                      <FieldItem label={t("daysAway")}>{show(c.day_counts.days_away)}</FieldItem>
                      <FieldItem label={t("restrictedDays")}>{show(c.day_counts.restricted_days)}</FieldItem>
                      <FieldItem label={t("transferDays")}>{show(c.day_counts.transfer_days)}</FieldItem>
                      <FieldItem label={t("lostCharged")}>
                        {show(c.day_counts.lost_days_charged)}
                        {c.day_counts.capped ? ` (${t("capped")})` : ""}
                      </FieldItem>
                    </FieldList>
                  </div>
                ) : null}
                <div>
                  <p className="mb-2 text-sm font-medium">{t("medicalAttachments")}</p>
                  <Attachments ownerType="injury_case_medical" ownerId={c.id} canUpload={editable} canDelete={editable} hint={t("medicalAttachHint")} />
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
        <div className="flex flex-col gap-6">
          <Card data-testid="classification-card">
            <CardHeader>
              <CardTitle>{t("classification")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <FieldList className="lg:grid-cols-1">
                <FieldItem label={t("effective")}>
                  <span className="inline-flex flex-wrap items-center gap-1" data-testid="case-category">
                    <span className="font-medium">{te(`caseCategory.${c.case_category}`)}</span>
                    <StatusBadge status={c.classification_status} label={te(`classificationStatus.${c.classification_status}`)} />
                    {c.open_lti ? <StatusBadge status="warning" label={ti("openLti")} /> : null}
                  </span>
                </FieldItem>
                <FieldItem label={t("derived")}>{te(`caseCategory.${c.derived_category}`)}</FieldItem>
                {c.category_override_justification ? (
                  <FieldItem label={t("override")}>
                    <span className="whitespace-pre-wrap">{c.category_override_justification}</span>
                  </FieldItem>
                ) : null}
                {c.excluded_from_rates ? (
                  <FieldItem label={t("fields.exclusion")}>{c.exclusion_reasons.map((x) => te(`rateExclusion.${x}`)).join(" · ")}</FieldItem>
                ) : null}
              </FieldList>
              {canClassify ? (
                <Button size="sm" onClick={() => setConfirming(true)} data-testid="confirm-classification">
                  <ShieldCheck aria-hidden />
                  {t("confirm")}
                </Button>
              ) : null}
            </CardContent>
          </Card>
          {can(me, "history.view", incident.project_id) ? <HistoryPanel entityType="injury_case" entityId={c.id} projectId={incident.project_id} /> : null}
        </div>
      </div>
      {confirming ? <ClassifyDialog kase={c} onClose={() => setConfirming(false)} /> : null}
    </div>
  );
}

function ClassifyDialog({ kase: c, onClose }: { kase: Schemas["InjuryCaseRead"]; onClose: () => void }) {
  const t = useTranslations("cases");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const qc = useQueryClient();
  const [cat, setCat] = useState<Schemas["CaseCategory"]>(c.case_category);
  const [just, setJust] = useState(c.category_override_justification ?? "");
  const [justErr, setJustErr] = useState<string>();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const differs = cat !== c.derived_category;
  async function submit() {
    if (differs && just.trim().length < 20) {
      setJustErr(tv("minChars", { min: 20 }));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(
        api.POST("/api/v1/injury-cases/{case_id}/classification", { params: { path: { case_id: c.id } }, body: { case_category: cat, justification: differs ? just.trim() : null } }),
      );
      qc.setQueryData(hk.injuryCase(c.id), next);
      await qc.invalidateQueries({ queryKey: hk.incident(c.incident_id) });
      await qc.invalidateQueries({ queryKey: ["incidents"] });
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
          <DialogTitle>{t("confirmTitle")}</DialogTitle>
          <DialogDescription>
            {t("derived")}: {te(`caseCategory.${c.derived_category}`)}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <FormField id="classify-cat" label={t("fields.case_category")} required>
            <Select value={cat} onChange={(e) => setCat(e.target.value as Schemas["CaseCategory"])} data-testid="classify-category">
              {CASE_CATEGORIES.map((x) => (
                <option key={x} value={x}>
                  {te(`caseCategory.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          {differs ? (
            <FormField id="classify-just" label={t("justification")} hint={t("justificationHint")} required error={justErr}>
              <Textarea value={just} onChange={(e) => setJust(e.target.value)} maxLength={1000} />
            </FormField>
          ) : null}
          <MutationError error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={busy} data-testid="classify-save">
            {t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
