"use client";
import { BookOpen, ChevronDown, FileText, Info, Lightbulb, Lock, Send, ShieldOff, Stamp, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Code } from "@/components/access/common";
import { RecordActions } from "@/components/common/record-actions";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StackedDate } from "@/components/medical/common";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useFuRequirements, useFuSubmissions, useSimilarLessons } from "@/lib/api/followup";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";
import { AckDialog, GeneratePackDialog, SubmissionDialog, VoidSubmissionDialog, WaiveDialog } from "./actions";
import { Countdown, DeadlineRule, FuBadge, OnTimeBadge, RequirementBadge, useBi, useFuCaps } from "./common";

type S = Schemas;
type Req = S["FuRequirementRead"];
type Dialog = { kind: "pack" | "submit" | "waive"; req: Req } | { kind: "ack" | "void"; sub: S["FuSubmissionRead"]; req: Req } | null;

const OPEN: S["FuRequirementStatus"][] = ["due", "overdue"];
const RANK: Record<S["FuRequirementStatus"], number> = { overdue: 0, due: 1, submitted: 2, acknowledged: 3, waived: 4, not_required: 5 };

/** Overdue first, then due (soonest first), then the rest by due time. */
export function sortRequirements(items: Req[]): Req[] {
  return [...items].sort((a, b) => RANK[a.status] - RANK[b.status] || Date.parse(a.due_at) - Date.parse(b.due_at));
}

type PackGate = { block: boolean; reason: "needsInvestigation" | "needsInvestigationMaybe" | "needsIdentity" } | null;

/**
 * Why the server would refuse "Generate pack", worked out from data the page already holds (no extra request):
 * CLIENT-FINAL needs the approved investigation (PK-5; known on the incident page, a hint elsewhere); identity packs
 * need injured-person identity access, and GOSI-WIR also the medical part unless the user is a Contractor HSE Rep (PK-1).
 * The server still decides; this only hides a button that would fail and says why.
 */
function usePackGate(r: Req, incident?: S["IncidentRead"]): PackGate {
  const caps = useFuCaps(r.project_id);
  const me = caps.me;
  if (r.form_code === "CLIENT-FINAL") {
    if (!incident) return { block: false, reason: "needsInvestigationMaybe" };
    return incident.investigation?.approved_at ? null : { block: true, reason: "needsInvestigation" };
  }
  if (r.form_code === "GOSI-WIR" || r.form_code === "MHRSD-LTR") {
    const rep = Boolean(me?.projects.find((p) => p.project_id === r.project_id)?.roles.includes("contractor_hse_rep"));
    const identity = can(me, "injury.identity_view", r.project_id);
    const medical = can(me, "injury.medical_view", r.project_id) || rep;
    if (!identity || (r.form_code === "GOSI-WIR" && !medical)) return { block: true, reason: "needsIdentity" };
  }
  return null;
}

/** Due time of a requirement; "end of day" when it falls at 23:59 Riyadh time (investigation-due finals, D-220). */
function DueAt({ due, open, projectId }: { due: string; open: boolean; projectId: string }) {
  const td = useTranslations("fuDesign");
  const eod = new Date(due).toLocaleTimeString("en-GB", { timeZone: "Asia/Riyadh", hour: "2-digit", minute: "2-digit", hour12: false }) === "23:59";
  return (
    <dd className="flex flex-col gap-1">
      <StackedDate v={due} time projectId={projectId} />
      {eod ? <span className="text-xs text-muted-foreground" data-testid="fu-end-of-day">{td("endOfDayShort")}</span> : null}
      <Countdown due={due} open={open} projectId={projectId} />
    </dd>
  );
}

/** Requirement cards (body · stage, due time and countdown, submission, pack, actions). Phone-first: one card per requirement. */
export function RequirementList({ items, projectId, showIncident, incident }: { items: Req[]; projectId: string; showIncident?: boolean; incident?: S["IncidentRead"] }) {
  const [dialog, setDialog] = useState<Dialog>(null);
  // Dialogs read the latest copy of the requirement (a pack approved meanwhile, a refetch after navigation).
  const fresh = (r: Req) => items.find((x) => x.id === r.id) ?? r;
  return (
    <>
      <ul className="flex flex-col gap-3" data-testid="fu-requirements">
        {sortRequirements(items).map((r) => (
          <RequirementCard key={r.id} r={r} projectId={projectId} showIncident={showIncident} incident={incident} onDialog={setDialog} />
        ))}
      </ul>
      {dialog?.kind === "pack" ? <GeneratePackDialog req={fresh(dialog.req)} onClose={() => setDialog(null)} /> : null}
      {dialog?.kind === "submit" ? <SubmissionDialog key={fresh(dialog.req).pack_status ?? "none"} req={fresh(dialog.req)} onClose={() => setDialog(null)} /> : null}
      {dialog?.kind === "waive" ? <WaiveDialog req={fresh(dialog.req)} onClose={() => setDialog(null)} /> : null}
      {dialog?.kind === "ack" ? <AckDialog sub={dialog.sub} projectId={projectId} onClose={() => setDialog(null)} /> : null}
      {dialog?.kind === "void" ? <VoidSubmissionDialog sub={dialog.sub} onClose={() => setDialog(null)} /> : null}
    </>
  );
}

function RequirementCard({ r, projectId, showIncident, incident, onDialog }: { r: Req; projectId: string; showIncident?: boolean; incident?: S["IncidentRead"]; onDialog: (d: Dialog) => void }) {
  const t = useTranslations("fu.req");
  const td = useTranslations("fuDesign");
  const gate = usePackGate(r, incident);
  const te = useTranslations("enums");
  const caps = useFuCaps(projectId);
  const { dateTime } = useFormatters(projectId);
  const [open, setOpen] = useState(false);
  const isOpen = OPEN.includes(r.status);
  const packable = caps.record && Boolean(r.form_code) && isOpen && r.pack_status !== "submitted";
  const canPack = packable && !gate?.block;
  const done = r.status === "submitted" || r.status === "acknowledged";
  return (
    <li
      className={cn("flex flex-col gap-3 rounded-md border p-3", r.status === "overdue" && "border-danger bg-danger-bg/40")}
      data-testid="fu-req"
      data-rule={r.rule_code}
      data-status={r.status}
      data-incident={r.incident_ref}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="font-medium">
            {te(`externalBody.${r.body}`)} · {te(`fuStage.${r.stage}`)}
          </span>
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Code>{r.rule_code}</Code>
            {r.form_code ? <span>{te(`fuForm.${r.form_code}`)}</span> : null}
            {r.source === "client" ? <span>{te("fuRuleSource.client")}</span> : null}
            {showIncident ? (
              <Link href={`/incidents/${r.incident_id}`} className="text-primary hover:underline" data-testid="fu-req-incident">
                <Code>{r.incident_ref}</Code>
              </Link>
            ) : null}
          </span>
        </div>
        <RequirementBadge status={r.status} />
      </div>
      <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        <div className="flex flex-col gap-0.5">
          <dt className="text-xs text-muted-foreground">{t("due")}</dt>
          <DueAt due={r.due_at} open={isOpen} projectId={projectId} />
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="text-xs text-muted-foreground">{t("filer")}</dt>
          <dd>
            {te(`fuFiler.${r.filer}`)}
            {r.filer_code ? (
              <>
                {" · "}
                <Code>{r.filer_code}</Code>
              </>
            ) : null}
          </dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="text-xs text-muted-foreground">{t("submission")}</dt>
          <dd className="flex flex-col gap-1">
            {r.submission_no ? (
              <>
                <span className="flex flex-wrap items-center gap-2">
                  <Code>{r.submission_no}</Code>
                  <OnTimeBadge onTime={r.on_time} />
                </span>
                <span className="text-xs text-muted-foreground">{dateTime(r.submitted_at)}</span>
                {r.reference_no ? (
                  <span className="text-xs">
                    {t("ref")} <Code>{r.reference_no}</Code>
                  </span>
                ) : null}
              </>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </dd>
        </div>
      </dl>
      {r.case_labels.length ? (
        <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="fu-req-cases">
          <Users aria-hidden className="size-4 text-muted-foreground" />
          {r.case_labels.map((c) => (
            <bdi key={c}>{c}</bdi>
          ))}
        </p>
      ) : null}
      {r.trigger_note ? <p className="text-xs text-muted-foreground">{r.trigger_note}</p> : null}
      {r.status === "waived" ? (
        <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="fu-req-waiver">
          <ShieldOff aria-hidden className="size-4 text-muted-foreground" />
          {r.waiver_reason_code ? te(`fuWaiverReason.${r.waiver_reason_code}`) : null}
          {r.waiver_text ? <span className="text-muted-foreground">— {r.waiver_text}</span> : null}
          {r.waiver_reference ? <Code>{r.waiver_reference}</Code> : null}
        </p>
      ) : null}
      {r.pack_no ? (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <FileText aria-hidden className="size-4 text-muted-foreground" />
          {caps.packs && r.pack_id ? (
            <Link href={`/notification-packs/${r.pack_id}`} className="text-primary hover:underline" data-testid="fu-req-pack">
              <Code>{r.pack_no}</Code>
            </Link>
          ) : (
            <Code>{r.pack_no}</Code>
          )}
          {r.pack_status ? <FuBadge group="fuPackStatus" status={r.pack_status} testId="fu-pack-status" /> : null}
        </p>
      ) : null}
      {caps.record && isOpen ? (
        <div className="flex flex-wrap gap-2">
          {canPack ? (
            <Button variant="outline" className="min-h-12 sm:min-h-control" onClick={() => onDialog({ kind: "pack", req: r })} data-testid="fu-generate">
              <FileText aria-hidden />
              {r.pack_no ? t("regenerate") : t("generate")}
            </Button>
          ) : null}
          <Button className="min-h-12 sm:min-h-control" onClick={() => onDialog({ kind: "submit", req: r })} data-testid="fu-submit">
            <Send aria-hidden />
            {t("record")}
          </Button>
        </div>
      ) : null}
      {packable && gate ? (
        <p className="flex items-start gap-2 text-sm text-muted-foreground" data-testid="fu-pack-gate" data-reason={gate.reason}>
          {gate.reason === "needsIdentity" ? <Lock aria-hidden className="mt-0.5 size-4 shrink-0" /> : <Info aria-hidden className="mt-0.5 size-4 shrink-0" />}
          {td(`pack.${gate.reason}`)}
        </p>
      ) : null}
      {done || (caps.settings && isOpen) ? (
        <div>
          <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} aria-expanded={open} data-testid="fu-req-more">
            <ChevronDown aria-hidden className={cn("transition-transform", open && "rotate-180")} />
            {done ? t("submissions") : t("more")}
          </Button>
          {open ? <RequirementMore r={r} projectId={projectId} onDialog={onDialog} /> : null}
        </div>
      ) : null}
    </li>
  );
}

/** Submissions of a requirement (evidence count, acknowledgement) and the record actions: void (217), waive (218). */
function RequirementMore({ r, projectId, onDialog }: { r: Req; projectId: string; onDialog: (d: Dialog) => void }) {
  const t = useTranslations("fu.req");
  const te = useTranslations("enums");
  const caps = useFuCaps(projectId);
  const name = useLocalizedName();
  const bi = useBi();
  const { dateTime } = useFormatters(projectId);
  const q = useFuSubmissions(projectId, { requirement_id: r.id });
  const subs = q.data?.items ?? [];
  const live = subs.filter((s) => s.status !== "voided");
  return (
    <div className="mt-2 flex flex-col gap-2" data-testid="fu-req-detail">
      {q.isLoading ? <LoadingState rows={1} /> : null}
      {subs.map((s) => (
        <div key={s.id} className="flex flex-col gap-1 rounded-md border bg-muted/30 p-3 text-sm" data-testid="fu-sub" data-status={s.status}>
          <span className="flex flex-wrap items-center gap-2">
            <Code>{s.submission_no}</Code>
            <FuBadge group="fuSubmissionStatus" status={s.status} testId="fu-sub-status" />
            <OnTimeBadge onTime={s.on_time} />
          </span>
          <span>
            {te(`fuChannel.${s.channel}`)} · {dateTime(s.submitted_at)}
            {s.recorded_by ? ` · ${name(s.recorded_by.full_name_en, s.recorded_by.full_name_ar)}` : ""}
          </span>
          {s.contacted_desk_en || s.contacted_desk_ar ? <span className="text-muted-foreground">{bi(s.contacted_desk_en, s.contacted_desk_ar)}</span> : null}
          {s.reference_no ? (
            <span>
              {t("ref")} <Code>{s.reference_no}</Code>
            </span>
          ) : null}
          {s.evidence_file_ids ? (
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Stamp aria-hidden className="size-4" />
              {t("evidenceCount", { n: s.evidence_file_ids.length })}
            </span>
          ) : null}
          {s.acknowledged_at ? (
            <span className="text-success" data-testid="fu-sub-ack">
              {t("acknowledgedAt", { at: dateTime(s.acknowledged_at) })}
              {s.ack_reference ? (
                <>
                  {" · "}
                  <Code>{s.ack_reference}</Code>
                </>
              ) : null}
            </span>
          ) : null}
          {s.void_reason ? <span className="text-muted-foreground">{s.void_reason}</span> : null}
          {caps.record && s.status === "recorded" ? (
            <Button variant="outline" size="sm" className="mt-1 w-fit" onClick={() => onDialog({ kind: "ack", sub: s, req: r })} data-testid="fu-ack">
              {t("recordAck")}
            </Button>
          ) : null}
        </div>
      ))}
      {(caps.approve && live.length) || (caps.settings && OPEN.includes(r.status)) ? (
        <RecordActions testId="fu-req-end" className="mt-2">
          {caps.approve
            ? live.map((s) => (
                <Button key={s.id} variant="destructive-outline" size="sm" onClick={() => onDialog({ kind: "void", sub: s, req: r })} data-testid="fu-void">
                  {t("void", { no: s.submission_no })}
                </Button>
              ))
            : null}
          {caps.settings && OPEN.includes(r.status) ? (
            <Button variant="destructive-outline" size="sm" onClick={() => onDialog({ kind: "waive", req: r })} data-testid="fu-waive">
              {t("waive")}
            </Button>
          ) : null}
        </RecordActions>
      ) : null}
    </div>
  );
}

/* ═════════════ Phase 1 incident page: "Notifications & follow-up" panel (6f §8.4) ═════════════ */

export function IncidentFollowupPanel({ incident }: { incident: S["IncidentRead"] }) {
  const t = useTranslations("fu.panel");
  const caps = useFuCaps(incident.project_id);
  const q = useFuRequirements(incident.project_id, { incident_id: incident.id, page_size: 100 }, { enabled: caps.view });
  if (!caps.view) return null;
  const items = q.data?.items ?? [];
  // Incidents before the project's switch date keep the Phase 1 items only (NR-1): no panel then.
  if (q.isSuccess && items.length === 0) return null;
  const overdue = items.filter((r) => r.status === "overdue").length;
  return (
    <Card data-testid="fu-panel">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {t("title")}
          {overdue ? <RequirementBadge status="overdue" /> : null}
        </CardTitle>
        <p className="text-xs text-muted-foreground">{t("hint")}</p>
        <DeadlineRule />
      </CardHeader>
      <CardContent>
        {q.isLoading ? <LoadingState rows={2} /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <RequirementList items={items} projectId={incident.project_id} incident={incident} />}
      </CardContent>
    </Card>
  );
}

/** Up to three similar Published lessons (LL-6), on the incident page for 222 holders. */
export function SimilarLessonsCard({ incident }: { incident: S["IncidentRead"] }) {
  const t = useTranslations("fu.similar");
  const caps = useFuCaps(incident.project_id);
  const q = useSimilarLessons(incident.id, { enabled: caps.library && incident.status !== "draft" });
  const ar = useLocale() === "ar";
  if (!caps.library || incident.status === "draft") return null;
  const items = q.data?.items ?? [];
  return (
    <Card data-testid="similar-lessons">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Lightbulb aria-hidden className="size-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {q.isLoading ? (
          <LoadingState rows={1} />
        ) : items.length === 0 ? (
          <EmptyState message={t("none")} />
        ) : (
          <ul className="flex flex-col divide-y">
            {items.map((l) => (
              <li key={l.id} className="flex flex-col gap-1 py-2 text-sm" data-testid="similar-lesson">
                <Link href={`/lessons/${l.id}`} className="inline-flex min-h-touch items-center gap-2 font-medium text-primary hover:underline">
                  <BookOpen aria-hidden className="size-4 shrink-0" />
                  <Code>{l.lesson_no}</Code>
                </Link>
                <span>{ar ? (l.title_ar ?? l.title_en) : (l.title_en ?? l.title_ar)}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
