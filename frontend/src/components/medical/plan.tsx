"use client";
import { History, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { ExportButtons } from "@/components/common/export-buttons";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, StepDialog, WorkerLabel } from "@/components/access/common";
import { Tick } from "@/components/cert/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useEngagements, useZones } from "@/lib/api/queries";
import { useFitnessGaps, useMedicalLineVersions, useMedicalPlan, useMedicalRefresh } from "@/lib/api/medical";
import { ADP_CATEGORIES } from "@/lib/train-enums";
import { EXPOSURE_GROUPS, MED_APPLIES_TO_MANUAL } from "@/lib/med-enums";
import { TRADES } from "@/lib/access-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { DateFilter } from "@/components/training/common";
import { FitnessCodeLabel, FitnessCodeSelect, MedicalPlanSubNav, TierNote, useFitnessCatalogue, useMedCaps, workerHealthHref } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/** Applies-to values in words (trades, exposure groups, ADP categories, zones). */
function useValueLabel(projectId: string) {
  const te = useTranslations("enums");
  const zones = useZones(projectId, { page_size: 200 });
  return (kind: S["MedicalAppliesTo"], v: string) => {
    if (kind === "trade") return te.has(`trade.${v}` as never) ? te(`trade.${v}` as never) : v;
    if (kind === "exposure_group") return te.has(`exposureGroup.${v}` as never) ? te(`exposureGroup.${v}` as never) : v;
    if (kind === "adp_category") return te.has(`adpCategory.${v}` as never) ? te(`adpCategory.${v}` as never) : v;
    if (kind === "crew_role") return te.has(`ptwCrewRole.${v}` as never) ? te(`ptwCrewRole.${v}` as never) : v;
    if (kind === "zone") return zones.data?.items.find((z) => z.id === v)?.code ?? v;
    return v;
  };
}

/* ═════════════ requirement plan (§3.4, MR-1…MR-6) ═════════════ */

export function MedicalPlanPage() {
  return <ProjectGate>{(p) => <Plan project={p} />}</ProjectGate>;
}

function Plan({ project }: { project: Project }) {
  const t = useTranslations("medical.plan");
  const te = useTranslations("enums");
  const caps = useMedCaps(project.id);
  const { date } = useFormatters(project.id);
  const { label } = useFitnessCatalogue(project.id);
  const s = useSearchState();
  const asOf = s.get("as_of") ?? "";
  const q = useMedicalPlan(project.id, { as_of: asOf || null, with_counts: true });
  const value = useValueLabel(project.id);
  const [create, setCreate] = useState(false);
  const [edit, setEdit] = useState<S["MedicalPlanLineRead"] | null>(null);
  const [remove, setRemove] = useState<S["MedicalPlanLineRead"] | null>(null);
  const [versions, setVersions] = useState<S["MedicalPlanLineRead"] | null>(null);
  const plan = q.data;
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.planEdit ? (
            <Button onClick={() => setCreate(true)} data-testid="new-plan-line">
              <Plus aria-hidden />
              {t("newLine")}
            </Button>
          ) : null
        }
      />
      <MedicalPlanSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="medical_plan" params={{ project_id: project.id }} /> : null}>
        <DateFilter id="plan-as-of" label={t("asOf")} value={asOf} onChange={(v) => s.set({ as_of: v })} />
      </ListToolbar>
      <p className="mb-2 text-xs text-muted-foreground">{t("noExemptions")}</p>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : plan && plan.lines.length ? (
        <>
          <Table data-testid="medical-plan-table">
            <THead>
              <TR>
                <TH>{t("line")}</TH>
                <TH>{t("appliesTo")}</TH>
                <TH>{t("code")}</TH>
                <TH>{t("due")}</TH>
                <TH>{t("counted")}</TH>
                <TH>{t("met")}</TH>
                <TH>{t("gaps")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {plan.lines.map((l) => (
                <TR key={l.id} data-testid="plan-line" data-line={l.line_no} data-source={l.source}>
                  <TD label={t("line")}>
                    <Code className="font-medium">{l.line_no}</Code>
                    <span className="mt-1 flex flex-wrap gap-1">
                      <Badge tone={l.source === "manual" ? "neutral" : "info"}>
                        {l.read_only ? <Lock aria-hidden /> : null}
                        {te(`medLineSource.${l.source}`)}
                      </Badge>
                      {!l.kpi_counted ? <Badge tone="neutral">{t("notCounted")}</Badge> : null}
                    </span>
                    <span className="block text-xs text-muted-foreground">{t("from", { d: date(l.effective_from) })}</span>
                  </TD>
                  <TD label={t("appliesTo")}>
                    <span className="font-medium">{te(`medAppliesTo.${l.applies_to_kind}`)}</span>
                    {l.applies_to_values.length ? <span className="block text-xs">{l.applies_to_values.map((v) => value(l.applies_to_kind, v)).join(" · ")}</span> : null}
                    {l.trades.length ? <span className="block text-xs text-muted-foreground">{l.trades.map((v) => value("trade", v)).join(" · ")}</span> : null}
                  </TD>
                  <TD label={t("code")}>
                    <FitnessCodeLabel code={l.code} name={label(l.code)} />
                    {plan.hook_codes.includes(l.code) ? <Badge tone="info" className="ms-1">{t("hookCode")}</Badge> : null}
                  </TD>
                  <TD label={t("due")}>{t("days", { n: l.due_within_days })}</TD>
                  <TD label={t("counted")}>
                    <span className="ltr tabular-nums" data-testid="line-counted">{l.counted ?? "—"}</span>
                  </TD>
                  <TD label={t("met")}>
                    <span className="ltr tabular-nums" data-testid="line-met">{l.met ?? "—"}</span>
                  </TD>
                  <TD label={t("gaps")}>
                    {l.gaps ? (
                      <Link href={`/fitness-gaps?code=${encodeURIComponent(l.code)}`} className="ltr font-medium text-danger tabular-nums hover:underline" data-testid="line-gaps">
                        {l.gaps}
                      </Link>
                    ) : (
                      <span className="ltr tabular-nums" data-testid="line-gaps">{l.gaps ?? "—"}</span>
                    )}
                  </TD>
                  <TD>
                    <span className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setVersions(l)} aria-label={t("versions")}>
                        <History aria-hidden />
                      </Button>
                      {caps.planEdit && !l.read_only ? (
                        <>
                          <Button size="sm" variant="ghost" onClick={() => setEdit(l)} aria-label={t("edit")} data-testid="edit-plan-line">
                            <Pencil aria-hidden />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setRemove(l)} aria-label={t("remove")} data-testid="remove-plan-line">
                            <Trash2 aria-hidden />
                          </Button>
                        </>
                      ) : null}
                    </span>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <p className="mt-2 text-xs text-muted-foreground">{t("asOfNote", { d: date(plan.as_of) })}</p>
        </>
      ) : (
        <EmptyState />
      )}
      {create ? <PlanLineDialog project={project} onClose={() => setCreate(false)} /> : null}
      {edit ? <PlanLineDialog project={project} line={edit} onClose={() => setEdit(null)} /> : null}
      {remove ? <RemoveLineDialog line={remove} onClose={() => setRemove(null)} /> : null}
      {versions ? <VersionsDialog project={project} line={versions} onClose={() => setVersions(null)} /> : null}
    </div>
  );
}

function PlanLineDialog({ project, line, onClose }: { project: Project; line?: S["MedicalPlanLineRead"]; onClose: () => void }) {
  const t = useTranslations("medical.plan");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useMedicalRefresh();
  const zones = useZones(project.id, { page_size: 200 });
  const [kind, setKind] = useState<S["MedicalAppliesTo"]>(line?.applies_to_kind ?? "trade");
  const [values, setValues] = useState<string[]>(line?.applies_to_values ?? []);
  const [code, setCode] = useState(line?.code ?? "");
  const [due, setDue] = useState(String(line?.due_within_days ?? 0));
  const [reason, setReason] = useState("");
  const options: { value: string; label: string }[] =
    kind === "trade"
      ? TRADES.map((x) => ({ value: x, label: te(`trade.${x}`) }))
      : kind === "exposure_group"
        ? EXPOSURE_GROUPS.map((x) => ({ value: x, label: te(`exposureGroup.${x}`) }))
        : kind === "adp_category"
          ? ADP_CATEGORIES.map((x) => ({ value: x, label: te(`adpCategory.${x}`) }))
          : kind === "zone"
            ? (zones.data?.items ?? []).map((z) => ({ value: z.id, label: z.code }))
            : [];
  const needsValues = kind !== "all_workers";
  const valid = code && (!needsValues || values.length > 0) && /^\d+$/.test(due);
  return (
    <StepDialog
      title={line ? t("editTitle", { no: line.line_no }) : t("newLine")}
      description={t("lineHint")}
      confirmLabel={tc("save")}
      disabled={!valid}
      wide
      testId="save-plan-line"
      onConfirm={async () => {
        if (line) {
          await unwrap(
            api.PATCH("/api/v1/medical-plan-lines/{line_id}", { params: { path: { line_id: line.line_id } }, body: { applies_to_values: needsValues ? values : [], due_within_days: Number(due), reason: reason.trim() || null } }),
          );
        } else {
          await unwrap(
            api.POST("/api/v1/projects/{project_id}/medical-plan/lines", {
              params: { path: { project_id: project.id } },
              body: { applies_to_kind: kind, applies_to_values: needsValues ? values : [], code, due_within_days: Number(due) },
            }),
          );
        }
        toast.success(tc("saved"));
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="pl-kind" label={t("appliesTo")} required>
          <Select
            value={kind}
            disabled={Boolean(line)}
            onChange={(e) => {
              setKind(e.target.value as S["MedicalAppliesTo"]);
              setValues([]);
            }}
            data-testid="pl-kind"
          >
            {MED_APPLIES_TO_MANUAL.map((x) => (
              <option key={x} value={x}>
                {te(`medAppliesTo.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {line ? (
          <FormField id="pl-code" label={t("code")}>
            <Input value={line.code} disabled className="ltr" />
          </FormField>
        ) : (
          <FitnessCodeSelect id="pl-code" label={t("code")} value={code} onChange={setCode} projectId={project.id} required />
        )}
        <FormField id="pl-due" label={t("dueWithin")} required hint={t("dueHint")}>
          <Input value={due} onChange={(e) => setDue(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className="ltr" data-testid="pl-due" />
        </FormField>
      </div>
      {needsValues ? <CheckboxGroup id="pl-values" legend={t("values")} required columns={3} options={options} value={values} onChange={setValues} /> : null}
      {line ? (
        <FormField id="pl-reason" label={t("reason")} hint={t("loosenHint")}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="pl-reason" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}

function RemoveLineDialog({ line, onClose }: { line: S["MedicalPlanLineRead"]; onClose: () => void }) {
  const t = useTranslations("medical.plan");
  const refresh = useMedicalRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("removeTitle", { no: line.line_no })}
      description={t("removeHint")}
      confirmLabel={t("remove")}
      destructive
      disabled={reason.trim().length < 20}
      testId="remove-line-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/medical-plan-lines/{line_id}/remove", { params: { path: { line_id: line.line_id } }, body: { reason: reason.trim() } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="rl-reason" label={t("reason")} required hint={t("reason20", { n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="rl-reason" />
      </FormField>
    </StepDialog>
  );
}

function VersionsDialog({ project, line, onClose }: { project: Project; line: S["MedicalPlanLineRead"]; onClose: () => void }) {
  const t = useTranslations("medical.plan");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const { date } = useFormatters(project.id);
  const value = useValueLabel(project.id);
  const q = useMedicalLineVersions(line.line_id);
  return (
    <StepDialog title={t("versionsOf", { no: line.line_no })} confirmLabel={tc("close")} onConfirm={async () => undefined} onClose={onClose} wide>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <ul className="flex flex-col gap-2 text-sm" data-testid="plan-versions">
          {(q.data?.items ?? []).map((v) => (
            <li key={v.id} className="rounded-md border p-2">
              <span className="font-medium">
                {date(v.effective_from)} → {v.effective_to ? date(v.effective_to) : t("current")}
              </span>
              <span className="block">
                {te(`medAppliesTo.${v.applies_to_kind}`)}: {v.applies_to_values.map((x) => value(v.applies_to_kind, x)).join(" · ") || "—"} · {t("days", { n: v.due_within_days })}
              </span>
              {v.reason ? <span className="block text-xs text-muted-foreground">{v.reason}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </StepDialog>
  );
}

/* ═════════════ gap register (§8.4, tier-aware) ═════════════ */

export function FitnessGapsPage() {
  return <ProjectGate>{(p) => <Gaps project={p} />}</ProjectGate>;
}

const PAGE_SIZE = 50;

function Gaps({ project }: { project: Project }) {
  const t = useTranslations("medical.gaps");
  const te = useTranslations("enums");
  const caps = useMedCaps(project.id);
  const { date } = useFormatters(project.id);
  const { codes, label } = useFitnessCatalogue(project.id);
  const engagements = useEngagements(project.id, { page_size: 200 });
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const code = s.get("code") ?? "";
  const asOf = s.get("as_of") ?? "";
  const hookOnly = s.get("hook") === "1";
  const q = useFitnessGaps(project.id, { as_of: asOf || null, code: code ? [code] : null, engagement_id: s.get("engagement") || null, hook_codes_only: hookOnly, page, page_size: PAGE_SIZE });
  const items = q.data?.items ?? [];
  const tier = q.data?.tier;
  const tier2 = tier === "functional" || tier === "clinical_admin";
  const tier3 = tier === "clinical_admin";
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <MedicalPlanSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="fitness_gaps" params={{ project_id: project.id }} /> : null}>
        <SelectFilter id="gap-code" label={t("code")} value={code} onChange={(v) => s.set({ code: v })} options={codes.map((c) => ({ value: c.code, label: c.code }))} />
        <SelectFilter id="gap-eng" label={t("contractor")} value={s.get("engagement") ?? ""} onChange={(v) => s.set({ engagement: v })} options={(engagements.data?.items ?? []).map((e) => ({ value: e.id, label: e.contractor.short_code }))} />
        <DateFilter id="gap-as-of" label={t("asOf")} value={asOf} onChange={(v) => s.set({ as_of: v })} />
        <Tick id="gap-hook" label={t("hookOnly")} checked={hookOnly} onChange={(v) => s.set({ hook: v ? "1" : "" })} />
      </ListToolbar>
      <TierNote tier={tier} />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <p className="mb-2 text-sm" data-testid="gaps-total">
            {t("total", { n: q.data?.total ?? 0, d: date(q.data?.as_of ?? "") })}
          </p>
          <Table data-testid="fitness-gaps-table">
            <THead>
              <TR>
                <TH>{t("worker")}</TH>
                <TH>{t("contractor")}</TH>
                <TH>{t("trade")}</TH>
                <TH>{t("code")}</TH>
                <TH>{t("dueDate")}</TH>
                {tier2 ? <TH>{t("category")}</TH> : null}
                {tier3 ? <TH>{t("reason")}</TH> : null}
              </TR>
            </THead>
            <TBody>
              {items.map((g) => (
                <TR key={`${g.deployment_id}-${g.code}`} data-testid="gap-row" data-worker={g.worker.worker_no} data-code={g.code}>
                  <TD label={t("worker")}>
                    <Link href={workerHealthHref(g.worker.id, g.deployment_id)} className="text-primary hover:underline">
                      <WorkerLabel w={g.worker} />
                    </Link>
                  </TD>
                  <TD label={t("contractor")}>{g.engagement_short_code ? <Code>{g.engagement_short_code}</Code> : "—"}</TD>
                  <TD label={t("trade")}>{te(`trade.${g.trade}`)}</TD>
                  <TD label={t("code")}>
                    <FitnessCodeLabel code={g.code} name={label(g.code)} />
                    <span className="mt-1 flex flex-wrap gap-1">
                      {g.hook_code ? <Badge tone="info">{t("hookCode")}</Badge> : null}
                      {g.critical ? <Badge tone="danger">{t("critical")}</Badge> : null}
                    </span>
                  </TD>
                  <TD label={t("dueDate")}>{date(g.due_date)}</TD>
                  {tier2 ? (
                    <TD label={t("category")}>
                      <span data-testid="gap-category">{g.outcome_category ? (te.has(`gapCategory.${g.outcome_category}` as never) ? te(`gapCategory.${g.outcome_category}` as never) : g.outcome_category) : "—"}</span>
                    </TD>
                  ) : null}
                  {tier3 ? <TD label={t("reason")}>{g.reason_code ? te(`hookReason.${g.reason_code}`) : "—"}</TD> : null}
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("none")} />
      )}
    </div>
  );
}
