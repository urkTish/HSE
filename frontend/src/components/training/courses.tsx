"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { Tick } from "@/components/cert/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useProjects } from "@/lib/api/queries";
import { tk, useTrainingCourse, useTrainingCourses, useTrainingRefresh } from "@/lib/api/training";
import { useCurrentProject } from "@/lib/current-project";
import { ACB_CODES, COURSE_CATEGORIES, DELIVERY_MODES, INDUCTION_TYPES, WORKER_LANGUAGES } from "@/lib/train-enums";
import { useSearchState } from "@/lib/url-state";
import { CourseLabel, TrainingCatalogueSubNav, useCourseCatalogue, useTrainingCaps } from "./common";

type S = Schemas;

/* ───────────── list ───────────── */

export function CourseListPage() {
  const t = useTranslations("training.courses");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { project } = useCurrentProject();
  const caps = useTrainingCaps(project?.id);
  const s = useSearchState();
  const category = s.getAll("category") as S["CourseCategory"][];
  const active = s.get("active");
  const hook = s.get("hook");
  const [create, setCreate] = useState(false);
  const q = useTrainingCourses({
    q: s.get("q") || null,
    category: category.length ? category : null,
    active: active === "1" ? true : active === "0" ? false : null,
    hook_code: hook === "1" ? true : null,
    project_id: project?.id ?? null,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.courseEdit ? (
            <Button onClick={() => setCreate(true)} data-testid="new-course">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <TrainingCatalogueSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="training_courses" /> : null}>
        <SearchFilter id="course-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="course-cat" label={t("category")} options={COURSE_CATEGORIES.map((x) => ({ value: x, label: te(`courseCategory.${x}`) }))} value={category} onChange={(v) => s.set({ category: v })} />
        <SelectFilter
          id="course-active"
          label={t("active")}
          value={active ?? ""}
          onChange={(v) => s.set({ active: v })}
          options={[
            { value: "1", label: tc("yes") },
            { value: "0", label: tc("no") },
          ]}
        />
        <SelectFilter id="course-hook" label={t("hookCode")} value={hook ?? ""} onChange={(v) => s.set({ hook: v })} options={[{ value: "1", label: tc("yes") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="courses-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("name")}</TH>
              <TH>{t("category")}</TH>
              <TH>{t("validity")}</TH>
              <TH>{t("minHours")}</TH>
              <TH>{t("flags")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((c) => (
              <TR key={c.code} data-testid="course-row" data-code={c.code}>
                <TD label={t("code")}>
                  <Link href={`/training-courses/${encodeURIComponent(c.code)}`} className="font-medium text-primary hover:underline">
                    <Code>{c.code}</Code>
                  </Link>
                </TD>
                <TD label={t("name")}>{locale === "ar" ? c.name_ar : c.name_en}</TD>
                <TD label={t("category")}>
                  <span className="text-sm">{te(`courseCategory.${c.category}`)}</span>
                </TD>
                <TD label={t("validity")}>
                  <ValidityMonths c={c} />
                </TD>
                <TD label={t("minHours")}>{c.min_duration_hours ? <span className="ltr tabular-nums">{c.min_duration_hours}</span> : "—"}</TD>
                <TD label={t("flags")}>
                  <span className="flex flex-wrap gap-1">
                    {c.hook_code ? (
                      <Badge tone="info" data-testid="hook-code">
                        <Lock aria-hidden />
                        {t("hookCode")}
                      </Badge>
                    ) : null}
                    {c.critical_on_project ? <Badge tone="danger">{t("critical")}</Badge> : null}
                    {c.renews_only ? <Badge tone="neutral">{t("renewsOnly")}</Badge> : null}
                    {!c.active ? <Badge tone="neutral">{t("inactive")}</Badge> : null}
                  </span>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState />
      )}
      {create ? <CourseDialog onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

function ValidityMonths({ c }: { c: S["CourseRead"] }) {
  const t = useTranslations("training.courses");
  if (c.category === "induction_link") return <span className="text-xs text-muted-foreground">{t("phase2Validity")}</span>;
  if (c.validity_months === null) return <span className="text-sm">{t("noExpiry")}</span>;
  const eff = c.effective_validity_months;
  return (
    <span className="text-sm" data-testid="course-validity" data-months={c.validity_months} data-effective={eff ?? ""}>
      {t("months", { n: c.validity_months })}
      {eff !== undefined && eff !== null && eff !== c.validity_months ? <span className="block text-xs text-warning">{t("projectMonths", { n: eff })}</span> : null}
    </span>
  );
}

/* ───────────── create / edit (tighten only on edit, CC-2) ───────────── */

function CourseDialog({ course, onClose }: { course?: S["CourseRead"]; onClose: () => void }) {
  const t = useTranslations("training.courses");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const refresh = useTrainingRefresh();
  const projects = useProjects({ page_size: 100 });
  const { courses } = useCourseCatalogue();
  const others = courses.filter((c) => c.code !== course?.code);
  const [code, setCode] = useState(course?.code ?? "");
  const [nameEn, setNameEn] = useState(course?.name_en ?? "");
  const [nameAr, setNameAr] = useState(course?.name_ar ?? "");
  const [category, setCategory] = useState<S["CourseCategory"]>(course?.category ?? "awareness");
  const [indType, setIndType] = useState<S["InductionType"]>(course?.induction_link?.induction_type ?? "general_site");
  const [indCodes, setIndCodes] = useState<{ project: string; code: string }[]>(Object.entries(course?.induction_link?.project_course_codes ?? {}).map(([project, code]) => ({ project, code })));
  const [validity, setValidity] = useState(course ? (course.validity_months === null ? "" : String(course.validity_months)) : "24");
  const [minHours, setMinHours] = useState(course?.min_duration_hours ?? "");
  const [maxClass, setMaxClass] = useState(course?.max_class_size ? String(course.max_class_size) : "12");
  const [modes, setModes] = useState<S["DeliveryMode"][]>(course?.delivery_modes ?? ["classroom"]);
  const [theory, setTheory] = useState(course?.theory_required ?? true);
  const [passMark, setPassMark] = useState(course?.pass_mark_pct ? String(course.pass_mark_pct) : "80");
  const [practical, setPractical] = useState(course?.practical_required ?? false);
  const [prereq, setPrereq] = useState<string[]>(course?.prerequisite_codes ?? []);
  const [satisfies, setSatisfies] = useState<string[]>(course?.satisfies ?? []);
  const [renewal, setRenewal] = useState(course?.renewal_course_code ?? "");
  const [renewsOnly, setRenewsOnly] = useState(course?.renews_only ?? false);
  const [internal, setInternal] = useState(course?.provider_rule?.internal_allowed ?? true);
  const [contractor, setContractor] = useState(course?.provider_rule?.contractor_delivery_allowed ?? false);
  const [bodies, setBodies] = useState<S["AccreditationBodyCode"][]>(course?.provider_rule?.accreditation_bodies_required ?? []);
  const [langs, setLangs] = useState<S["WorkerLanguage"][]>(course?.languages_offered ?? ["ar", "en"]);
  const [active, setActive] = useState(course?.active ?? true);
  const [reason, setReason] = useState("");
  const induction = category === "induction_link";
  const professional = category === "professional_qualification";
  const valid =
    /^[A-Z0-9-]{2,20}$/.test(code.trim().toUpperCase()) &&
    nameEn.trim() &&
    nameAr.trim() &&
    (induction || (minHours && maxClass && modes.length && langs.length && (validity || professional))) &&
    (!theory || induction || passMark);
  async function save() {
    const body = {
      name_en: nameEn.trim(),
      name_ar: nameAr.trim(),
      category,
      induction_link: induction ? { induction_type: indType, project_course_codes: Object.fromEntries(indCodes.filter((x) => x.project && x.code.trim()).map((x) => [x.project, x.code.trim()])) } : null,
      validity_months: induction || !validity ? null : Number(validity),
      min_duration_hours: induction ? null : minHours || null,
      max_class_size: induction ? null : Number(maxClass) || null,
      delivery_modes: induction ? [] : modes,
      theory_required: induction ? false : theory,
      pass_mark_pct: !induction && theory ? Number(passMark) : null,
      practical_required: induction ? false : practical,
      prerequisite_codes: prereq,
      satisfies,
      renewal_course_code: renewal || null,
      renews_only: renewsOnly,
      provider_rule: induction ? null : { internal_allowed: internal, contractor_delivery_allowed: contractor, accreditation_bodies_required: bodies },
      languages_offered: langs,
      active,
    };
    if (course) {
      const r = await unwrap(api.PATCH("/api/v1/training-courses/{code}", { params: { path: { code: course.code } }, body: { ...body, reason: reason.trim() || null } }));
      qc.setQueryData(tk.course(course.code, ""), r);
      await refresh();
      toast.success(r.records_recomputed ? t("recomputed", { n: r.records_recomputed }) : tc("saved"));
      return;
    }
    const r = await unwrap(api.POST("/api/v1/training-courses", { body: { ...body, code: code.trim().toUpperCase() } }));
    await refresh();
    toast.success(t("created", { code: r.code }));
    router.push(`/training-courses/${encodeURIComponent(r.code)}`);
  }
  const opts = others.map((c) => ({ value: c.code, label: `${c.code} — ${c.name_en}` }));
  return (
    <StepDialog title={course ? t("edit") : t("new")} description={course ? t("tightenHint") : t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-course">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="course-code" label={t("code")} required hint={t("codeHint")}>
          <Input value={code} disabled={Boolean(course)} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={20} className="ltr uppercase" data-testid="course-code" />
        </FormField>
        <FormField id="course-category" label={t("category")} required>
          <Select value={category} onChange={(e) => setCategory(e.target.value as S["CourseCategory"])} data-testid="course-category">
            {COURSE_CATEGORIES.map((x) => (
              <option key={x} value={x}>
                {te(`courseCategory.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="course-name-en" label={t("nameEn")} required>
          <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} dir="ltr" maxLength={150} data-testid="course-name-en" />
        </FormField>
        <FormField id="course-name-ar" label={t("nameAr")} required>
          <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" maxLength={150} data-testid="course-name-ar" />
        </FormField>
      </div>
      {induction ? (
        <div className="flex flex-col gap-2 rounded-md border p-3" data-testid="induction-link">
          <p className="text-sm text-muted-foreground">{t("inductionHint")}</p>
          <FormField id="course-ind-type" label={t("inductionType")} required>
            <Select value={indType} onChange={(e) => setIndType(e.target.value as S["InductionType"])}>
              {INDUCTION_TYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`inductionType.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          {indType === "zone_specific" ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium">{t("projectCourseCodes")}</legend>
              {indCodes.map((x, i) => (
                <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                  <Select aria-label={t("project")} value={x.project} onChange={(e) => setIndCodes(indCodes.map((y, j) => (j === i ? { ...y, project: e.target.value } : y)))}>
                    <option value="">{tc("select")}</option>
                    {(projects.data?.items ?? []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.code}
                      </option>
                    ))}
                  </Select>
                  <Input aria-label={t("phase2Code")} placeholder={t("phase2Code")} className="ltr" value={x.code} onChange={(e) => setIndCodes(indCodes.map((y, j) => (j === i ? { ...y, code: e.target.value } : y)))} />
                  <Button variant="ghost" onClick={() => setIndCodes(indCodes.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                    <span className="sr-only">{tc("remove")}</span>
                  </Button>
                </div>
              ))}
              <Button variant="outline" size="sm" className="self-start" onClick={() => setIndCodes([...indCodes, { project: "", code: "" }])}>
                <Plus aria-hidden />
                {t("addMapping")}
              </Button>
            </fieldset>
          ) : null}
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField id="course-validity" label={t("validityMonths")} required={!professional} hint={professional ? t("validityProfessional") : t("validityHint")}>
              <Input type="number" min={1} max={60} value={validity} onChange={(e) => setValidity(e.target.value)} className="ltr" data-testid="course-validity-months" />
            </FormField>
            <FormField id="course-min" label={t("minHours")} required hint={t("minHoursHint")}>
              <Input type="number" step="0.25" min={0.5} max={400} value={minHours} onChange={(e) => setMinHours(e.target.value)} className="ltr" data-testid="course-min-hours" />
            </FormField>
            <FormField id="course-max" label={t("maxClass")} required>
              <Input type="number" min={1} max={60} value={maxClass} onChange={(e) => setMaxClass(e.target.value)} className="ltr" data-testid="course-max-class" />
            </FormField>
          </div>
          <CheckboxGroup id="course-modes" legend={t("deliveryModes")} required options={DELIVERY_MODES.map((x) => ({ value: x, label: te(`deliveryMode.${x}`) }))} value={modes} onChange={setModes} hint={t("modesHint")} />
          <div className="grid gap-3 sm:grid-cols-3">
            <Tick id="course-theory" label={t("theoryRequired")} checked={theory} onChange={setTheory} />
            {theory ? (
              <FormField id="course-pass" label={t("passMark")} required hint={t("passMarkHint")}>
                <Input type="number" min={50} max={100} value={passMark} onChange={(e) => setPassMark(e.target.value)} className="ltr" data-testid="course-pass-mark" />
              </FormField>
            ) : (
              <div />
            )}
            <Tick id="course-practical" label={t("practicalRequired")} checked={practical} onChange={setPractical} />
          </div>
          <fieldset className="flex flex-col gap-2 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">{t("providerRule")}</legend>
            <Tick id="course-internal" label={t("internalAllowed")} checked={internal} onChange={setInternal} />
            <Tick id="course-contractor" label={t("contractorAllowed")} checked={contractor} onChange={setContractor} />
            <MultiSelect id="course-bodies" label={t("bodiesRequired")} allLabel={t("noneRequired")} options={ACB_CODES.map((x) => ({ value: x, label: te(`acb.${x}`) }))} value={bodies} onChange={setBodies} testId="course-bodies" />
            <p className="text-xs text-muted-foreground">{t("bodiesHint")}</p>
          </fieldset>
        </>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <MultiSelect id="course-prereq" label={t("prerequisites")} allLabel={t("none")} options={opts} value={prereq} onChange={setPrereq} />
        <MultiSelect id="course-satisfies" label={t("satisfies")} allLabel={t("none")} options={opts} value={satisfies} onChange={setSatisfies} />
        <FormField id="course-renewal" label={t("renewalCourse")}>
          <Select value={renewal} onChange={(e) => setRenewal(e.target.value)}>
            <option value="">{t("none")}</option>
            {others
              .filter((c) => c.renews_only)
              .map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code} — {c.name_en}
                </option>
              ))}
          </Select>
        </FormField>
        <Tick id="course-renews-only" label={t("renewsOnlyLabel")} checked={renewsOnly} onChange={setRenewsOnly} />
      </div>
      <CheckboxGroup id="course-langs" legend={t("languages")} required options={WORKER_LANGUAGES.map((x) => ({ value: x, label: te(`workerLanguage.${x}`) }))} value={langs} onChange={setLangs} />
      <Tick id="course-active" label={t("activeLabel")} checked={active} onChange={setActive} />
      {course ? (
        <FormField id="course-reason" label={t("changeReason")} hint={t("reasonHint")}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="course-reason" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}

/* ───────────── detail ───────────── */

export function CourseDetail({ code }: { code: string }) {
  const { project } = useCurrentProject();
  const q = useTrainingCourse(code, project?.id ?? "");
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <CourseView c={q.data} projectCode={project?.code ?? null} />;
}

function CourseView({ c, projectCode }: { c: S["CourseRead"]; projectCode: string | null }) {
  const t = useTranslations("training.courses");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const refresh = useTrainingRefresh();
  const caps = useTrainingCaps();
  const [edit, setEdit] = useState(false);
  const [del, setDel] = useState(false);
  const induction = c.category === "induction_link";
  const codes = (xs: string[]) =>
    xs.length ? (
      <span className="flex flex-wrap gap-1">
        {xs.map((x) => (
          <Link key={x} href={`/training-courses/${encodeURIComponent(x)}`} className="text-primary hover:underline">
            <Code>{x}</Code>
          </Link>
        ))}
      </span>
    ) : (
      "—"
    );
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/training-courses" }, { label: c.code }]} />
        <PageHeader
          title={`${c.code} — ${locale === "ar" ? c.name_ar : c.name_en}`}
          description={te(`courseCategory.${c.category}`)}
          actions={
            <>
              {c.hook_code ? (
                <Badge tone="info">
                  <Lock aria-hidden />
                  {t("hookCode")}
                </Badge>
              ) : null}
              {!c.active ? <Badge tone="neutral">{t("inactive")}</Badge> : null}
              {caps.courseEdit ? (
                <Button variant="outline" onClick={() => setEdit(true)} data-testid="edit-course">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              {caps.courseEdit && !c.in_use ? (
                <Button variant="destructive-outline" onClick={() => setDel(true)} data-testid="delete-course">
                  <Trash2 aria-hidden />
                  {tc("delete")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {c.in_use && caps.courseEdit ? <Alert tone="info">{t("inUseHint")}</Alert> : null}
      {induction ? <Alert tone="info">{t("inductionOwned")}</Alert> : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("nameEn")}>{c.name_en}</FieldItem>
            <FieldItem label={t("nameAr")}>{c.name_ar}</FieldItem>
            {induction ? (
              <FieldItem label={t("inductionType")}>{c.induction_link ? te(`inductionType.${c.induction_link.induction_type}`) : "—"}</FieldItem>
            ) : (
              <>
                <FieldItem label={t("validityMonths")}>
                  <ValidityMonths c={c} />
                  {projectCode && c.effective_validity_months !== undefined ? <span className="block text-xs text-muted-foreground">{t("onProject", { code: projectCode })}</span> : null}
                </FieldItem>
                <FieldItem label={t("minHours")} ltr>
                  {c.min_duration_hours ?? "—"}
                </FieldItem>
                <FieldItem label={t("maxClass")} ltr>
                  {c.max_class_size ?? "—"}
                </FieldItem>
                <FieldItem label={t("deliveryModes")}>{c.delivery_modes.map((m) => te(`deliveryMode.${m}`)).join(" · ") || "—"}</FieldItem>
                <FieldItem label={t("theoryRequired")}>
                  <YesNo value={c.theory_required} yes={tc("yes")} no={tc("no")} />
                  {c.theory_required && c.pass_mark_pct ? (
                    <span className="ms-2" data-testid="pass-mark">
                      {t("passMarkValue", { pct: c.pass_mark_pct })}
                      {c.effective_pass_mark_pct && c.effective_pass_mark_pct !== c.pass_mark_pct ? <span className="ms-1 text-warning">{t("effectivePassMark", { pct: c.effective_pass_mark_pct })}</span> : null}
                    </span>
                  ) : null}
                </FieldItem>
                <FieldItem label={t("practicalRequired")}>
                  <YesNo value={c.practical_required} yes={tc("yes")} no={tc("no")} />
                </FieldItem>
                <FieldItem label={t("providerRule")} wide>
                  {c.provider_rule ? (
                    <span className="flex flex-wrap gap-1 text-sm" data-testid="provider-rule">
                      <Badge tone={c.provider_rule.internal_allowed ? "success" : "neutral"}>{c.provider_rule.internal_allowed ? t("internalYes") : t("internalNo")}</Badge>
                      <Badge tone={c.provider_rule.contractor_delivery_allowed ? "success" : "neutral"}>{c.provider_rule.contractor_delivery_allowed ? t("contractorYes") : t("contractorNo")}</Badge>
                      {c.provider_rule.accreditation_bodies_required.length ? <Badge tone="warning">{t("accreditedBy", { bodies: c.provider_rule.accreditation_bodies_required.map((b) => te(`acb.${b}`)).join(", ") })}</Badge> : null}
                    </span>
                  ) : (
                    "—"
                  )}
                </FieldItem>
              </>
            )}
            <FieldItem label={t("prerequisites")}>{codes(c.prerequisite_codes)}</FieldItem>
            <FieldItem label={t("satisfies")}>{codes(c.satisfies)}</FieldItem>
            <FieldItem label={t("satisfiedBy")}>{codes(c.satisfied_by)}</FieldItem>
            <FieldItem label={t("renewalCourse")}>{c.renewal_course_code ? codes([c.renewal_course_code]) : "—"}</FieldItem>
            <FieldItem label={t("renewsOnlyLabel")}>
              <YesNo value={c.renews_only} yes={tc("yes")} no={tc("no")} />
            </FieldItem>
            <FieldItem label={t("languages")}>{c.languages_offered.map((l) => te(`workerLanguage.${l}`)).join(" · ") || "—"}</FieldItem>
            <FieldItem label={t("hookCode")}>
              <YesNo value={c.hook_code} yes={tc("yes")} no={tc("no")} />
              {c.critical_on_project ? <Badge tone="danger" className="ms-2">{t("critical")}</Badge> : null}
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("satisfactionTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {c.satisfied_by.length ? (
            <p>
              {t("satisfactionHint", { code: c.code })} <CourseLabel code={c.satisfied_by.join(", ")} />
            </p>
          ) : (
            <p>{t("satisfactionNone", { code: c.code })}</p>
          )}
        </CardContent>
      </Card>
      <HistoryPanel entityType="training_course" entityId={c.id} />
      {edit ? <CourseDialog course={c} onClose={() => setEdit(false)} /> : null}
      {del ? (
        <StepDialog
          title={t("deleteTitle")}
          description={t("deleteHint")}
          confirmLabel={tc("delete")}
          destructive
          onClose={() => setDel(false)}
          onConfirm={async () => {
            await unwrap(api.DELETE("/api/v1/training-courses/{code}", { params: { path: { code: c.code } } }));
            await refresh();
            router.push("/training-courses");
          }}
          testId="delete-course-confirm"
        />
      ) : null}
    </div>
  );
}
