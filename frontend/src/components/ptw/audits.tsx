"use client";
import { Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { StepDialog } from "@/components/access/common";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { usePermits, usePtwAudit, usePtwAuditChecklist, usePtwAudits, usePtwRefresh } from "@/lib/api/ptw";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { AUDIT_FINDING_SEVERITIES, PTW_AUDIT_STATUSES, PTW_AUDIT_TYPES } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { DateTimeInput, nowIso, PermitNo, userLabel } from "./common";

type S = Schemas;
type Ans = { answer: S["AuditAnswer"] | null; severity: S["AuditFindingSeverity"] | null; note: string };
const PAGE_SIZE = 50;
const ansKey = (a: S["AuditAnswer"]) => (a === "n.a." ? "na" : a);

/* ───────────── register ───────────── */

export function PtwAuditListPage() {
  return <ProjectGate>{(p) => <AuditList project={p} />}</ProjectGate>;
}

function AuditList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("ptwAudits");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const opts = useProjectOptions(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const types = s.getAll("audit_type") as S["PtwAuditType"][];
  const status = s.getAll("status") as S["PtwAuditStatus"][];
  const engs = s.getAll("engagement_id");
  const q = usePtwAudits(project.id, {
    audit_type: types.length ? types : null,
    status: status.length ? status : null,
    engagement_id: engs.length ? engs : null,
    permit_id: s.get("permit_id") || null,
    date_from: s.get("date_from") || null,
    date_to: s.get("date_to") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          canWrite(me, "ptw_audit.conduct", project.id) ? (
            <Button asChild>
              <Link href="/ptw-audits/new" data-testid="new-ptw-audit">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar>
        <MultiSelect id="pa-type" label={t("type")} options={PTW_AUDIT_TYPES.map((x) => ({ value: x, label: te(`ptwAuditType.${x}`) }))} value={types} onChange={(v) => s.set({ audit_type: v })} />
        <MultiSelect id="pa-status" label={tc("status")} options={PTW_AUDIT_STATUSES.map((x) => ({ value: x, label: te(`ptwAuditStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="pa-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <FormField id="pa-from" label={t("from")}>
          <Input id="pa-from" type="date" className="ltr" value={s.get("date_from") ?? ""} onChange={(e) => s.set({ date_from: e.target.value })} />
        </FormField>
        <FormField id="pa-to" label={t("to")}>
          <Input id="pa-to" type="date" className="ltr" value={s.get("date_to") ?? ""} onChange={(e) => s.set({ date_to: e.target.value })} />
        </FormField>
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="ptw-audits-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("type")}</TH>
                <TH>{t("permit")}</TH>
                <TH>{tc("contractor")}</TH>
                <TH>{t("auditor")}</TH>
                <TH>{t("score")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="ptw-audit-row">
                  <TD label={t("no")}>
                    <Link href={`/ptw-audits/${a.id}`} className="ltr font-medium text-primary hover:underline">
                      {a.audit_no}
                    </Link>
                    <span className="ltr block text-xs text-muted-foreground">{dateTime(a.audited_at)}</span>
                  </TD>
                  <TD label={t("type")}>{te(`ptwAuditType.${a.audit_type}`)}</TD>
                  <TD label={t("permit")}>{a.permit ? <PermitNo p={a.permit} /> : (a.zone?.code ?? "—")}</TD>
                  <TD label={tc("contractor")}>{a.engagement.short_code}</TD>
                  <TD label={t("auditor")}>{userLabel(a.auditor, locale)}</TD>
                  <TD label={t("score")}>
                    <bdi className="ltr tabular-nums">{a.score_pct !== null ? `${a.score_pct} %` : "—"}</bdi>
                    {a.critical_count ? <span className="block text-xs text-danger">{t("criticalN", { n: a.critical_count })}</span> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={a.status} label={te(`ptwAuditStatus.${a.status}`)} />
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
    </div>
  );
}

/* ───────────── checklist editor ───────────── */

function ItemsEditor({ items, answers, onChange, disabled }: { items: S["AuditItemRead"][]; answers: Record<string, Ans>; onChange: (a: Record<string, Ans>) => void; disabled?: boolean }) {
  const t = useTranslations("ptwAudits");
  const te = useTranslations("enums");
  const locale = useLocale();
  return (
    <ol className="flex flex-col divide-y rounded-md border" data-testid="audit-items">
      {items.map((i) => {
        const v = answers[i.code] ?? { answer: null, severity: null, note: "" };
        const set = (p: Partial<Ans>) => onChange({ ...answers, [i.code]: { ...v, ...p } });
        const nc = v.answer === "non_compliant";
        return (
          <li key={i.code} className={cn("flex flex-col gap-2 p-3", !i.applies && "bg-muted/40")} data-testid="audit-item" data-code={i.code} data-applies={i.applies ? "true" : "false"}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <span className="text-sm">
                <bdi className="ltr me-1.5 font-mono text-xs text-muted-foreground">{i.code}</bdi>
                {locale === "ar" ? i.label_ar : i.label_en}
                <span className="ms-1.5 text-xs text-muted-foreground">({te(`findingSeverityPtw.${i.default_severity}`)})</span>
              </span>
              <span role="radiogroup" aria-label={i.code} className="flex gap-1">
                {(["compliant", "non_compliant", "n.a."] as const)
                  .filter((a) => a !== "n.a." || !i.applies)
                  .map((a) => (
                    <label key={a} className={cn("inline-flex min-h-touch cursor-pointer items-center gap-1 rounded-md border px-2 text-xs", v.answer === a && (a === "non_compliant" ? "border-danger bg-danger-bg" : a === "compliant" ? "border-success bg-success-bg" : "border-input bg-muted"))}>
                      <input type="radio" name={`ans-${i.code}`} className="sr-only" checked={v.answer === a} disabled={disabled} onChange={() => set({ answer: a, severity: a === "non_compliant" ? (v.severity ?? i.default_severity) : null })} data-testid={`ans-${i.code}-${ansKey(a)}`} />
                      {te(`auditAnswer.${ansKey(a)}`)}
                    </label>
                  ))}
              </span>
            </div>
            {nc ? (
              <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
                <Select aria-label={t("severity")} value={v.severity ?? i.default_severity} disabled={disabled} onChange={(e) => set({ severity: e.target.value as S["AuditFindingSeverity"] })} data-testid={`sev-${i.code}`}>
                  {AUDIT_FINDING_SEVERITIES.map((x) => (
                    <option key={x} value={x}>
                      {te(`findingSeverityPtw.${x}`)}
                    </option>
                  ))}
                </Select>
                <Input aria-label={t("finding")} placeholder={t("findingHint")} value={v.note} disabled={disabled} onChange={(e) => set({ note: e.target.value })} />
              </div>
            ) : null}
            {nc && (v.severity ?? i.default_severity) === "critical" ? <p className="text-xs text-danger">{t("criticalHint")}</p> : null}
          </li>
        );
      })}
    </ol>
  );
}

function toBody(answers: Record<string, Ans>): S["AuditItemInput"][] {
  return Object.entries(answers)
    .filter(([, v]) => v.answer)
    .map(([code, v]) => ({ code: code as S["AuditItem"], answer: v.answer as S["AuditAnswer"], severity: v.answer === "non_compliant" ? v.severity : null, note: v.note.trim() || null }));
}

function fromItems(items: S["AuditItemRead"][]): Record<string, Ans> {
  return Object.fromEntries(items.map((i) => [i.code, { answer: i.answer, severity: i.severity, note: i.note ?? "" }]));
}

/* ───────────── create ───────────── */

export function PtwAuditCreatePage() {
  return <ProjectGate>{(p) => <AuditCreate project={p} />}</ProjectGate>;
}

function AuditCreate({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("ptwAudits");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const router = useRouter();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const [type, setType] = useState<S["PtwAuditType"]>((s.get("audit_type") as S["PtwAuditType"] | null) ?? "field");
  const [permit, setPermit] = useState(s.get("permit_id") ?? "");
  const [at, setAt] = useState(nowIso());
  const [site, setSite] = useState("");
  const [zone, setZone] = useState("");
  const [eng, setEng] = useState("");
  const [stopAt, setStopAt] = useState(nowIso());
  const [desc, setDesc] = useState("");
  const [answers, setAnswers] = useState<Record<string, Ans>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const statuses: S["PermitStatus"][] = type === "field" ? ["issued", "active", "suspended"] : ["closed", "expired"];
  const pq = usePermits(project.id, { status: statuses, page_size: 200 }, { enabled: type !== "unpermitted_work" });
  const cq = usePtwAuditChecklist(project.id, type, type === "unpermitted_work" ? null : permit || null);
  const ready = type === "unpermitted_work" ? Boolean(site && eng && desc.trim().length >= 10) : Boolean(permit);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const a = await unwrap(
        api.POST("/api/v1/projects/{project_id}/ptw-audits", {
          params: { path: { project_id: project.id } },
          body:
            type === "unpermitted_work"
              ? { audit_type: type, site_id: site, zone_id: zone || null, engagement_id: eng, audited_at: at, stop_work_issued_at: stopAt, unpermitted_work_desc: desc.trim(), items: toBody(answers) }
              : { audit_type: type, permit_id: permit, audited_at: at, items: toBody(answers) },
        }),
      );
      toast.success(t("createdToast", { no: a.audit_no }));
      router.push(`/ptw-audits/${a.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/ptw-audits" }, { label: t("new") }]} />
        <PageHeader title={t("new")} description={t("newHint")} />
      </div>
      <FormSection title={t("what")}>
        <FormField id="ac-type" label={t("type")} required>
          <Select
            id="ac-type"
            value={type}
            onChange={(e) => {
              setType(e.target.value as S["PtwAuditType"]);
              setPermit("");
              setAnswers({});
            }}
            data-testid="audit-type"
          >
            {PTW_AUDIT_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`ptwAuditType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ac-at" label={t("auditedAt")} required>
          <DateTimeInput id="ac-at" value={at} onChange={setAt} />
        </FormField>
        {type !== "unpermitted_work" ? (
          <FormField id="ac-permit" label={t("permit")} required className="sm:col-span-2">
            <Select
              id="ac-permit"
              value={permit}
              onChange={(e) => {
                setPermit(e.target.value);
                setAnswers({});
              }}
              data-testid="audit-permit"
            >
              <option value="">—</option>
              {(pq.data?.items ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_no} · {p.title}
                </option>
              ))}
            </Select>
          </FormField>
        ) : (
          <>
            <FormField id="ac-site" label={tc("site")} required>
              <Select id="ac-site" value={site} onChange={(e) => setSite(e.target.value)}>
                <option value="">—</option>
                {opts.sites.map((x) => (
                  <option key={x.value} value={x.value}>
                    {x.label}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="ac-zone" label={tc("zone")}>
              <Select id="ac-zone" value={zone} onChange={(e) => setZone(e.target.value)}>
                <option value="">—</option>
                {opts.zones
                  .filter((z) => !site || z.siteId === site)
                  .map((z) => (
                    <option key={z.value} value={z.value}>
                      {z.label}
                    </option>
                  ))}
              </Select>
            </FormField>
            <FormField id="ac-eng" label={tc("contractor")} required>
              <Select id="ac-eng" value={eng} onChange={(e) => setEng(e.target.value)}>
                <option value="">—</option>
                {opts.engagements.map((x) => (
                  <option key={x.value} value={x.value}>
                    {x.label}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="ac-stop" label={t("stopWorkAt")} required>
              <DateTimeInput id="ac-stop" value={stopAt} onChange={setStopAt} />
            </FormField>
            <FormField id="ac-desc" label={t("unpermittedDesc")} required hint={t("unpermittedHint")} className="sm:col-span-2">
              <Textarea id="ac-desc" value={desc} onChange={(e) => setDesc(e.target.value)} />
            </FormField>
          </>
        )}
      </FormSection>
      {cq.data && (type === "unpermitted_work" || permit) ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("checklist")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">{t("checklistHint")}</p>
            <ItemsEditor items={cq.data.items} answers={answers} onChange={setAnswers} />
          </CardContent>
        </Card>
      ) : cq.isError ? (
        <ErrorState error={cq.error} onRetry={() => cq.refetch()} />
      ) : null}
      <MutationError error={error} />
      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={busy || !ready} data-testid="save-audit">
          {busy ? tc("saving") : t("saveDraft")}
        </Button>
      </div>
    </div>
  );
}

/* ───────────── audit page ───────────── */

export function PtwAuditDetail({ id }: { id: string }) {
  const t = useTranslations("ptwAudits");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const name = useLocalizedName();
  const q = usePtwAudit(id);
  const refresh = usePtwRefresh();
  const [answers, setAnswers] = useState<Record<string, Ans> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [completing, setCompleting] = useState(false);
  const [note, setNote] = useState("");
  const { dateTime } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const a = q.data;
  const mine = a.auditor.id === me.id && canWrite(me, "ptw_audit.conduct", a.project_id);
  const editable = a.status === "draft" && mine;
  const ans = answers ?? fromItems(a.items);
  const covered = new Set(a.cas.map((c) => c.item_code));
  const missing = a.required_cas.filter((c) => !covered.has(c));
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.PATCH("/api/v1/ptw-audits/{audit_id}", { params: { path: { audit_id: a.id } }, body: { items: toBody(ans) } }));
      await refresh();
      setAnswers(null);
      toast.success(tc("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const caHref = (code: S["AuditItem"]) => {
    const item = a.items.find((i) => i.code === code);
    const sev = item?.severity ?? item?.default_severity;
    const params = new URLSearchParams({
      source_type: "ptw_audit",
      source_id: a.id,
      source_ref: `${a.audit_no} ${code}`,
      title: `${code} ${item?.label_en ?? ""}`.slice(0, 150),
      priority: sev === "critical" ? "critical" : "high",
      engagement_id: a.engagement.id,
      site_id: a.site.id,
      ...(a.zone ? { zone_id: a.zone.id } : {}),
    });
    return `/actions/new?${params.toString()}`;
  };
  return (
    <div className="flex flex-col gap-5" data-testid="ptw-audit-detail" data-status={a.status}>
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/ptw-audits" }, { label: a.audit_no }]} />
        <PageHeader
          title={<bdi className="ltr">{a.audit_no}</bdi>}
          description={te(`ptwAuditType.${a.audit_type}`)}
          actions={
            <>
              <StatusBadge status={a.status} label={te(`ptwAuditStatus.${a.status}`)} />
              {editable ? (
                <Button onClick={() => setCompleting(true)} data-testid="complete-audit">
                  {t("complete")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {a.permit_suspended ? (
        <Alert tone="danger" data-testid="audit-suspended">
          {t("permitSuspended")}
        </Alert>
      ) : null}
      {missing.length && a.status === "draft" ? (
        <Alert tone="warning" data-testid="cas-missing">
          {t("casMissing", { list: missing.join(", ") })}
        </Alert>
      ) : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            {a.permit ? (
              <FieldItem label={t("permit")}>
                <PermitNo p={a.permit} />
              </FieldItem>
            ) : null}
            <FieldItem label={tc("site")}>{name(a.site.name_en, a.site.name_ar)}</FieldItem>
            <FieldItem label={tc("zone")}>{a.zone ? `${a.zone.code} — ${name(a.zone.name_en, a.zone.name_ar)}` : "—"}</FieldItem>
            <FieldItem label={tc("contractor")}>{a.engagement.short_code}</FieldItem>
            <FieldItem label={t("auditor")}>{userLabel(a.auditor, locale)}</FieldItem>
            <FieldItem label={t("auditedAt")}>
              <span className="ltr">{dateTime(a.audited_at)}</span>
            </FieldItem>
            <FieldItem label={t("score")}>
              <span data-testid="audit-score" className="ltr tabular-nums">
                {a.score_pct !== null ? `${a.score_pct} %` : "—"} ({a.compliant_count}/{a.applicable_count})
              </span>
            </FieldItem>
            <FieldItem label={t("critical")}>
              <span className={cn("tabular-nums", a.critical_count && "font-semibold text-danger")}>{a.critical_count}</span>
            </FieldItem>
            {a.unpermitted_work_desc ? <FieldItem label={t("unpermittedDesc")}>{a.unpermitted_work_desc}</FieldItem> : null}
            {a.stop_work_issued_at ? (
              <FieldItem label={t("stopWorkAt")}>
                <span className="ltr">{dateTime(a.stop_work_issued_at)}</span>
              </FieldItem>
            ) : null}
            {a.locks_at && a.status === "completed" ? (
              <FieldItem label={t("locksAt")}>
                <span className="ltr">{dateTime(a.locks_at)}</span>
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("checklist")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <ItemsEditor items={a.items} answers={ans} onChange={setAnswers} disabled={!editable} />
          <MutationError error={error} />
          {editable && answers ? (
            <div className="flex justify-end">
              <Button onClick={() => void save()} disabled={busy} data-testid="save-audit">
                {busy ? tc("saving") : tc("save")}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Card data-testid="audit-cas">
        <CardHeader>
          <CardTitle className="text-base">{t("cas")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {a.cas.length ? (
            <ul className="flex flex-col divide-y rounded-md border">
              {a.cas.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-2 p-2">
                  <Link href={`/actions/${c.id}`} className="ltr font-medium text-primary hover:underline">
                    {c.ref}
                  </Link>
                  {c.item_code ? <bdi className="ltr font-mono text-xs">{c.item_code}</bdi> : null}
                  <span className="text-xs text-muted-foreground">{te.has(`caPriority.${c.priority}` as "caPriority.high") ? te(`caPriority.${c.priority}` as "caPriority.high") : c.priority}</span>
                  <StatusBadge status={c.status} label={te.has(`caStatus.${c.status}` as "caStatus.open") ? te(`caStatus.${c.status}` as "caStatus.open") : c.status} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">{t("noCas")}</p>
          )}
          {missing.length && canWrite(me, "ca.create", a.project_id) ? (
            <div className="flex flex-wrap gap-2">
              {missing.map((c) => (
                <Button key={c} size="sm" variant="outline" asChild>
                  <Link href={caHref(c)} data-testid={`raise-ca-${c}`}>
                    {t("raiseCa", { code: c })}
                  </Link>
                </Button>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("photos")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Attachments ownerType="ptw_audit_photo" ownerId={a.id} canUpload={editable} canDelete={editable} hint={t("photosHint")} />
        </CardContent>
      </Card>
      <HistoryPanel entityType="ptw_audit" entityId={a.id} projectId={a.project_id} />
      {completing ? (
        <StepDialog
          title={t("completeTitle")}
          description={t("completeHint")}
          confirmLabel={t("complete")}
          onClose={() => setCompleting(false)}
          testId="complete-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/ptw-audits/{audit_id}/complete", { params: { path: { audit_id: a.id } }, body: { note: note.trim() || null } }));
            await refresh();
            toast.success(te("ptwAuditStatus.completed"));
          }}
        >
          <FormField id="cmp-note" label={t("note")}>
            <Textarea id="cmp-note" value={note} onChange={(e) => setNote(e.target.value)} />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}
