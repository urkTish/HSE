"use client";
import { Plus, ShieldAlert, Stethoscope } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, PossibleIdHint } from "@/components/common/api-warnings";
import { ExportButtons } from "@/components/common/export-buttons";
import { FormField } from "@/components/common/form-field";
import { ListToolbar } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, DeploymentPicker, StepDialog, WorkerLabel } from "@/components/access/common";
import { Tick, UserName } from "@/components/cert/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useFitnessHolds, useFitnessReferrals, useMedicalRefresh } from "@/lib/api/medical";
import { HOLD_STATUSES, REFERRAL_REASONS, REFERRAL_STATUSES } from "@/lib/med-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { FitnessCasesSubNav, HoldStatusBadge, NoDiagnosisHint, ReferralStatusBadge, TierNote, useMedCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

/** Link to record the assessment that releases a hold or closes a referral (FA-5, FH-3). */
function assessHref(workerNo: string, type: S["AssessmentType"], ref: { hold?: string; referral?: string }) {
  const q = new URLSearchParams({ worker_no: workerNo, type });
  if (ref.hold) q.set("hold", ref.hold);
  if (ref.referral) q.set("referral", ref.referral);
  return `/fitness-assessments/new?${q.toString()}`;
}

/* ═════════════ holds (§3.7, §4.4, FH-1…FH-8) ═════════════ */

export function FitnessHoldsPage() {
  return <ProjectGate>{(p) => <Holds project={p} />}</ProjectGate>;
}

function Holds({ project }: { project: Project }) {
  const t = useTranslations("medical.holds");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useMedCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["HoldStatus"][];
  const wdh = s.get("wdh") === "1";
  const q = useFitnessHolds(project.id, { status: status.length ? status : null, with_work_during_hold: wdh || null, page, page_size: PAGE_SIZE });
  const [place, setPlace] = useState(false);
  const [cancel, setCancel] = useState<S["FitnessHoldRead"] | null>(null);
  const items = q.data?.items ?? [];
  const tier3 = items[0]?.tier === "clinical_admin";
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.holdManage ? (
            <Button onClick={() => setPlace(true)} data-testid="place-hold">
              <Plus aria-hidden />
              {t("place")}
            </Button>
          ) : null
        }
      />
      <FitnessCasesSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="fitness_holds" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="hold-status" label={tc("status")} options={HOLD_STATUSES.map((x) => ({ value: x, label: te(`holdStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <Tick id="hold-wdh" label={t("withWorkDuringHold")} checked={wdh} onChange={(v) => s.set({ wdh: v ? "1" : "" })} />
      </ListToolbar>
      <TierNote tier={items[0]?.tier} />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="holds-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("started")}</TH>
                <TH>{t("ended")}</TH>
                <TH>{t("hours")}</TH>
                <TH>{t("workDuringHold")}</TH>
                {tier3 ? <TH>{t("reason")}</TH> : null}
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((h) => (
                <TR key={h.id} data-testid="hold-row" data-no={h.hold_no} data-status={h.status}>
                  <TD label={t("no")}>
                    <Code className="font-medium">{h.hold_no}</Code>
                  </TD>
                  <TD label={t("worker")}>
                    <WorkerLabel w={h.worker} link />
                  </TD>
                  <TD label={t("started")}>{dateTime(h.started_at)}</TD>
                  <TD label={t("ended")}>{h.released_at ? dateTime(h.released_at) : h.cancelled_at ? dateTime(h.cancelled_at) : "—"}</TD>
                  <TD label={t("hours")}>
                    <span className="ltr tabular-nums">{h.hold_hours}</span>
                  </TD>
                  <TD label={t("workDuringHold")}>
                    {h.work_during_hold.length ? (
                      <ul className="text-xs text-danger" data-testid="wdh">
                        {h.work_during_hold.map((w, i) => (
                          <li key={i}>
                            {te(`workDuringHold.${w.event_type}`)} · {dateTime(w.at)} {w.ref ? <Code>{w.ref}</Code> : null}
                          </li>
                        ))}
                      </ul>
                    ) : h.compliant ? (
                      <Badge tone="success">{t("compliant")}</Badge>
                    ) : (
                      "—"
                    )}
                  </TD>
                  {tier3 ? (
                    <TD label={t("reason")}>
                      {h.reason ? <span data-testid="hold-reason">{te(`holdReason.${h.reason}`)}</span> : "—"}
                      {h.source_ref ? <Code className="block text-xs">{h.source_ref}</Code> : null}
                      {h.reason_text ? <span className="block text-xs text-muted-foreground">{h.reason_text}</span> : null}
                      {h.release_assessment_no ? <span className="block text-xs">{t("releasedBy", { no: h.release_assessment_no })}</span> : null}
                      {h.cancel_code ? <span className="block text-xs">{te(`holdCancelCode.${h.cancel_code}`)}</span> : null}
                      {h.cancel_reason ? <span className="block text-xs text-muted-foreground">{h.cancel_reason}</span> : null}
                    </TD>
                  ) : null}
                  <TD label={tc("status")}>
                    <HoldStatusBadge status={h.status} />
                  </TD>
                  <TD>
                    {h.status === "active" ? (
                      <span className="flex flex-wrap gap-1">
                        {(caps.recordClinic || caps.submitExternal) && h.reason ? (
                          <Button size="sm" variant="outline" asChild>
                            <Link href={assessHref(h.worker.worker_no, h.reason === "referral" ? "referral" : "return_to_work", h.reason === "referral" ? {} : { hold: h.id })} data-testid="hold-assess">
                              <Stethoscope aria-hidden />
                              {t("assess")}
                            </Link>
                          </Button>
                        ) : null}
                        {caps.holdCancel ? (
                          <Button size="sm" variant="destructive-outline" onClick={() => setCancel(h)} data-testid="hold-cancel">
                            {t("cancel")}
                          </Button>
                        ) : null}
                      </span>
                    ) : null}
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
      {place ? <PlaceHoldDialog project={project} onClose={() => setPlace(false)} /> : null}
      {cancel ? (
        <ReasonDialog
          title={t("cancelTitle", { no: cancel.hold_no })}
          description={t("cancelHint")}
          confirmLabel={t("cancel")}
          onConfirm={async (reason) => {
            await unwrap(api.POST("/api/v1/fitness-holds/{hold_id}/cancel", { params: { path: { hold_id: cancel.id } }, body: { reason } }));
          }}
          onClose={() => setCancel(null)}
        />
      ) : null}
    </div>
  );
}

/** Reason ≥ 20 characters (holds, referrals, plan removal). */
export function ReasonDialog({
  title,
  description,
  confirmLabel,
  min = 20,
  onConfirm,
  onClose,
}: {
  title: string;
  description?: string;
  confirmLabel: string;
  min?: number;
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const t = useTranslations("medical.common");
  const refresh = useMedicalRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      destructive
      dismissLabel={t("back")}
      disabled={reason.trim().length < min}
      testId="reason-confirm"
      onConfirm={async () => {
        await onConfirm(reason.trim());
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="md-reason" label={t("reason")} required hint={t("reasonMin", { min, n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="md-reason" />
      </FormField>
      <p className="text-xs text-muted-foreground">
        <NoDiagnosisHint />
      </p>
    </StepDialog>
  );
}

export function PlaceHoldDialog({ project, deployment, onClose }: { project: Project; deployment?: S["DeploymentRead"] | null; onClose: () => void }) {
  const t = useTranslations("medical.holds");
  const tc = useTranslations("common");
  const refresh = useMedicalRefresh();
  const [d, setD] = useState<S["DeploymentRead"] | null>(deployment ?? null);
  const [text, setText] = useState("");
  return (
    <StepDialog
      title={t("place")}
      description={t("placeHint")}
      confirmLabel={t("place")}
      destructive
      disabled={!d || text.trim().length < 20}
      testId="place-hold-confirm"
      onConfirm={async () => {
        if (!d) return;
        const r = await unwrap(api.POST("/api/v1/projects/{project_id}/fitness-holds", { params: { path: { project_id: project.id } }, body: { worker_id: d.worker_id, reason_text: text.trim() } }));
        toast.success(t("placed", { no: r.hold_no }));
        await refresh();
      }}
      onClose={onClose}
    >
      {deployment ? null : <DeploymentPicker id="hold-worker" projectId={project.id} value={d} onChange={setD} label={t("worker")} required status={["mobilised", "pending_induction"]} />}
      <FormField id="hold-text" label={t("reasonText")} required hint={t("reasonTextHint", { n: text.trim().length })}>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={300} data-testid="hold-text" />
      </FormField>
      <p className="text-xs text-muted-foreground">
        <NoDiagnosisHint />
      </p>
      <PossibleIdHint text={text} />
      <span className="sr-only">{tc("required")}</span>
    </StepDialog>
  );
}

/* ═════════════ referrals (§3.8, §4.5, RF-1…RF-7) ═════════════ */

export function FitnessReferralsPage() {
  return <ProjectGate>{(p) => <Referrals project={p} />}</ProjectGate>;
}

function Referrals({ project }: { project: Project }) {
  const t = useTranslations("medical.referrals");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useMedCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["ReferralStatus"][];
  const overdue = s.get("overdue") === "1" || s.get("overdue") === "true";
  const q = useFitnessReferrals(project.id, { status: status.length ? status : null, overdue: overdue || null, page, page_size: PAGE_SIZE });
  const [raise, setRaise] = useState(false);
  const [cancel, setCancel] = useState<S["FitnessReferralRead"] | null>(null);
  const items = q.data?.items ?? [];
  const tier3 = items[0]?.tier === "clinical_admin";
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.refer ? (
            <Button onClick={() => setRaise(true)} data-testid="raise-referral">
              <Plus aria-hidden />
              {t("raise")}
            </Button>
          ) : null
        }
      />
      <FitnessCasesSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="fitness_referrals" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="ref-status" label={tc("status")} options={REFERRAL_STATUSES.map((x) => ({ value: x, label: te(`referralStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <Tick id="ref-overdue" label={t("overdueOnly")} checked={overdue} onChange={(v) => s.set({ overdue: v ? "1" : "" })} />
      </ListToolbar>
      <TierNote tier={items[0]?.tier} />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="referrals-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("raised")}</TH>
                <TH>{t("due")}</TH>
                <TH>{t("removeFromWork")}</TH>
                {tier3 ? <TH>{t("reason")}</TH> : null}
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="referral-row" data-no={r.referral_no} data-status={r.status}>
                  <TD label={t("no")}>
                    <Code className="font-medium">{r.referral_no}</Code>
                    {r.hold_no ? <Code className="block text-xs text-muted-foreground">{r.hold_no}</Code> : null}
                  </TD>
                  <TD label={t("worker")}>
                    <WorkerLabel w={r.worker} link />
                  </TD>
                  <TD label={t("raised")}>
                    {dateTime(r.raised_at)}
                    <span className="block text-xs text-muted-foreground">
                      <UserName u={r.raised_by} />
                    </span>
                  </TD>
                  <TD label={t("due")}>
                    {dateTime(r.due_at)}
                    {r.assessed_at ? (
                      <span className={r.on_time ? "block text-xs text-success" : "block text-xs text-danger"} data-testid="referral-on-time" data-on-time={r.on_time ? "yes" : "no"}>
                        {r.on_time ? t("onTime") : t("late")} · {dateTime(r.assessed_at)}
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("removeFromWork")}>{r.remove_from_work ? <Badge tone="danger">{tc("yes")}</Badge> : tc("no")}</TD>
                  {tier3 ? (
                    <TD label={t("reason")}>
                      {r.reason ? <span data-testid="referral-reason">{te(`referralReason.${r.reason}`)}</span> : "—"}
                      {r.note ? <span className="block text-xs text-muted-foreground" data-testid="referral-note">{r.note}</span> : null}
                      {r.cancel_reason ? <span className="block text-xs text-muted-foreground">{r.cancel_reason}</span> : null}
                    </TD>
                  ) : null}
                  <TD label={tc("status")}>
                    <ReferralStatusBadge status={r.status} overdue={r.overdue} />
                  </TD>
                  <TD>
                    {r.status === "open" ? (
                      <span className="flex flex-wrap gap-1">
                        {caps.recordClinic || caps.submitExternal ? (
                          <Button size="sm" variant="outline" asChild>
                            <Link href={assessHref(r.worker.worker_no, "referral", { referral: r.id })} data-testid="referral-assess">
                              <Stethoscope aria-hidden />
                              {t("assess")}
                            </Link>
                          </Button>
                        ) : null}
                        {caps.holdCancel || (!r.remove_from_work && caps.refer) ? (
                          <Button size="sm" variant="destructive-outline" onClick={() => setCancel(r)} data-testid="referral-cancel">
                            {t("cancel")}
                          </Button>
                        ) : null}
                      </span>
                    ) : null}
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
      {raise ? <RaiseReferralDialog project={project} onClose={() => setRaise(false)} /> : null}
      {cancel ? (
        <ReasonDialog
          title={t("cancelTitle", { no: cancel.referral_no })}
          confirmLabel={t("cancel")}
          onConfirm={async (reason) => {
            await unwrap(api.POST("/api/v1/fitness-referrals/{referral_id}/cancel", { params: { path: { referral_id: cancel.id } }, body: { reason } }));
          }}
          onClose={() => setCancel(null)}
        />
      ) : null}
    </div>
  );
}

export function RaiseReferralDialog({ project, deployment, onClose }: { project: Project; deployment?: S["DeploymentRead"] | null; onClose: () => void }) {
  const t = useTranslations("medical.referrals");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useMedicalRefresh();
  const [d, setD] = useState<S["DeploymentRead"] | null>(deployment ?? null);
  const [reason, setReason] = useState<S["ReferralReason"] | "">("");
  const [note, setNote] = useState("");
  const [remove, setRemove] = useState(false);
  const [result, setResult] = useState<S["FitnessReferralRead"] | null>(null);
  const shown = useRef<S["FitnessReferralRead"] | null>(null);
  if (result) {
    return (
      <StepDialog title={t("raised", { no: result.referral_no })} confirmLabel={tc("close")} onConfirm={async () => undefined} onClose={onClose}>
        <div data-testid="referral-raised" data-no={result.referral_no}>
          {result.hold_no ? (
            <Alert tone="warning">
              <ShieldAlert aria-hidden className="inline size-4" /> {t("holdCreated", { no: result.hold_no })}
            </Alert>
          ) : null}
          <ApiWarnings warnings={result.warnings} />
          {result.incident_draft_link ? (
            <Link href={result.incident_draft_link} className="text-primary hover:underline" data-testid="incident-draft-link">
              {t("openIncidentDraft")}
            </Link>
          ) : null}
        </div>
      </StepDialog>
    );
  }
  return (
    <StepDialog
      title={t("raise")}
      description={t("raiseHint")}
      confirmLabel={t("raise")}
      disabled={!d || !reason}
      testId="raise-referral-confirm"
      onConfirm={async () => {
        if (!d || !reason) return;
        const r = await unwrap(
          api.POST("/api/v1/projects/{project_id}/fitness-referrals", { params: { path: { project_id: project.id } }, body: { worker_id: d.worker_id, reason, note: note.trim() || null, remove_from_work: remove } }),
        );
        await refresh();
        if (r.hold_no || r.warnings?.length || r.incident_draft_link) shown.current = r;
        else toast.success(t("raised", { no: r.referral_no }));
      }}
      onClose={() => (shown.current ? setResult(shown.current) : onClose())}
    >
      {deployment ? null : <DeploymentPicker id="ref-worker" projectId={project.id} value={d} onChange={setD} label={t("worker")} required status={["mobilised"]} />}
      <FormField id="ref-reason" label={t("reason")} required>
        <Select value={reason} onChange={(e) => setReason(e.target.value as S["ReferralReason"])} data-testid="ref-reason">
          <option value="">{tc("select")}</option>
          {REFERRAL_REASONS.map((x) => (
            <option key={x} value={x}>
              {te(`referralReason.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="ref-note" label={t("note")} hint={t("noteHint")}>
        <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} data-testid="ref-note" />
      </FormField>
      <PossibleIdHint text={note} />
      <Tick id="ref-remove" label={t("removeFromWorkLabel")} checked={remove} onChange={setRemove} />
      {remove ? <Alert tone="warning">{t("removeHint")}</Alert> : null}
    </StepDialog>
  );
}
