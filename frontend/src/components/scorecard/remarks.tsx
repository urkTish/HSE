"use client";
import { MessageSquarePlus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Code, StepDialog } from "@/components/access/common";
import { ApiWarnings, PossibleIdHint } from "@/components/common/api-warnings";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Choices, DeadlineRule, Countdown, FilePick, toFileInput } from "@/components/followup/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useScRefresh, useScRemarks } from "@/lib/api/scorecard";
import { useDisplay } from "@/lib/digits";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ScBadge, ScSubNav, useScCaps, useScRef } from "./common";

type S = Schemas;
type Remark = S["ScRemarkRead"];

const REASONS: S["ScDisputeReason"][] = ["data_error", "wrong_attribution", "not_applicable", "other"];

/* ═════════════ dispute register (§8.3) ═════════════ */

export function RemarksPage() {
  return <ProjectGate>{(p) => <Register projectId={p.id} />}</ProjectGate>;
}

function Register({ projectId }: { projectId: string }) {
  const t = useTranslations("sc.remarks");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const caps = useScCaps(projectId);
  const s = useSearchState();
  const kind = (s.get("kind") as S["ScRemarkKind"] | null) ?? "";
  const status = (s.get("status") as S["ScRemarkStatus"] | null) ?? "";
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ScSubNav />
      <ListToolbar>
        <SelectFilter id="rm-kind" label={t("kind")} value={kind} onChange={(v) => s.set({ kind: v || null })} options={(["dispute", "comment"] as const).map((x) => ({ value: x, label: te(`scRemarkKind.${x}`) }))} />
        <SelectFilter id="rm-status" label={t("status")} value={status} onChange={(v) => s.set({ status: v || null })} options={(["open", "resolved", "withdrawn"] as const).map((x) => ({ value: x, label: te(`scRemarkStatus.${x}`) }))} />
      </ListToolbar>
      <DeadlineRule className="mb-2" />
      <RemarkList projectId={projectId} kind={kind || undefined} status={status || undefined} showCard />
    </div>
  );
}

/* ═════════════ list of comments and disputes (card page and register) ═════════════ */

export function RemarkList({ projectId, cardId, kind, status, showCard }: { projectId: string; cardId?: string; kind?: S["ScRemarkKind"]; status?: S["ScRemarkStatus"]; showCard?: boolean }) {
  const t = useTranslations("sc.remarks");
  const te = useTranslations("enums");
  const caps = useScCaps(projectId);
  const name = useLocalizedName();
  const ref = useScRef();
  const show = useDisplay(projectId);
  const { dateTime } = useFormatters(projectId);
  const refresh = useScRefresh();
  const q = useScRemarks(projectId, { card_id: cardId ?? null, kind: kind ?? null, status: status ?? null, page_size: 200 });
  const [resolve, setResolve] = useState<Remark | null>(null);
  const [error, setError] = useState<unknown>(null);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const items = q.data?.items ?? [];
  if (!items.length) return <EmptyState message={t("empty")} />;
  async function withdraw(r: Remark) {
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/scorecard-remarks/{remark_id}/withdraw", { params: { path: { remark_id: r.id } } }));
      await refresh();
      toast.success(t("withdrawn"));
    } catch (e) {
      setError(e);
    }
  }
  return (
    <>
      <MutationError error={error} />
      <ul className="flex flex-col divide-y rounded-md border" data-testid="sc-remarks">
        {items.map((r) => {
          const mine = r.raised_by?.id === caps.me?.id;
          return (
            <li key={r.id} className="flex flex-col gap-2 px-4 py-3" data-testid="sc-remark" data-kind={r.kind} data-status={r.status}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{te(`scRemarkKind.${r.kind}`)}</span>
                {r.internal ? <span className="rounded bg-muted px-1.5 text-xs text-muted-foreground">{t("internal")}</span> : null}
                <ScBadge group="scRemarkStatus" status={r.status} testId="sc-remark-status" />
                {showCard ? (
                  <Link href={`/scorecards/${r.card_id}`} className="text-primary hover:underline">
                    <Code>{r.scorecard_no}</Code>
                  </Link>
                ) : null}
                {r.target_code ? (
                  <span className="text-sm">
                    <Code>{r.target_code}</Code> {ref.label(r.target_code.startsWith("CP-") ? "caps" : "metrics", r.target_code)}
                  </span>
                ) : (
                  <span className="text-sm text-muted-foreground">{t("wholeCard")}</span>
                )}
                {r.reason_code ? <span className="text-sm text-muted-foreground">· {te(`scDisputeReason.${r.reason_code}`)}</span> : null}
              </div>
              <p className="text-sm whitespace-pre-wrap" data-testid="sc-remark-text">
                {r.text}
              </p>
              <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {r.raised_by ? name(r.raised_by.full_name_en, r.raised_by.full_name_ar) : t("someone")} · {dateTime(r.raised_at)}
                {r.due_at && r.status === "open" ? (
                  <>
                    · {t("dueAt", { at: dateTime(r.due_at) })}
                    <Countdown due={r.due_at} projectId={projectId} />
                  </>
                ) : null}
              </p>
              <ApiWarnings warnings={r.warnings} />
              {r.resolution ? (
                <div className="rounded-md bg-muted/40 px-3 py-2 text-sm" data-testid="sc-resolution" data-resolution={r.resolution}>
                  <p className="font-medium">{te(`scResolution.${r.resolution}`)}</p>
                  {r.resolution_text ? <p className="whitespace-pre-wrap">{r.resolution_text}</p> : null}
                  {r.corrected_record_ref ? (
                    <p className="text-xs">
                      {t("corrected")} <Code>{r.corrected_record_ref}</Code>
                    </p>
                  ) : null}
                  {r.old_points !== null || r.new_points !== null ? (
                    <p className="text-xs" data-testid="sc-resolution-points">
                      {t("points", { old: show(r.old_points ? Number(r.old_points).toFixed(1) : "—"), new: show(r.new_points ? Number(r.new_points).toFixed(1) : "—") })}
                      {r.old_score && r.new_score ? ` · ${t("scoreChange", { old: show(Number(r.old_score).toFixed(1)), new: show(Number(r.new_score).toFixed(1)) })}` : null}
                    </p>
                  ) : null}
                  {r.resolved_by ? (
                    <p className="text-xs text-muted-foreground">
                      {name(r.resolved_by.full_name_en, r.resolved_by.full_name_ar)} · {r.resolved_at ? dateTime(r.resolved_at) : ""}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {r.status === "open" ? (
                <div className="flex flex-wrap gap-2">
                  {caps.resolve && r.kind === "dispute" ? (
                    <Button size="sm" onClick={() => setResolve(r)} data-testid="sc-resolve">
                      {t("resolve")}
                    </Button>
                  ) : null}
                  {mine ? (
                    <Button size="sm" variant="outline" onClick={() => void withdraw(r)} data-testid="sc-withdraw">
                      {t("withdraw")}
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {resolve ? <ResolveDialog remark={resolve} canExclude={caps.manage} onClose={() => setResolve(null)} /> : null}
    </>
  );
}

/* ═════════════ raise a comment or dispute (DP-1, DP-2, P6g-4) ═════════════ */

export function NewRemarkButton({ card }: { card: S["ScCardRead"] }) {
  const t = useTranslations("sc.remarks");
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)} data-testid="sc-new-remark">
        <MessageSquarePlus aria-hidden />
        {t("new")}
      </Button>
      {open ? <RemarkDialog card={card} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function RemarkDialog({ card, onClose }: { card: S["ScCardRead"]; onClose: () => void }) {
  const t = useTranslations("sc.remarks");
  const tf = useTranslations("fu.common");
  const te = useTranslations("enums");
  const caps = useScCaps(card.project_id);
  const ref = useScRef();
  const refresh = useScRefresh();
  // DP-1: HSE Officers comment (internal notes); contractor reps comment or dispute.
  const canDispute = caps.rep || caps.manage;
  const [kind, setKind] = useState<S["ScRemarkKind"]>(canDispute ? "dispute" : "comment");
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState<S["ScDisputeReason"] | "">("");
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const n = text.trim().length;
  const dispute = kind === "dispute";
  const ok = n >= 20 && n <= 1000 && (!dispute || (Boolean(target) && Boolean(reason)));
  return (
    <StepDialog
      title={t("newTitle", { no: card.scorecard_no })}
      description={dispute ? t("disputeBody") : t("commentBody")}
      confirmLabel={dispute ? t("raiseDispute") : t("addComment")}
      testId="sc-remark-confirm"
      wide
      disabled={!ok}
      onConfirm={async () => {
        const r = await unwrap(
          api.POST("/api/v1/scorecards/{card_id}/remarks", {
            params: { path: { card_id: card.id as string } },
            body: { kind, target_code: target || null, reason_code: dispute ? (reason as S["ScDisputeReason"]) : null, text: text.trim(), files: await Promise.all(files.map(toFileInput)) },
          }),
        );
        await refresh();
        toast.success(dispute ? t("disputeDone") : t("commentDone"));
        if (r.warnings?.length) toast.warning(t("possibleIdWarning"));
      }}
      onClose={onClose}
    >
      {canDispute ? (
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-sm font-medium">{t("kind")}</legend>
          <Choices
            label={t("kind")}
            testId="sc-remark-kind"
            value={kind}
            options={(["dispute", "comment"] as const).map((k) => ({ value: k, label: te(`scRemarkKind.${k}`) }))}
            onChange={setKind}
          />
        </fieldset>
      ) : (
        <p className="text-sm text-muted-foreground">{t("internalNote")}</p>
      )}
      <FormField id="sc-remark-target" label={t("target")} required={dispute}>
        <Select id="sc-remark-target" value={target} onChange={(e) => setTarget(e.target.value)} data-testid="sc-remark-target">
          <option value="">{t("wholeCard")}</option>
          {(card.lines ?? []).map((l) => (
            <option key={l.metric_code} value={l.metric_code}>
              {l.metric_code} · {ref.label("metrics", l.metric_code)}
            </option>
          ))}
          {card.caps_applied.map((c) => (
            <option key={c.cap_code} value={c.cap_code}>
              {c.cap_code} · {ref.label("caps", c.cap_code)}
            </option>
          ))}
        </Select>
      </FormField>
      {dispute ? (
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-sm font-medium">{t("reason")}</legend>
          <Choices label={t("reason")} testId="sc-remark-reason" value={reason} options={REASONS.map((r) => ({ value: r, label: te(`scDisputeReason.${r}`) }))} onChange={setReason} />
        </fieldset>
      ) : null}
      <FormField id="sc-remark-text" label={t("text")} required hint={tf("reasonMin", { min: 20, n })}>
        <Textarea id="sc-remark-text" value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} data-testid="sc-remark-text-input" />
      </FormField>
      <p className="text-xs text-muted-foreground">{t("noNames")}</p>
      <PossibleIdHint text={text} />
      <FormField id="sc-remark-files" label={t("files")} hint={t("filesHint")}>
        <FilePick files={files} onChange={setFiles} max={3} testId="sc-remark-files" accept="image/*,application/pdf" />
      </FormField>
    </StepDialog>
  );
}

/* ═════════════ resolve a dispute (DP-3…DP-5) ═════════════ */

function ResolveDialog({ remark, canExclude, onClose }: { remark: Remark; canExclude: boolean; onClose: () => void }) {
  const t = useTranslations("sc.remarks");
  const tf = useTranslations("fu.common");
  const te = useTranslations("enums");
  const refresh = useScRefresh();
  const [resolution, setResolution] = useState<S["ScResolution"] | "">("");
  const [text, setText] = useState("");
  const [corrected, setCorrected] = useState("");
  const n = text.trim().length;
  const cap = remark.target_code?.startsWith("CP-") ?? false;
  const options: S["ScResolution"][] = ["upheld_data_corrected", ...(canExclude && !cap ? (["upheld_metric_excluded"] as const) : []), "rejected"];
  const ok = Boolean(resolution) && n >= 20 && (resolution !== "upheld_data_corrected" || corrected.trim().length > 0);
  return (
    <StepDialog
      title={t("resolveTitle", { target: remark.target_code ?? t("wholeCard") })}
      description={t("resolveBody")}
      confirmLabel={t("resolveConfirm")}
      testId="sc-resolve-confirm"
      wide
      disabled={!ok}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/scorecard-remarks/{remark_id}/resolve", {
            params: { path: { remark_id: remark.id } },
            body: { resolution: resolution as S["ScResolution"], resolution_text: text.trim(), corrected_record_ref: corrected.trim() || null },
          }),
        );
        await refresh();
        toast.success(t("resolved"));
      }}
      onClose={onClose}
    >
      <blockquote className="border-s-4 ps-3 text-sm text-muted-foreground">{remark.text}</blockquote>
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-sm font-medium">{t("resolution")}</legend>
        <Choices label={t("resolution")} testId="sc-resolution-choice" value={resolution} options={options.map((r) => ({ value: r, label: te(`scResolution.${r}`) }))} onChange={setResolution} />
        {cap ? <p className="text-xs text-muted-foreground">{t("capNotExcludable")}</p> : !canExclude ? <p className="text-xs text-muted-foreground">{t("excludeManagerOnly")}</p> : null}
      </fieldset>
      {resolution === "upheld_data_corrected" ? (
        <FormField id="sc-corrected" label={t("correctedRef")} required hint={t("correctedHint")}>
          <Input id="sc-corrected" value={corrected} onChange={(e) => setCorrected(e.target.value)} className="ltr" data-testid="sc-corrected-ref" />
        </FormField>
      ) : null}
      <FormField id="sc-resolution-text" label={t("resolutionText")} required hint={tf("reasonMin", { min: 20, n })}>
        <Textarea id="sc-resolution-text" value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} data-testid="sc-resolution-text" />
      </FormField>
    </StepDialog>
  );
}
