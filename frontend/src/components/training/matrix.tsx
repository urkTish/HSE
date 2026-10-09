"use client";
import { History, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, StepDialog } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { StackedDate } from "@/components/medical/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useMatrixLineVersions, useTrainingMatrix, useTrainingRefresh } from "@/lib/api/training";
import { TRADES } from "@/lib/access-enums";
import { MANUAL_APPLIES_TO, MATRIX_APPLIES_TO, MATRIX_LEVELS, MATRIX_ROLES } from "@/lib/train-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { DateFilter, RequirementText, TrainingMatrixSubNav, useCourseCatalogue, useTrainingCaps } from "./common";

type S = Schemas;
const ANY_OF_CATEGORIES: S["CourseCategory"][] = ["professional_qualification", "awareness"];

/* ───────────── matrix ───────────── */

export function MatrixPage() {
  return <ProjectGate>{(p) => <Matrix project={p} />}</ProjectGate>;
}

function Matrix({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.matrix");
  const te = useTranslations("enums");
  const caps = useTrainingCaps(project.id);
  const { courses, label: courseName } = useCourseCatalogue(project.id);
  const s = useSearchState();
  const kinds = s.getAll("kind") as S["MatrixAppliesTo"][];
  const q = useTrainingMatrix(project.id, {
    as_of: s.get("as_of") || null,
    applies_to_kind: kinds.length ? kinds : null,
    level: (s.get("level") as S["MatrixLevel"]) || null,
    source: (s.get("source") as S["MatrixLineSource"]) || null,
    course_code: s.get("course") || null,
    include_counts: true,
  });
  const [line, setLine] = useState<S["MatrixLineRead"] | "new" | null>(null);
  const [remove, setRemove] = useState<S["MatrixLineRead"] | null>(null);
  const [versions, setVersions] = useState<S["MatrixLineRead"] | null>(null);
  const lines = q.data?.lines ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.matrixEdit ? (
            <Button onClick={() => setLine("new")} data-testid="new-matrix-line">
              <Plus aria-hidden />
              {t("newLine")}
            </Button>
          ) : null
        }
      />
      <TrainingMatrixSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="training_matrix" params={{ project_id: project.id }} /> : null}>
        <DateFilter id="mx-asof" label={t("asOf")} value={s.get("as_of") ?? ""} onChange={(v) => s.set({ as_of: v })} />
        <MultiSelect id="mx-kind" label={t("appliesTo")} options={MATRIX_APPLIES_TO.map((x) => ({ value: x, label: te(`matrixAppliesTo.${x}`) }))} value={kinds} onChange={(v) => s.set({ kind: v })} />
        <SelectFilter id="mx-level" label={t("level")} value={s.get("level") ?? ""} onChange={(v) => s.set({ level: v })} options={MATRIX_LEVELS.map((x) => ({ value: x, label: te(`matrixLevel.${x}`) }))} />
        <SelectFilter
          id="mx-source"
          label={t("source")}
          value={s.get("source") ?? ""}
          onChange={(v) => s.set({ source: v })}
          options={(["manual", "hook"] as const).map((x) => ({ value: x, label: te(`matrixSource.${x}`) }))}
        />
        <SelectFilter id="mx-course" label={t("course")} value={s.get("course") ?? ""} onChange={(v) => s.set({ course: v })} options={courses.map((c) => ({ value: c.code, label: c.code }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : lines.length ? (
        <Table data-testid="matrix-table">
          <THead>
            <TR>
              <TH>{t("lineNo")}</TH>
              <TH>{t("appliesTo")}</TH>
              <TH>{t("requirement")}</TH>
              <TH>{t("level")}</TH>
              <TH>{t("dueDays")}</TH>
              <TH>{t("source")}</TH>
              <TH>{t("population")}</TH>
              <TH>
                <span className="sr-only">{t("actions")}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {lines.map((l) => (
              <TR key={l.id} data-testid="matrix-line" data-line={l.line_no} data-source={l.source} data-counted={l.kpi_counted ? "yes" : "no"}>
                <TD label={t("lineNo")}>
                  <Code className="font-medium">{l.line_no}</Code>
                  <span className="mt-0.5 flex gap-1 text-xs text-muted-foreground">
                    <span>{t("fromLabel")}</span>
                    <StackedDate v={l.effective_from} projectId={project.id} />
                  </span>
                </TD>
                <TD label={t("appliesTo")}>
                  <span className="text-sm font-medium">{te(`matrixAppliesTo.${l.applies_to_kind}`)}</span>
                  {l.applies_to_labels.length ? <span className="block text-xs text-muted-foreground">{l.applies_to_labels.join(" · ")}</span> : null}
                </TD>
                <TD label={t("requirement")}>
                  <RequirementText r={l.requirement} />
                  {l.requirement.course_code ? <span className="block max-w-56 text-xs text-muted-foreground">{courseName(l.requirement.course_code)}</span> : null}
                </TD>
                <TD label={t("level")}>
                  <StatusBadge status={l.level} label={te(`matrixLevel.${l.level}`)} />
                </TD>
                <TD label={t("dueDays")}>
                  <span className="ltr tabular-nums">{l.due_within_days}</span>
                </TD>
                <TD label={t("source")}>
                  {l.source === "hook" ? (
                    <Badge tone="info" data-testid="line-hook">
                      <Lock aria-hidden />
                      {te("matrixSource.hook")}
                    </Badge>
                  ) : (
                    <span className="text-sm">{te("matrixSource.manual")}</span>
                  )}
                  {!l.kpi_counted ? <span className="block text-xs text-muted-foreground">{t("enforcementOnly")}</span> : null}
                  {l.hook_attach_point ? <span className="block text-xs text-muted-foreground ltr">{l.hook_attach_point}</span> : null}
                </TD>
                <TD label={t("population")}>
                  {l.applicable_deployments !== undefined && l.applicable_deployments !== null ? (
                    <Link href={`/training-gaps?course_code=${encodeURIComponent(l.requirement.course_code ?? "")}`} className="ltr tabular-nums text-primary hover:underline">
                      {l.applicable_deployments}
                    </Link>
                  ) : (
                    "—"
                  )}
                </TD>
                <TD label={t("actions")}>
                  <span className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setVersions(l)} data-testid="line-versions">
                      <History aria-hidden />
                      <span className="sr-only">{t("versions")}</span>
                    </Button>
                    {caps.matrixEdit && l.source === "manual" && !l.effective_to ? (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => setLine(l)} data-testid="edit-line">
                          <Pencil aria-hidden />
                          <span className="sr-only">{t("editLine")}</span>
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setRemove(l)} data-testid="remove-line">
                          <Trash2 aria-hidden />
                          <span className="sr-only">{t("removeLine")}</span>
                        </Button>
                      </>
                    ) : null}
                  </span>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {line ? <LineDialog project={project} line={line === "new" ? undefined : line} onClose={() => setLine(null)} /> : null}
      {remove ? <RemoveDialog line={remove} onClose={() => setRemove(null)} /> : null}
      {versions ? <VersionsDialog line={versions} projectId={project.id} onClose={() => setVersions(null)} /> : null}
    </div>
  );
}

function LineDialog({ project, line, onClose }: { project: S["ProjectRead"]; line?: S["MatrixLineRead"]; onClose: () => void }) {
  const t = useTranslations("training.matrix");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useTrainingCaps(project.id);
  const refresh = useTrainingRefresh();
  const opts = useProjectOptions(project.id);
  const { courses } = useCourseCatalogue(project.id, { active: true });
  const [kind, setKind] = useState<S["MatrixAppliesTo"]>(line?.applies_to_kind ?? "trade");
  const [values, setValues] = useState<string[]>(line?.applies_to_values ?? []);
  const [mode, setMode] = useState<"one" | "any">(line?.requirement.any_of?.length ? "any" : "one");
  const [code, setCode] = useState(line?.requirement.course_code ?? "");
  const [anyOf, setAnyOf] = useState<string[]>(line?.requirement.any_of ?? []);
  const [level, setLevel] = useState<S["MatrixLevel"]>(line?.level ?? "mandatory");
  const [due, setDue] = useState(String(line?.due_within_days ?? 0));
  const [reason, setReason] = useState("");
  const loosening = Boolean(line) && line?.level === "mandatory" && (level === "recommended" || Number(due) > (line?.due_within_days ?? 0));
  const valueOptions =
    kind === "trade"
      ? TRADES.map((x) => ({ value: x, label: te(`trade.${x}`) }))
      : kind === "matrix_role"
        ? MATRIX_ROLES.map((x) => ({ value: x, label: te(`matrixRole.${x}`) }))
        : kind === "zone"
          ? opts.zones.map((z) => ({ value: z.value, label: z.label }))
          : [];
  const reqOk = mode === "one" ? Boolean(code) : anyOf.length >= 2 && anyOf.length <= 6;
  const valid = (kind === "all_workers" || values.length > 0) && reqOk && due !== "" && Number(due) >= 0 && (!loosening || reason.trim().length >= 20);
  async function save() {
    const requirement = mode === "one" ? { course_code: code, any_of: null } : { course_code: null, any_of: anyOf };
    if (line) {
      await unwrap(api.PATCH("/api/v1/training-matrix-lines/{line_id}", { params: { path: { line_id: line.id } }, body: { applies_to_values: values, requirement, level, due_within_days: Number(due), reason: reason.trim() || null } }));
    } else {
      await unwrap(api.POST("/api/v1/projects/{project_id}/training-matrix/lines", { params: { path: { project_id: project.id } }, body: { applies_to_kind: kind, applies_to_values: kind === "all_workers" ? [] : values, requirement, level, due_within_days: Number(due) } }));
    }
    await refresh();
    toast.success(tc("saved"));
  }
  return (
    <StepDialog title={line ? t("editLine") : t("newLine")} description={t("lineHint")} warning={loosening && !caps.manager ? t("looseningManagerOnly") : undefined} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-line">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="mx-kind-in" label={t("appliesTo")} required>
          <Select
            value={kind}
            disabled={Boolean(line)}
            onChange={(e) => {
              setKind(e.target.value as S["MatrixAppliesTo"]);
              setValues([]);
            }}
            data-testid="mx-kind-in"
          >
            {MANUAL_APPLIES_TO.map((x) => (
              <option key={x} value={x}>
                {te(`matrixAppliesTo.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {kind !== "all_workers" ? <MultiSelect id="mx-values" label={t("values")} options={valueOptions} value={values} onChange={setValues} testId="mx-values" /> : <div />}
      </div>
      <fieldset className="flex flex-wrap gap-4 text-sm">
        <legend className="mb-1 text-sm font-medium">{t("requirement")}</legend>
        <label className="flex min-h-touch items-center gap-2">
          <input type="radio" checked={mode === "one"} onChange={() => setMode("one")} />
          {t("oneCourse")}
        </label>
        <label className="flex min-h-touch items-center gap-2">
          <input type="radio" checked={mode === "any"} onChange={() => setMode("any")} data-testid="mx-any-of" />
          {t("anyOfCourses")}
        </label>
      </fieldset>
      {mode === "one" ? (
        <FormField id="mx-course-in" label={t("course")} required>
          <Select value={code} onChange={(e) => setCode(e.target.value)} data-testid="mx-course-in">
            <option value="">{tc("select")}</option>
            {courses.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code} — {c.name_en}
                {c.hook_code ? " ★" : ""}
              </option>
            ))}
          </Select>
        </FormField>
      ) : (
        <>
          <MultiSelect id="mx-anyof-in" label={t("anyOfCourses")} options={courses.map((c) => ({ value: c.code, label: `${c.code} — ${c.name_en}` }))} value={anyOf} onChange={setAnyOf} testId="mx-anyof-in" />
          <p className="text-xs text-muted-foreground">{t("anyOfHint", { cats: ANY_OF_CATEGORIES.map((c) => te(`courseCategory.${c}`)).join(", ") })}</p>
        </>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="mx-level-in" label={t("level")} required>
          <Select value={level} onChange={(e) => setLevel(e.target.value as S["MatrixLevel"])} data-testid="mx-level-in">
            {MATRIX_LEVELS.map((x) => (
              <option key={x} value={x}>
                {te(`matrixLevel.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="mx-due" label={t("dueDays")} required hint={t("dueDaysHint")}>
          <Input type="number" min={0} value={due} onChange={(e) => setDue(e.target.value)} className="ltr" data-testid="mx-due" />
        </FormField>
      </div>
      {line ? (
        <FormField id="mx-reason" label={tc("reason")} required={loosening} hint={t("reason20")}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="mx-reason" />
        </FormField>
      ) : null}
      <p className="text-xs text-muted-foreground">{t("noBackdating")}</p>
    </StepDialog>
  );
}

function RemoveDialog({ line, onClose }: { line: S["MatrixLineRead"]; onClose: () => void }) {
  const t = useTranslations("training.matrix");
  const tc = useTranslations("common");
  const caps = useTrainingCaps(line.project_id);
  const refresh = useTrainingRefresh();
  const [reason, setReason] = useState("");
  const mandatory = line.level === "mandatory";
  return (
    <StepDialog
      title={t("removeTitle", { no: line.line_no })}
      description={t("removeHint")}
      warning={mandatory && !caps.manager ? t("looseningManagerOnly") : undefined}
      confirmLabel={t("removeLine")}
      destructive
      disabled={mandatory && reason.trim().length < 20}
      onClose={onClose}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/training-matrix-lines/{line_id}/remove", { params: { path: { line_id: line.id } }, body: { reason: reason.trim() || null } }));
        await refresh();
      }}
      testId="remove-line-confirm"
    >
      <FormField id="mx-rm-reason" label={tc("reason")} required={mandatory} hint={t("reason20")}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="mx-rm-reason" />
      </FormField>
    </StepDialog>
  );
}

function VersionsDialog({ line, projectId, onClose }: { line: S["MatrixLineRead"]; projectId: string; onClose: () => void }) {
  const t = useTranslations("training.matrix");
  const te = useTranslations("enums");
  const { date } = useFormatters(projectId);
  const q = useMatrixLineVersions(line.id);
  return (
    <StepDialog title={t("versionsTitle", { no: line.line_no })} confirmLabel={t("close")} onConfirm={async () => undefined} onClose={onClose} wide testId="versions-close">
      {q.isLoading ? (
        <LoadingState rows={2} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <ul className="flex flex-col divide-y text-sm" data-testid="line-versions-list">
          {(q.data?.versions ?? []).map((v) => (
            <li key={v.version_id} className="flex flex-col gap-0.5 py-2">
              <span className="font-medium">
                <span className="ltr">{date(v.effective_from)}</span> – <span className="ltr">{v.effective_to ? date(v.effective_to) : t("current")}</span>
              </span>
              <span>
                {te(`matrixAppliesTo.${v.applies_to_kind}`)}
                {v.applies_to_labels.length ? `: ${v.applies_to_labels.join(", ")}` : ""} · <RequirementText r={v.requirement} /> · {te(`matrixLevel.${v.level}`)} · {t("dueDaysShort", { n: v.due_within_days })}
              </span>
              {v.reason ? <span className="text-xs text-muted-foreground">{v.reason}</span> : null}
              {v.created_by ? (
                <span className="text-xs text-muted-foreground">
                  <UserName u={v.created_by} />
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {line.source === "hook" ? <Alert tone="info">{t("derivedHint")}</Alert> : null}
    </StepDialog>
  );
}
