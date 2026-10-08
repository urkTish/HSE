"use client";
import { Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ExportButtons } from "@/components/common/export-buttons";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, DeploymentPicker, StepDialog, WorkerLabel } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useBlacklistRegister, useCertificationBans, useCertRefresh } from "@/lib/api/cert";
import { BAN_REASONS, BAN_STATUSES, BLACKLIST_SUBJECTS } from "@/lib/cert-enums";
import { todayInZone } from "@/lib/datetime";
import { can } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { PersonnelSubNav, Tick, UserName, useCertTypes } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

/* ───────────── certification bans (person) ───────────── */

export function BanListPage() {
  return <ProjectGate>{(p) => <BanList project={p} />}</ProjectGate>;
}

function BanList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("bans");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const { date, dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["BanStatus"][];
  const q = useCertificationBans({ status: status.length ? status : null, review_due: s.get("review_due") === "1" ? true : null, page, page_size: PAGE_SIZE });
  const [create, setCreate] = useState(false);
  const [lift, setLift] = useState<S["CertificationBanRead"] | null>(null);
  const [reason, setReason] = useState("");
  const refresh = useCertRefresh();
  const manager = can(me, "cert.blacklist");
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          manager ? (
            <Button variant="destructive-outline" onClick={() => setCreate(true)} data-testid="new-ban">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <PersonnelSubNav />
      <ListToolbar>
        <MultiSelect id="bn-status" label={tc("status")} options={BAN_STATUSES.map((x) => ({ value: x, label: te(`banStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="bn-review" label={t("reviewDue")} value={s.get("review_due") ?? ""} onChange={(v) => s.set({ review_due: v })} options={[{ value: "1", label: tc("yes") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="bans-table">
            <THead>
              <TR>
                <TH>{t("worker")}</TH>
                <TH>{t("scope")}</TH>
                <TH>{tc("reason")}</TH>
                <TH>{t("from")}</TH>
                <TH>{t("reviewOn")}</TH>
                <TH>{tc("status")}</TH>
                <TH>
                  <span className="sr-only">{tc("actions")}</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {items.map((b) => (
                <TR key={b.id} data-testid="ban-row" data-worker={b.worker.worker_no}>
                  <TD label={t("worker")}>
                    <WorkerLabel w={b.worker} link />
                  </TD>
                  <TD label={t("scope")}>{b.scope_all ? t("allTypes") : b.cert_types.map((c) => <Code key={c} className="me-1">{c}</Code>)}</TD>
                  <TD label={tc("reason")}>
                    {/* Contractor HSE Reps see the "not accepted" message only (BL-5): no reason is returned. */}
                    {b.reason_code ? te(`banReason.${b.reason_code}`) : locale === "ar" ? b.message_ar : b.message_en}
                    {b.reason_text ? <span className="block text-xs text-muted-foreground">{b.reason_text}</span> : null}
                  </TD>
                  <TD label={t("from")}>
                    {date(b.from_date)}
                    {b.created_by ? (
                      <span className="block text-xs text-muted-foreground">
                        <UserName u={b.created_by} />
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("reviewOn")}>{date(b.review_due_on)}</TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={b.status === "active" ? "banned" : "lifted"} label={te(`banStatus.${b.status}`)} />
                    {b.lifted_at ? <span className="block text-xs text-muted-foreground">{dateTime(b.lifted_at)}</span> : null}
                  </TD>
                  <TD label={tc("actions")}>
                    {manager && b.status === "active" ? (
                      <Button size="sm" variant="outline" onClick={() => setLift(b)} data-testid="lift-ban">
                        {t("lift")}
                      </Button>
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
      {create ? <BanDialog project={project} onClose={() => setCreate(false)} /> : null}
      {lift ? (
        <StepDialog
          title={t("liftTitle")}
          description={t("liftHint")}
          confirmLabel={t("lift")}
          disabled={reason.trim().length < 5}
          onClose={() => {
            setLift(null);
            setReason("");
          }}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/certification-bans/{ban_id}/lift", { params: { path: { ban_id: lift.id } }, body: { reason: reason.trim() } }));
            await refresh();
            toast.success(t("lifted"));
          }}
          testId="lift-ban-confirm"
        >
          <FormField id="lb-reason" label={tc("reason")} required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="lb-reason" />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

/** BL-4: a certification ban blocks new certificates and makes existing ones not count; Phase 2 worker status is unchanged. */
function BanDialog({ project, onClose }: { project: S["ProjectRead"]; onClose: () => void }) {
  const t = useTranslations("bans");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useCertRefresh();
  const { types } = useCertTypes(project.id);
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [all, setAll] = useState(true);
  const [ctypes, setCtypes] = useState<string[]>([]);
  const [code, setCode] = useState<S["BanReason"]>("forged_certificate");
  const [text, setText] = useState("");
  const [from, setFrom] = useState(todayInZone());
  async function save() {
    await unwrap(api.POST("/api/v1/certification-bans", { body: { worker_id: (dep as S["DeploymentRead"]).worker_id, scope_all: all, cert_types: all ? [] : ctypes, reason_code: code, reason_text: text.trim(), from_date: from } }));
    await refresh();
    toast.success(t("created"));
  }
  return (
    <StepDialog title={t("new")} description={t("newHint")} confirmLabel={t("ban")} destructive onConfirm={save} onClose={onClose} disabled={!dep || text.trim().length < 20 || (!all && !ctypes.length)} wide testId="ban-confirm">
      <DeploymentPicker id="bn-worker" projectId={project.id} value={dep} onChange={setDep} label={t("worker")} required />
      <Tick id="bn-all" label={t("allTypes")} checked={all} onChange={setAll} />
      {!all ? <MultiSelect id="bn-types" label={t("certTypes")} options={types.map((c) => ({ value: c.code, label: `${c.code} — ${c.label_en}` }))} value={ctypes} onChange={setCtypes} /> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="bn-code" label={tc("reason")} required>
          <Select value={code} onChange={(e) => setCode(e.target.value as S["BanReason"])}>
            {BAN_REASONS.map((x) => (
              <option key={x} value={x}>
                {te(`banReason.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="bn-from" label={t("from")} required>
          <Input type="date" className="ltr" value={from} onChange={(e) => setFrom(e.target.value)} />
        </FormField>
      </div>
      <FormField id="bn-text" label={t("details")} required hint={t("reason20")}>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} data-testid="bn-text" />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── blacklist register (equipment, persons, TPIs) ───────────── */

export function BlacklistRegisterPage() {
  return <ProjectGate>{(p) => <BlacklistRegister project={p} />}</ProjectGate>;
}

function BlacklistRegister({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("bans");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const subject = s.get("subject") as S["BlacklistSubject"] | null;
  const q = useBlacklistRegister({ subject: subject ? [subject] : null, project_id: s.get("all") === "1" ? null : project.id, active_only: s.get("history") === "1" ? false : true });
  const items = q.data?.items ?? [];
  const reasonLabel = (c: string | null) => {
    if (!c) return t("notAcceptedOnly");
    if (te.has(`banReason.${c as S["BanReason"]}`)) return te(`banReason.${c as S["BanReason"]}`);
    if (te.has(`equipmentBlacklistReason.${c as S["EquipmentBlacklistReason"]}`)) return te(`equipmentBlacklistReason.${c as S["EquipmentBlacklistReason"]}`);
    return c;
  };
  const href = (r: S["BlacklistRegisterRow"]) => (r.subject === "equipment" ? `/equipment/${r.subject_id}` : r.subject === "tpi" ? `/tpis/${r.subject_id}` : `/workers/${r.subject_id}`);
  return (
    <div>
      <PageHeader title={t("registerTitle")} description={t("registerSubtitle")} />
      <PersonnelSubNav />
      <ListToolbar actions={can(me, "export.cert", project.id) ? <ExportButtons dataset="blacklist_register" params={{ project_id: project.id }} /> : null}>
        <SelectFilter id="bl-subject" label={t("subject")} value={s.get("subject") ?? ""} onChange={(v) => s.set({ subject: v })} options={BLACKLIST_SUBJECTS.map((x) => ({ value: x, label: te(`blacklistSubject.${x}`) }))} />
        <SelectFilter id="bl-all" label={t("scope")} value={s.get("all") ?? ""} onChange={(v) => s.set({ all: v })} options={[{ value: "1", label: t("allProjects") }]} />
        <SelectFilter id="bl-history" label={t("include")} value={s.get("history") ?? ""} onChange={(v) => s.set({ history: v })} options={[{ value: "1", label: t("includeLifted") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="blacklist-table">
          <THead>
            <TR>
              <TH>{t("subject")}</TH>
              <TH>{t("ref")}</TH>
              <TH>{tc("reason")}</TH>
              <TH>{t("from")}</TH>
              <TH>{t("reviewOn")}</TH>
              <TH>{tc("status")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((r) => (
              <TR key={`${r.subject}-${r.subject_id}-${r.from_date}`} data-testid="blacklist-row" data-ref={r.ref} data-subject={r.subject}>
                <TD label={t("subject")}>{te(`blacklistSubject.${r.subject}`)}</TD>
                <TD label={t("ref")}>
                  <Link href={href(r)} className="text-primary hover:underline">
                    <Code>{r.ref}</Code>
                  </Link>
                  <span className="block text-xs text-muted-foreground">{locale === "ar" ? r.label_ar : r.label_en}</span>
                </TD>
                <TD label={tc("reason")}>{reasonLabel(r.reason_code)}</TD>
                <TD label={t("from")}>{date(r.from_date)}</TD>
                <TD label={t("reviewOn")}>{r.review_due_on ? date(r.review_due_on) : "—"}</TD>
                <TD label={tc("status")}>
                  <StatusBadge status={r.status === "active" || r.status === "blacklisted" ? "blacklisted" : "lifted"} label={te.has(`banStatus.${r.status as S["BanStatus"]}`) ? te(`banStatus.${r.status as S["BanStatus"]}`) : r.status} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("registerEmpty")} />
      )}
    </div>
  );
}
