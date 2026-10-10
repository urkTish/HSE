"use client";
import { Download, FilePen, FilePlus2, Lock, Paperclip, Plus, Stamp, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Code, StepDialog } from "@/components/access/common";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { RecordActions } from "@/components/common/record-actions";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Choices, DayDue } from "@/components/followup/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useEngagements, useUsers } from "@/lib/api/queries";
import { useDistributionList, usePackDeliveries, useReportPack, useReportPacks, useScRefresh } from "@/lib/api/scorecard";
import { useDisplay } from "@/lib/digits";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ReportsSubNav, ScBadge, previousMonth, recentMonths, usePeriodLabel, useScCaps, useScRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Pack = S["RpPackDetail"];

const TYPES: S["RpType"][] = ["MCR", "SCP", "OSHA300", "HEAT", "CPS"];
const PROJECT_TYPES: S["RpType"][] = ["MCR", "SCP", "OSHA300", "HEAT"];
const STATUSES: S["RpStatus"][] = ["draft", "in_review", "issued", "superseded"];
const PURPOSES: S["XpPurpose"][] = ["gosi", "mhrsd", "client_report", "legal", "insurance", "audit", "data_subject_request", "internal_analysis", "other"];

/* ═════════════ report-pack register with revisions (§8.3) ═════════════ */

export function ReportPacksPage() {
  return <ProjectGate>{(p) => <Register project={p} />}</ProjectGate>;
}

function Register({ project }: { project: Project }) {
  const t = useTranslations("rp.register");
  const td = useTranslations("scDesign.pack");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const ref = useScRef();
  const period = usePeriodLabel(project.id);
  const caps = useScCaps(project.id);
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const type = (s.get("type") as S["RpType"] | null) ?? "";
  const status = (s.get("status") as S["RpStatus"] | null) ?? "";
  const q = useReportPacks(project.id, { report_type: type || null, status: status || null, page_size: 200 }, { enabled: caps.packs });
  const [create, setCreate] = useState(false);
  if (!caps.packs) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.prepare ? (
            <Button onClick={() => setCreate(true)} data-testid="rp-new">
              <FilePlus2 aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <ReportsSubNav />
      <ListToolbar>
        <SelectFilter id="rp-type" label={t("type")} value={type} onChange={(v) => s.set({ type: v || null })} options={PROJECT_TYPES.map((x) => ({ value: x, label: `${x} · ${ref.label("report_types", x)}` }))} />
        <SelectFilter id="rp-status" label={t("status")} value={status} onChange={(v) => s.set({ status: v || null })} options={STATUSES.map((x) => ({ value: x, label: te(`rpStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="rp-list">
          <THead>
            <TR>
              <TH>{t("docNo")}</TH>
              <TH>{t("type")}</TH>
              <TH>{t("period")}</TH>
              <TH>{t("status")}</TH>
              <TH>{t("due")}</TH>
              <TH>{t("issued")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((p) => (
              <TR key={p.id} data-testid="rp-row" data-doc={p.doc_no} data-revision={p.revision} data-status={p.status}>
                <TD label={t("docNo")}>
                  <Link href={`/report-packs/${p.id}`} className="text-primary hover:underline">
                    <Code>{p.doc_no}</Code>
                  </Link>{" "}
                  <span className="text-xs text-muted-foreground">{t("rev", { n: show(String(p.revision)) })}</span>
                  {p.revised_since_issue ? <span className="block text-xs text-warning">{t("revised")}</span> : null}
                </TD>
                <TD label={t("type")}>{ref.label("report_types", p.report_type)}</TD>
                <TD label={t("period")}>
                  <bdi>{period(p.period_start, p.period_end)}</bdi>
                </TD>
                <TD label={t("status")}>
                  <ScBadge group="rpStatus" status={p.status} />
                  {p.status === "draft" || p.status === "in_review" ? <span className="block text-xs text-muted-foreground">{td("notIssuedShort")}</span> : null}
                </TD>
                <TD label={t("due")}>{p.due_on ? <DayDue date={p.due_on} open={p.status === "draft" || p.status === "in_review"} projectId={project.id} /> : "—"}</TD>
                <TD label={t("issued")}>{p.issued_at ? dateTime(p.issued_at) : "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {create ? <CreatePackDialog project={project} onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

function CreatePackDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("rp.create");
  const te = useTranslations("enums");
  const tf = useTranslations("fu.common");
  const ref = useScRef();
  const router = useRouter();
  const refresh = useScRefresh();
  const caps = useScCaps(project.id);
  const engs = useEngagements(project.id, { page_size: 200 });
  const [type, setType] = useState<S["RpType"]>("MCR");
  const [month, setMonth] = useState(previousMonth());
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [eng, setEng] = useState("");
  const [names, setNames] = useState(false);
  const [purpose, setPurpose] = useState<S["XpPurpose"] | "">("");
  const [purposeText, setPurposeText] = useState("");
  const monthly = type === "MCR" || type === "SCP";
  const ok = (type !== "SCP" || Boolean(eng)) && (!names || Boolean(purpose));
  return (
    <StepDialog
      title={t("title")}
      description={t("body")}
      confirmLabel={t("confirm")}
      testId="rp-create-confirm"
      wide
      disabled={!ok}
      onConfirm={async () => {
        const pk = await unwrap(
          api.POST("/api/v1/report-packs", {
            body: {
              report_type: type,
              project_id: project.id,
              engagement_id: type === "SCP" ? eng : null,
              month: monthly ? month : null,
              year: monthly ? null : Number(year),
              with_names: type === "OSHA300" ? names : false,
              purpose: names ? (purpose as S["XpPurpose"]) : null,
              purpose_text: names && purposeText.trim() ? purposeText.trim() : null,
            },
          }),
        );
        await refresh();
        toast.success(t("done", { no: pk.doc_no }));
        router.push(`/report-packs/${pk.id}`);
      }}
      onClose={onClose}
    >
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-sm font-medium">{t("type")}</legend>
        <Choices label={t("type")} testId="rp-type-choice" value={type} options={PROJECT_TYPES.map((x) => ({ value: x, label: ref.label("report_types", x) }))} onChange={setType} />
      </fieldset>
      {monthly ? (
        <FormField id="rp-month" label={t("month")} required>
          <Select id="rp-month" value={month} onChange={(e) => setMonth(e.target.value)} data-testid="rp-month">
            {recentMonths(15).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </FormField>
      ) : (
        <FormField id="rp-year" label={t("year")} required hint={type === "OSHA300" ? t("ytdHint") : undefined}>
          <Input id="rp-year" type="number" className="ltr w-32" value={year} onChange={(e) => setYear(e.target.value)} data-testid="rp-year" />
        </FormField>
      )}
      {type === "SCP" ? (
        <FormField id="rp-eng" label={t("engagement")} required>
          <Select id="rp-eng" value={eng} onChange={(e) => setEng(e.target.value)} data-testid="rp-engagement">
            <option value="">—</option>
            {(engs.data?.items ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.contractor.short_code}
              </option>
            ))}
          </Select>
        </FormField>
      ) : null}
      {type === "OSHA300" ? (
        <div className="flex flex-col gap-2 rounded-md border p-3">
          <p className="text-sm text-muted-foreground">{t("oshaNote")}</p>
          {caps.me && caps.manage ? (
            <label className="flex min-h-touch items-center gap-3 text-sm">
              <Checkbox checked={names} onChange={(e) => setNames(e.target.checked)} data-testid="rp-with-names" />
              {t("withNames")}
            </label>
          ) : null}
          {names ? (
            <>
              <Alert tone="warning">{t("namesWarning")}</Alert>
              <FormField id="rp-purpose" label={t("purpose")} required>
                <Select id="rp-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value as S["XpPurpose"])} data-testid="rp-purpose">
                  <option value="">—</option>
                  {PURPOSES.map((p) => (
                    <option key={p} value={p}>
                      {te(`xpPurpose.${p}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              {purpose === "other" ? (
                <FormField id="rp-purpose-text" label={t("purposeText")} required hint={tf("reasonMin", { min: 20, n: purposeText.trim().length })}>
                  <Input id="rp-purpose-text" value={purposeText} onChange={(e) => setPurposeText(e.target.value)} />
                </FormField>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </StepDialog>
  );
}

/* ═════════════ one pack: control data, files, cycle, sections, delivery log (§4.4, RP-1…RP-10) ═════════════ */

export function ReportPackPage({ id }: { id: string }) {
  const t = useTranslations("rp.pack");
  const td = useTranslations("scDesign.pack");
  const tn = useTranslations("sc.nav");
  const ref = useScRef();
  const name = useLocalizedName();
  const q = useReportPack(id);
  const pk = q.data;
  const caps = useScCaps(pk?.project_id);
  const show = useDisplay(pk?.project_id);
  const period = usePeriodLabel(pk?.project_id);
  const { dateTime } = useFormatters(pk?.project_id);
  const refresh = useScRefresh();
  const [dialog, setDialog] = useState<"issue" | "return" | "reissue" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!pk) return <LoadingState />;
  const isCps = pk.report_type === "CPS";
  const prepare = isCps ? Boolean(caps.me?.is_hse_manager) : caps.prepare;
  const issue = isCps ? Boolean(caps.me?.is_hse_manager) : caps.issue;
  const reviewed = Boolean(pk.reviewed_by);
  const selfReview = reviewed && pk.reviewed_by?.id === caps.me?.id;

  async function act(action: S["RpAction"], done: string) {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/report-packs/{pack_id}/transitions", { params: { path: { pack_id: pk!.id } }, body: { action, scorecards_provisional: false, remove_xlsx_for_externals: false } }));
      await refresh();
      toast.success(done);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function download(kind: S["RpFileKind"]) {
    setError(null);
    try {
      const u = await unwrap(api.GET("/api/v1/report-packs/{pack_id}/files/{kind}/url", { params: { path: { pack_id: pk!.id, kind } } }));
      window.open(u.url, "_blank", "noopener");
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: tn("packs"), href: "/report-packs" }, { label: `${pk.doc_no} Rev ${pk.revision}` }]} />
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">
          <Code data-testid="rp-doc-no">{pk.doc_no}</Code> · {t("rev", { n: show(String(pk.revision)) })}
        </p>
        <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
          {ref.label("report_types", pk.report_type)}
          <ScBadge group="rpStatus" status={pk.status} testId="rp-status" />
        </h1>
      </div>
      {pk.status === "superseded" ? (
        <Alert tone="warning" data-testid="rp-superseded">
          {t("superseded", { n: pk.superseded_by_revision ?? "" })}
        </Alert>
      ) : null}
      {pk.revised_since_issue ? (
        <Alert tone="warning" data-testid="rp-revised">
          <span className="flex flex-col gap-2">
            {t("revisedSinceIssue")}
            {issue && pk.status === "issued" ? (
              <Button size="sm" variant="outline" className="w-fit" onClick={() => setDialog("reissue")}>
                {t("reissue")}
              </Button>
            ) : null}
          </span>
        </Alert>
      ) : null}
      {pk.with_names ? <Alert tone="warning">{t("withNames")}</Alert> : null}
      {pk.status === "draft" || pk.status === "in_review" ? (
        <div className="flex items-start gap-2.5 rounded-lg border-2 border-dashed border-border bg-muted/40 p-3 text-sm" data-testid="rp-state" data-state="not_issued">
          <FilePen aria-hidden className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
          <span className="flex flex-col gap-0.5">
            <span className="font-semibold">{td(pk.status === "draft" ? "draftTitle" : "reviewTitle")}</span>
            <span className="text-muted-foreground">{td(pk.status === "draft" ? "draftBody" : "reviewBody")}</span>
          </span>
        </div>
      ) : null}
      {pk.status === "issued" ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-success/40 bg-success-bg p-3 text-sm" data-testid="rp-state" data-state="issued">
          <Lock aria-hidden className="mt-0.5 size-5 shrink-0 text-success" />
          <span className="flex flex-col gap-0.5">
            <span className="font-semibold">
              {pk.issued_at ? td("issuedTitle", { at: dateTime(pk.issued_at), by: pk.issued_by ? name(pk.issued_by.full_name_en, pk.issued_by.full_name_ar) : "—" }) : td("issuedTitleShort")}
            </span>
            <span className="text-muted-foreground">{t("immutable")}</span>
          </span>
        </div>
      ) : null}
      {pk.scorecards_provisional ? (
        <div className="flex items-start gap-2.5 rounded-lg border-2 border-warning bg-warning-bg p-3 text-sm" data-testid="rp-provisional-banner">
          <Stamp aria-hidden className="mt-0.5 size-5 shrink-0 text-warning" />
          <span className="flex flex-col gap-0.5">
            <span className="font-semibold uppercase tracking-wide">{td("provisionalTitle")}</span>
            <span>{td("provisionalBody")}</span>
          </span>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("control")}</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={t("period")}>
              <bdi>{period(pk.period_start, pk.period_end)}</bdi>
              <bdi className="ltr block font-mono text-xs text-muted-foreground">
                {pk.period_start} → {pk.period_end}
              </bdi>
            </FieldItem>
            <FieldItem label={t("due")}>{pk.due_on ? <DayDue date={pk.due_on} open={pk.status === "draft" || pk.status === "in_review"} projectId={pk.project_id} /> : "—"}</FieldItem>
            <FieldItem label={t("prepared")}>
              {pk.prepared_by ? name(pk.prepared_by.full_name_en, pk.prepared_by.full_name_ar) : t("system")} · {pk.prepared_at ? dateTime(pk.prepared_at) : "—"}
            </FieldItem>
            <FieldItem label={t("reviewed")}>
              <span data-testid="rp-reviewed">{pk.reviewed_by ? `${name(pk.reviewed_by.full_name_en, pk.reviewed_by.full_name_ar)} · ${pk.reviewed_at ? dateTime(pk.reviewed_at) : ""}` : "—"}</span>
            </FieldItem>
            <FieldItem label={t("issuedBy")}>{pk.issued_by ? `${name(pk.issued_by.full_name_en, pk.issued_by.full_name_ar)} · ${pk.issued_at ? dateTime(pk.issued_at) : ""}` : "—"}</FieldItem>
            <FieldItem label={t("hash")} ltr>
              {pk.snapshot_hash ? pk.snapshot_hash.slice(0, 12) : "—"}
            </FieldItem>
            {pk.scorecards_provisional ? (
              <FieldItem label={t("provisional")} wide>
                {pk.provisional_reason}
              </FieldItem>
            ) : null}
            {pk.review_comment ? (
              <FieldItem label={t("reviewComment")} wide>
                {pk.review_comment}
              </FieldItem>
            ) : null}
            {pk.reissue_reason ? (
              <FieldItem label={t("reissueReason")} wide>
                {pk.reissue_reason}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>

      {pk.files.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("files")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2" data-testid="rp-files">
              {pk.files.map((f) => (
                <li key={f.kind} className="flex flex-wrap items-center gap-3" data-testid="rp-file" data-kind={f.kind}>
                  <Button variant="outline" size="sm" onClick={() => void download(f.kind)}>
                    <Download aria-hidden />
                    {t(`file.${f.kind}`)}
                  </Button>
                  <bdi className="ltr text-xs text-muted-foreground">
                    {f.file_name} · {(f.size_bytes / 1024).toFixed(0)} KB · {f.sha256.slice(0, 12)}
                  </bdi>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Snapshot pack={pk} />
      {pk.status === "issued" || pk.status === "superseded" ? <Deliveries packId={pk.id} projectId={pk.project_id} /> : null}

      <MutationError error={error} />
      {(prepare && (pk.status === "draft" || pk.status === "in_review")) ? (
        <div className="flex flex-wrap gap-2 border-t pt-4" data-testid="rp-actions">
          {pk.status === "draft" ? (
            <>
              <Button variant="outline" disabled={busy} onClick={() => void act("regenerate", t("regenerated"))} data-testid="rp-regenerate">
                {t("regenerate")}
              </Button>
              <Button disabled={busy} onClick={() => void act("submit_for_review", t("submitted"))} data-testid="rp-submit">
                {t("submit")}
              </Button>
            </>
          ) : null}
          {pk.status === "in_review" ? (
            <>
              <Button variant="outline" disabled={busy} onClick={() => setDialog("return")} data-testid="rp-return">
                {t("returnToDraft")}
              </Button>
              {!reviewed ? (
                <Button variant="outline" disabled={busy} onClick={() => void act("review", t("reviewedDone"))} data-testid="rp-review">
                  {t("review")}
                </Button>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
      {issue && (pk.status === "in_review" || pk.status === "issued") ? (
        <RecordActions label={pk.status === "issued" ? td("endReissue") : td("endIssue")} testId="rp-end">
          {pk.status === "in_review" ? (
            <>
              {!reviewed || selfReview ? <p className="w-full text-xs text-muted-foreground">{t("reviewerRule")}</p> : null}
              <Button disabled={busy} onClick={() => setDialog("issue")} data-testid="rp-issue">
                <Lock aria-hidden />
                {t("issue")}
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={() => setDialog("reissue")} data-testid="rp-reissue">
              {t("reissue")}
            </Button>
          )}
        </RecordActions>
      ) : null}
      {dialog === "issue" ? <IssueDialog pack={pk} onClose={() => setDialog(null)} /> : null}
      {dialog === "return" ? <ReturnDialog pack={pk} onClose={() => setDialog(null)} /> : null}
      {dialog === "reissue" ? <ReissueDialog pack={pk} onClose={() => setDialog(null)} /> : null}
    </div>
  );
}

function IssueDialog({ pack, onClose }: { pack: Pack; onClose: () => void }) {
  const t = useTranslations("rp.pack");
  const tf = useTranslations("fu.common");
  const refresh = useScRefresh();
  const [prov, setProv] = useState(false);
  const [reason, setReason] = useState("");
  const [noXlsx, setNoXlsx] = useState(false);
  const mcr = pack.report_type === "MCR";
  return (
    <StepDialog
      title={t("issueTitle", { no: pack.doc_no })}
      description={t("issueBody")}
      confirmLabel={t("issue")}
      testId="rp-issue-confirm"
      wide
      disabled={prov && reason.trim().length < 20}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/report-packs/{pack_id}/transitions", {
            params: { path: { pack_id: pack.id } },
            body: { action: "issue", scorecards_provisional: mcr ? prov : false, provisional_reason: prov ? reason.trim() : null, remove_xlsx_for_externals: noXlsx },
          }),
        );
        await refresh();
        toast.success(t("issued"));
      }}
      onClose={onClose}
    >
      {mcr ? (
        <div className="flex flex-col gap-2 rounded-md border p-3">
          <label className="flex min-h-touch items-center gap-3 text-sm">
            <Checkbox checked={prov} onChange={(e) => setProv(e.target.checked)} data-testid="rp-provisional" />
            {t("provisionalCheck")}
          </label>
          <p className="text-xs text-muted-foreground">{t("provisionalHint")}</p>
          {prov ? (
            <FormField id="rp-prov-reason" label={tf("reason")} required hint={tf("reasonMin", { min: 20, n: reason.trim().length })}>
              <Textarea id="rp-prov-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="rp-provisional-reason" />
            </FormField>
          ) : null}
        </div>
      ) : null}
      <label className="flex min-h-touch items-center gap-3 text-sm">
        <Checkbox checked={noXlsx} onChange={(e) => setNoXlsx(e.target.checked)} data-testid="rp-no-xlsx" />
        {t("noXlsx")}
      </label>
    </StepDialog>
  );
}

function ReturnDialog({ pack, onClose }: { pack: Pack; onClose: () => void }) {
  const t = useTranslations("rp.pack");
  const refresh = useScRefresh();
  const [comment, setComment] = useState("");
  return (
    <StepDialog
      title={t("returnToDraft")}
      confirmLabel={t("returnToDraft")}
      testId="rp-return-confirm"
      disabled={comment.trim().length < 5}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/report-packs/{pack_id}/transitions", { params: { path: { pack_id: pack.id } }, body: { action: "return_to_draft", comment: comment.trim(), scorecards_provisional: false, remove_xlsx_for_externals: false } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="rp-return-comment" label={t("reviewComment")} required>
        <Textarea id="rp-return-comment" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} data-testid="rp-return-comment" />
      </FormField>
    </StepDialog>
  );
}

function ReissueDialog({ pack, onClose }: { pack: Pack; onClose: () => void }) {
  const t = useTranslations("rp.pack");
  const tf = useTranslations("fu.common");
  const refresh = useScRefresh();
  const router = useRouter();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("reissueTitle", { no: pack.doc_no })}
      description={t("reissueBody")}
      confirmLabel={t("reissue")}
      testId="rp-reissue-confirm"
      disabled={reason.trim().length < 20}
      onConfirm={async () => {
        const n = await unwrap(api.POST("/api/v1/report-packs/{pack_id}/reissue", { params: { path: { pack_id: pack.id } }, body: { reason: reason.trim() } }));
        await refresh();
        router.push(`/report-packs/${n.id}`);
      }}
      onClose={onClose}
    >
      <FormField id="rp-reissue-reason" label={tf("reason")} required hint={tf("reasonMin", { min: 20, n: reason.trim().length })}>
        <Textarea id="rp-reissue-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="rp-reissue-reason" />
      </FormField>
    </StepDialog>
  );
}

/** The frozen numbers (RP-2): sections in RP-1 order, each with its tables, exactly as stored. */
type Col = [string, string, string];
type SnapTable = { title_en?: string; title_ar?: string; columns?: Col[]; rows?: Record<string, unknown>[] };
type SnapSection = { key: string; title_en?: string; title_ar?: string; watermark?: string | null; paragraphs_en?: string[]; paragraphs_ar?: string[]; tables?: SnapTable[] };

function Snapshot({ pack }: { pack: Pack }) {
  const t = useTranslations("rp.pack");
  const ar = useLocale() === "ar";
  const snap = pack.snapshot as { sections?: SnapSection[]; not_live?: string[] };
  const sections = snap.sections ?? [];
  if (!sections.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("contents")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("contentsHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {sections.map((s, i) => (
          <details key={`${s.key}-${i}`} className="rounded-md border" data-testid="rp-section" data-key={s.key}>
            <summary className="flex min-h-touch cursor-pointer flex-wrap items-center gap-2 px-3 py-1 text-sm font-medium">
              <span className="text-muted-foreground tabular-nums">{i + 1}.</span>
              {(ar ? s.title_ar : s.title_en) || s.key}
              {s.watermark ? (
                <span className="inline-flex items-center gap-1 rounded border border-warning/50 bg-warning-bg px-1.5 py-0.5 text-xs font-semibold text-warning" data-testid="rp-watermark">
                  <Stamp aria-hidden className="size-3.5" />
                  {s.watermark}
                </span>
              ) : null}
            </summary>
            <div className="flex flex-col gap-3 overflow-x-auto px-3 pb-3">
              {(ar ? s.paragraphs_ar : s.paragraphs_en)?.map((p, j) => (
                <p key={j} className="text-sm">
                  {p}
                </p>
              ))}
              {(s.tables ?? []).map((tb, j) => (
                <div key={j}>
                  {(ar ? tb.title_ar : tb.title_en) ? <p className="mb-1 text-xs font-semibold text-muted-foreground">{ar ? tb.title_ar : tb.title_en}</p> : null}
                  <Table stack={false}>
                    <THead>
                      <TR>
                        {(tb.columns ?? []).map((c) => (
                          <TH key={c[0]}>{ar ? c[2] : c[1]}</TH>
                        ))}
                      </TR>
                    </THead>
                    <TBody>
                      {(tb.rows ?? []).map((r, k) => (
                        <TR key={k}>
                          {(tb.columns ?? []).map((c) => (
                            <TD key={c[0]}>
                              <bdi>{String(r[c[0]] ?? "—")}</bdi>
                            </TD>
                          ))}
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </div>
              ))}
            </div>
          </details>
        ))}
        {snap.not_live?.length ? (
          <p className="text-xs text-muted-foreground" data-testid="rp-not-live">
            {t("notLive", { list: snap.not_live.join(", ") })}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Deliveries({ packId, projectId }: { packId: string; projectId: string | null }) {
  const t = useTranslations("rp.pack");
  const te = useTranslations("enums");
  const { dateTime } = useFormatters(projectId);
  const show = useDisplay(projectId);
  const q = usePackDeliveries(packId);
  const items = q.data?.items ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("deliveries")}</CardTitle>
      </CardHeader>
      <CardContent>
        {q.isLoading ? (
          <LoadingState rows={2} />
        ) : items.length ? (
          <Table data-testid="rp-deliveries">
            <THead>
              <TR>
                <TH>{t("member")}</TH>
                <TH>{t("channel")}</TH>
                <TH>{t("status")}</TH>
                <TH>{t("attachments")}</TH>
                <TH>{t("sentAt")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((d) => (
                <TR key={d.id} data-testid="rp-delivery" data-channel={d.channel}>
                  <TD label={t("member")}>
                    <bdi>{d.member}</bdi>
                    <span className="block text-xs text-muted-foreground">{t("rev", { n: show(String(d.revision)) })}</span>
                  </TD>
                  <TD label={t("channel")}>{te(`rpChannel.${d.channel}`)}</TD>
                  <TD label={t("status")}>
                    <ScBadge group="rpDeliveryStatus" status={d.status} />
                    {d.error ? <span className="block text-xs text-danger">{d.error}</span> : null}
                  </TD>
                  <TD label={t("attachments")}>
                    {d.attachments.length ? (
                      <ul className="flex flex-col gap-0.5 text-xs">
                        {d.attachments.map((a) => (
                          <li key={a} className="flex items-start gap-1">
                            <Paperclip aria-hidden className="mt-px size-3.5 shrink-0 text-muted-foreground" />
                            <bdi className="ltr break-all">{a}</bdi>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD label={t("sentAt")}>{dateTime(d.sent_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState message={t("noDeliveries")} />
        )}
      </CardContent>
    </Card>
  );
}

/* ═════════════ distribution lists per report type (DL-1…DL-3) ═════════════ */

export function DistributionListsPage() {
  return <ProjectGate>{(p) => <Distribution project={p} />}</ProjectGate>;
}

function Distribution({ project }: { project: Project }) {
  const t = useTranslations("rp.dist");
  const tc = useTranslations("common");
  const ref = useScRef();
  const caps = useScCaps(project.id);
  const s = useSearchState();
  const type = ((s.get("type") as S["RpType"] | null) ?? "MCR") as "MCR" | "SCP" | "CPS" | "OSHA300" | "HEAT";
  const q = useDistributionList(project.id, type, { enabled: caps.issue });
  if (!caps.issue) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ReportsSubNav />
      <ListToolbar>
        <SelectFilter id="dl-type" label={t("type")} value={type} onChange={(v) => s.set({ type: v || null })} options={TYPES.filter((x) => x !== "CPS").map((x) => ({ value: x, label: `${x} · ${ref.label("report_types", x)}` }))} allLabel="MCR" />
      </ListToolbar>
      {q.isLoading ? <LoadingState /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data ? <DistributionEditor key={`${type}-${JSON.stringify(q.data)}`} project={project} list={q.data} /> : null}
    </div>
  );
}

function DistributionEditor({ project, list }: { project: Project; list: S["RpDistributionList"] }) {
  const t = useTranslations("rp.dist");
  const te = useTranslations("enums");
  const name = useLocalizedName();
  const refresh = useScRefresh();
  const users = useUsers({ project_id: project.id, page_size: 200 });
  const [members, setMembers] = useState<S["RpMemberInput"][]>(
    list.members.map((m) => ({ kind: m.kind, user_id: m.user?.id ?? null, display_name_en: m.display_name_en, display_name_ar: m.display_name_ar, organisation: m.organisation, email: m.email, language: m.language, acknowledge_disclosure: false })),
  );
  const [pick, setPick] = useState("");
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const hasExternal = members.some((m) => m.kind === "external");
  const userName = (id: string | null | undefined) => {
    const u = users.data?.items.find((x) => x.id === id) ?? list.members.find((m) => m.user?.id === id)?.user;
    return u ? name(u.full_name_en, u.full_name_ar) : (id ?? "");
  };
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PUT("/api/v1/projects/{project_id}/distribution-lists/{report_type}", {
          params: { path: { project_id: project.id, report_type: list.report_type } },
          body: { members: members.map((m) => (m.kind === "external" ? { ...m, acknowledge_disclosure: ack } : m)) },
        }),
      );
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-4" data-testid="dl-editor">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("users")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <ul className="flex flex-col divide-y rounded-md border">
            {members.map((m, i) =>
              m.kind === "user" ? (
                <li key={`u-${m.user_id}`} className="flex items-center gap-2 px-3 py-2 text-sm" data-testid="dl-member" data-kind="user">
                  <span className="flex-1">{userName(m.user_id)}</span>
                  <Button variant="ghost" size="sm" aria-label={t("remove")} onClick={() => setMembers(members.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                  </Button>
                </li>
              ) : null,
            )}
          </ul>
          <div className="flex flex-wrap items-end gap-2">
            <FormField id="dl-user" label={t("addUser")}>
              <Select id="dl-user" value={pick} onChange={(e) => setPick(e.target.value)} data-testid="dl-user">
                <option value="">—</option>
                {(users.data?.items ?? [])
                  .filter((u) => !members.some((m) => m.user_id === u.id))
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {name(u.full_name_en, u.full_name_ar)}
                    </option>
                  ))}
              </Select>
            </FormField>
            <Button
              variant="outline"
              disabled={!pick}
              onClick={() => {
                setMembers([...members, { kind: "user", user_id: pick, language: "both", acknowledge_disclosure: false }]);
                setPick("");
              }}
              data-testid="dl-add-user"
            >
              <Plus aria-hidden />
              {t("add")}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">{t("scopeRule")}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("externals")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("externalRule")}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {members.map((m, i) =>
            m.kind === "external" ? (
              <div key={`e-${i}`} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[1fr_1fr_1fr_1fr_auto_auto]" data-testid="dl-member" data-kind="external">
                <Input aria-label={t("nameEn")} placeholder={t("nameEn")} value={m.display_name_en ?? ""} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, display_name_en: e.target.value } : x)))} data-testid="dl-ext-name" />
                <Input aria-label={t("nameAr")} placeholder={t("nameAr")} dir="rtl" value={m.display_name_ar ?? ""} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, display_name_ar: e.target.value } : x)))} />
                <Input aria-label={t("organisation")} placeholder={t("organisation")} value={m.organisation ?? ""} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, organisation: e.target.value } : x)))} data-testid="dl-ext-org" />
                <Input aria-label={t("email")} placeholder={t("email")} type="email" className="ltr" value={m.email ?? ""} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, email: e.target.value } : x)))} data-testid="dl-ext-email" />
                <Select aria-label={t("language")} value={m.language ?? "both"} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, language: e.target.value as S["RpLanguage"] } : x)))}>
                  {(["both", "en", "ar"] as const).map((l) => (
                    <option key={l} value={l}>
                      {te(`rpLanguage.${l}`)}
                    </option>
                  ))}
                </Select>
                <Button variant="ghost" aria-label={t("remove")} onClick={() => setMembers(members.filter((_, j) => j !== i))}>
                  <Trash2 aria-hidden />
                </Button>
              </div>
            ) : null,
          )}
          <Button variant="outline" size="sm" className="w-fit" onClick={() => setMembers([...members, { kind: "external", language: "both", display_name_en: "", organisation: "", email: "", acknowledge_disclosure: false }])} data-testid="dl-add-external">
            <Plus aria-hidden />
            {t("addExternal")}
          </Button>
          {hasExternal ? (
            <label className="flex min-h-touch items-center gap-3 text-sm">
              <Checkbox checked={ack} onChange={(e) => setAck(e.target.checked)} data-testid="dl-ack" />
              {t("acknowledge")}
            </label>
          ) : null}
        </CardContent>
      </Card>
      <MutationError error={error} />
      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={busy} data-testid="dl-save">
          {t("save")}
        </Button>
      </div>
    </div>
  );
}
