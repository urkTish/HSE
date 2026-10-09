"use client";
import { AlertTriangle, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, PossibleIdHint } from "@/components/common/api-warnings";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { DateFilter } from "@/components/training/common";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useBanExemptions, useBanPatrols, useHeatRefresh, useHeatSettings } from "@/lib/api/heat";
import { zonedInputToUtc } from "@/lib/datetime";
import { EXEMPTION_REASONS, EXEMPTION_STATUSES, PATROL_OUTCOMES } from "@/lib/heat-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { Codes, FreeText, HeatBanSubNav, HeatReasonDialog, RecordStatusBadge, nowLocalInput, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

const OUTCOME_TONE: Record<S["PatrolOutcome"], "success" | "info" | "danger"> = {
  no_outdoor_work: "success",
  compliant_shaded_or_indoor: "success",
  exempt_work: "info",
  violation: "danger",
};

function BanWindow({ project }: { project: Project }) {
  const t = useTranslations("heat.ban");
  const s = useHeatSettings(project.id);
  const d = s.data;
  if (!d) return null;
  return (
    <p className="mb-3 text-sm text-muted-foreground" data-testid="ban-window">
      {t("window", { from: d.midday_ban_period.start_mmdd, to: d.midday_ban_period.end_mmdd, start: d.midday_ban_hours.start_local.slice(0, 5), end: d.midday_ban_hours.end_local.slice(0, 5) })}
    </p>
  );
}

/* ═════════════ patrols (§3.9, MB-1…MB-4) ═════════════ */

export function BanPatrolsPage() {
  return <ProjectGate>{(p) => <Patrols project={p} />}</ProjectGate>;
}

function Patrols({ project }: { project: Project }) {
  const t = useTranslations("heat.ban");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const zone = s.get("zone") ?? "";
  const outcome = (s.get("outcome") ?? "") as S["PatrolOutcome"] | "";
  const day = s.get("day") ?? "";
  const q = useBanPatrols(project.id, { zone_id: zone || null, outcome: outcome || null, day: day || null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  const [record, setRecord] = useState(false);
  const [voiding, setVoiding] = useState<S["PatrolRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("patrolsTitle")}
        description={t("patrolsSubtitle")}
        actions={
          caps.patrol ? (
            <Button onClick={() => setRecord(true)} data-testid="new-patrol">
              <Plus aria-hidden />
              {t("record")}
            </Button>
          ) : null
        }
      />
      <HeatBanSubNav />
      <BanWindow project={project} />
      <ListToolbar>
        <SelectFilter id="bp-zone" label={t("zone")} value={zone} onChange={(v) => s.set({ zone: v })} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} />
        <SelectFilter id="bp-outcome" label={t("outcome")} value={outcome} onChange={(v) => s.set({ outcome: v })} options={PATROL_OUTCOMES.map((x) => ({ value: x, label: te(`patrolOutcome.${x}`) }))} />
        <DateFilter id="bp-day" label={t("day")} value={day} onChange={(v) => s.set({ day: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="patrols-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("zone")}</TH>
                <TH>{t("checkedAt")}</TH>
                <TH>{t("outcome")}</TH>
                <TH>{t("work")}</TH>
                <TH>{t("ca")}</TH>
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="patrol-row" data-no={x.patrol_no} data-outcome={x.outcome}>
                  <TD label={t("no")}>
                    <Code className="font-medium">{x.patrol_no}</Code>
                  </TD>
                  <TD label={t("zone")}>
                    <Code>{x.zone_code}</Code>
                  </TD>
                  <TD label={t("checkedAt")}>
                    <span className="whitespace-nowrap">{dateTime(x.checked_at)}</span>
                    <span className="block text-xs text-muted-foreground">
                      <UserName u={x.checked_by} />
                    </span>
                  </TD>
                  <TD label={t("outcome")}>
                    <Badge tone={OUTCOME_TONE[x.outcome]}>
                      {x.outcome === "violation" ? <AlertTriangle aria-hidden /> : null}
                      {te(`patrolOutcome.${x.outcome}`)}
                    </Badge>
                  </TD>
                  <TD label={t("work")}>
                    {x.contractor_code ? <Code>{x.contractor_code}</Code> : null}
                    {x.headcount ? <span className="ms-1">· {t("persons", { n: x.headcount })}</span> : null}
                    <FreeText className="block text-xs text-muted-foreground">{x.activity}</FreeText>
                    {x.exemption_ref ? <Code className="block text-xs">{x.exemption_ref}</Code> : null}
                    {!x.contractor_code && !x.activity ? "—" : null}
                  </TD>
                  <TD label={t("ca")}>{x.ca_ref ? <Code>{x.ca_ref}</Code> : "—"}</TD>
                  <TD label={tc("status")}>
                    <RecordStatusBadge status={x.status} />
                  </TD>
                  <TD>
                    {caps.void && x.status === "valid" ? (
                      <Button size="sm" variant="destructive-outline" onClick={() => setVoiding(x)} data-testid="patrol-void">
                        {t("void")}
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
        <EmptyState message={zone || outcome || day ? undefined : t("noPatrols")} />
      )}
      {record ? <PatrolDialog project={project} onClose={() => setRecord(false)} /> : null}
      {voiding ? (
        <HeatReasonDialog
          title={t("voidTitle", { no: voiding.patrol_no })}
          confirmLabel={t("void")}
          onConfirm={async (reason) => {
            await unwrap(api.POST("/api/v1/ban-patrols/{patrol_id}/void", { params: { path: { patrol_id: voiding.id } }, body: { reason } }));
          }}
          onClose={() => setVoiding(null)}
        />
      ) : null}
    </div>
  );
}

function PatrolDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("heat.ban");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useHeatRefresh();
  const opts = useProjectOptions(project.id);
  const [zone, setZone] = useState("");
  const [at, setAt] = useState(nowLocalInput());
  const [outcome, setOutcome] = useState<S["PatrolOutcome"] | "">("");
  const [eng, setEng] = useState("");
  const [head, setHead] = useState("");
  const [activity, setActivity] = useState("");
  const [result, setResult] = useState<S["PatrolRead"] | null>(null);
  const shown = useRef<S["PatrolRead"] | null>(null);
  const work = outcome === "violation" || outcome === "exempt_work";
  if (result) {
    return (
      <StepDialog title={t("recorded", { no: result.patrol_no })} confirmLabel={tc("close")} onConfirm={async () => undefined} onClose={onClose}>
        <div data-testid="patrol-recorded" data-no={result.patrol_no}>
          {result.ca_ref ? (
            <Alert tone="danger" data-testid="patrol-ca">
              {t("caRaised", { ref: result.ca_ref })}
            </Alert>
          ) : null}
          <ApiWarnings warnings={result.warnings} />
        </div>
      </StepDialog>
    );
  }
  return (
    <StepDialog
      title={t("record")}
      description={t("recordHint")}
      confirmLabel={t("save")}
      disabled={!zone || !at || !outcome || (work && (!eng || !head || !activity.trim()))}
      testId="patrol-confirm"
      onConfirm={async () => {
        if (!outcome) return;
        const r = await unwrap(
          api.POST("/api/v1/projects/{project_id}/ban-patrols", {
            params: { path: { project_id: project.id } },
            body: {
              zone_id: zone,
              checked_at: zonedInputToUtc(at),
              outcome,
              engagement_id: work ? eng : null,
              headcount: work ? Number(head) : null,
              activity: work ? activity.trim() : null,
            },
          }),
        );
        await refresh();
        if (r.ca_ref || r.warnings?.length) shown.current = r;
        else toast.success(t("recorded", { no: r.patrol_no }));
      }}
      onClose={() => (shown.current ? setResult(shown.current) : onClose())}
    >
      <FormField id="bp-z" label={t("zone")} required>
        <Select id="bp-z" value={zone} onChange={(e) => setZone(e.target.value)} data-testid="bp-zone">
          <option value="">{tc("select")}</option>
          {opts.zones.map((z) => (
            <option key={z.value} value={z.value}>
              {z.label}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="bp-at" label={t("checkedAt")} required hint={t("checkedAtHint")}>
        <Input id="bp-at" type="datetime-local" dir="ltr" value={at} onChange={(e) => setAt(e.target.value)} data-testid="bp-at" />
      </FormField>
      <fieldset className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t("outcome")}>
        <legend className="mb-1 text-sm font-medium">{t("outcome")}</legend>
        {PATROL_OUTCOMES.map((o) => (
          <Button key={o} type="button" role="radio" aria-checked={outcome === o} variant={outcome === o ? (o === "violation" ? "destructive" : "default") : "outline"} className="h-auto min-h-12 whitespace-normal" onClick={() => setOutcome(o)} data-testid={`bp-${o}`}>
            {te(`patrolOutcome.${o}`)}
          </Button>
        ))}
      </fieldset>
      {work ? (
        <>
          <FormField id="bp-eng" label={t("contractor")} required>
            <Select id="bp-eng" value={eng} onChange={(e) => setEng(e.target.value)} data-testid="bp-eng">
              <option value="">{tc("select")}</option>
              {opts.engagements.map((e) => (
                <option key={e.value} value={e.value}>
                  {e.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="bp-head" label={t("headcount")} required hint="1–500">
            <Input id="bp-head" inputMode="numeric" dir="ltr" value={head} onChange={(e) => setHead(e.target.value.replace(/[^0-9]/g, ""))} data-testid="bp-head" />
          </FormField>
          <FormField id="bp-activity" label={t("activity")} required>
            <Input id="bp-activity" value={activity} maxLength={200} onChange={(e) => setActivity(e.target.value)} data-testid="bp-activity" />
          </FormField>
          <PossibleIdHint text={activity} />
        </>
      ) : null}
      {outcome === "violation" ? <Alert tone="warning">{t("violationHint")}</Alert> : null}
    </StepDialog>
  );
}

/* ═════════════ exemptions (§3.10, MB-5) ═════════════ */

export function BanExemptionsPage() {
  return <ProjectGate>{(p) => <Exemptions project={p} />}</ProjectGate>;
}

const EX_TONE: Record<S["BanExemptionStatus"], string> = { active: "active", expired: "closed", revoked: "revoked" };

function Exemptions({ project }: { project: Project }) {
  const t = useTranslations("heat.ban");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["BanExemptionStatus"] | "";
  const q = useBanExemptions(project.id, { status: status || null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  const [grant, setGrant] = useState(false);
  const [revoke, setRevoke] = useState<S["BanExemptionRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("exemptionsTitle")}
        description={t("exemptionsSubtitle")}
        actions={
          caps.exempt ? (
            <Button onClick={() => setGrant(true)} data-testid="grant-exemption">
              <Plus aria-hidden />
              {t("grant")}
            </Button>
          ) : null
        }
      />
      <HeatBanSubNav />
      <BanWindow project={project} />
      <ListToolbar>
        <SelectFilter id="bx-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={EXEMPTION_STATUSES.map((x) => ({ value: x, label: te(`banExemptionStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="exemptions-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("contractor")}</TH>
                <TH>{t("zones")}</TH>
                <TH>{t("dates")}</TH>
                <TH>{t("reason")}</TH>
                <TH>{t("controls")}</TH>
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="exemption-row" data-no={x.exemption_no} data-status={x.status}>
                  <TD label={t("no")}>
                    <Code className="font-medium">{x.exemption_no}</Code>
                    <span className="block text-xs text-muted-foreground">
                      <UserName u={x.granted_by} /> · {dateTime(x.granted_at)}
                    </span>
                  </TD>
                  <TD label={t("contractor")}>{x.contractor_code ? <Code>{x.contractor_code}</Code> : "—"}</TD>
                  <TD label={t("zones")}>
                    <Codes items={x.zone_codes} />
                  </TD>
                  <TD label={t("dates")}>
                    <span className="whitespace-nowrap">
                      {date(x.date_from)} – {date(x.date_to)}
                    </span>
                  </TD>
                  <TD label={t("reason")}>{te(`banExemptionReason.${x.reason}`)}</TD>
                  <TD label={t("controls")}>
                    <FreeText className="text-xs">{x.controls_en}</FreeText>
                    <FreeText className="block text-xs text-muted-foreground">{x.controls_ar}</FreeText>
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={EX_TONE[x.status]} label={te(`banExemptionStatus.${x.status}`)} />
                    <FreeText className="block text-xs text-muted-foreground">{x.status === "revoked" ? x.status_reason : null}</FreeText>
                  </TD>
                  <TD>
                    {caps.exempt && x.status === "active" ? (
                      <Button size="sm" variant="destructive-outline" onClick={() => setRevoke(x)} data-testid="exemption-revoke">
                        {t("revoke")}
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
        <EmptyState message={status ? undefined : t("noExemptions")} />
      )}
      {grant ? <GrantDialog project={project} onClose={() => setGrant(false)} /> : null}
      {revoke ? (
        <HeatReasonDialog
          title={t("revokeTitle", { no: revoke.exemption_no })}
          confirmLabel={t("revoke")}
          onConfirm={async (reason) => {
            await unwrap(api.POST("/api/v1/ban-exemptions/{exemption_id}/revoke", { params: { path: { exemption_id: revoke.id } }, body: { reason } }));
          }}
          onClose={() => setRevoke(null)}
        />
      ) : null}
    </div>
  );
}

function GrantDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("heat.ban");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tcm = useTranslations("heat.common");
  const refresh = useHeatRefresh();
  const opts = useProjectOptions(project.id);
  const [eng, setEng] = useState("");
  const [zones, setZones] = useState<string[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reason, setReason] = useState<S["BanExemptionReason"] | "">("");
  const [en, setEn] = useState("");
  const [ar, setAr] = useState("");
  const controlsOk = en.trim().length >= 30 || ar.trim().length >= 30;
  return (
    <StepDialog
      title={t("grant")}
      description={t("grantHint")}
      confirmLabel={t("grant")}
      disabled={!eng || !zones.length || !from || !to || !reason || !controlsOk}
      testId="exemption-confirm"
      wide
      onConfirm={async () => {
        if (!reason) return;
        const r = await unwrap(
          api.POST("/api/v1/projects/{project_id}/ban-exemptions", {
            params: { path: { project_id: project.id } },
            body: { engagement_id: eng, zone_ids: zones, date_from: from, date_to: to, reason, controls_en: en.trim() || null, controls_ar: ar.trim() || null },
          }),
        );
        toast.success(t("granted", { no: r.exemption_no }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="bx-eng" label={t("contractor")} required>
        <Select id="bx-eng" value={eng} onChange={(e) => setEng(e.target.value)} data-testid="bx-eng">
          <option value="">{tc("select")}</option>
          {opts.engagements.map((e) => (
            <option key={e.value} value={e.value}>
              {e.label}
            </option>
          ))}
        </Select>
      </FormField>
      <MultiSelect id="bx-zones" label={t("zones")} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={setZones} />
      <div className="grid grid-cols-2 gap-3">
        <FormField id="bx-from" label={t("from")} required>
          <Input id="bx-from" type="date" dir="ltr" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="bx-from" />
        </FormField>
        <FormField id="bx-to" label={t("to")} required hint={t("maxDays")}>
          <Input id="bx-to" type="date" dir="ltr" value={to} onChange={(e) => setTo(e.target.value)} data-testid="bx-to" />
        </FormField>
      </div>
      <FormField id="bx-reason" label={t("reason")} required>
        <Select id="bx-reason" value={reason} onChange={(e) => setReason(e.target.value as S["BanExemptionReason"])} data-testid="bx-reason">
          <option value="">{tc("select")}</option>
          {EXEMPTION_REASONS.map((x) => (
            <option key={x} value={x}>
              {te(`banExemptionReason.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="bx-en" label={t("controlsEn")} hint={tcm("reasonMin", { min: 30, n: en.trim().length })}>
        <Textarea value={en} onChange={(e) => setEn(e.target.value)} maxLength={1000} data-testid="bx-en" />
      </FormField>
      <FormField id="bx-ar" label={t("controlsAr")} hint={t("oneLanguage")}>
        <Textarea dir="rtl" value={ar} onChange={(e) => setAr(e.target.value)} maxLength={1000} />
      </FormField>
      <PossibleIdHint text={`${en} ${ar}`} />
    </StepDialog>
  );
}
