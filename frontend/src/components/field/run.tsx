"use client";
import { ArrowDown, CheckCircle2, ClipboardCheck, Hourglass, OctagonAlert, Plus, Send, Trash2, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { MutationError } from "@/components/common/states";
import { MultiSelect } from "@/components/common/multi-select";
import { Code } from "@/components/access/common";
import { Checkbox } from "@/components/ui/checkbox";
import { ChoiceMark } from "@/components/heat/common";
import { Link, useRouter } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useTemplates } from "@/lib/api/field";
import { useInspection, useInspectionPlan } from "@/lib/api/hse";
import { usePermits } from "@/lib/api/ptw";
import { SEVERITY_RANK } from "@/lib/field-enums";
import { cacheHoursOf, newUuid, submitWithOutbox, useFieldOffline } from "@/lib/field-offline";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { CriticalMark, FieldInspectSubNav, NoNamesHint, PhotoPicker, ResultBadge, Score, useBi, useFieldCaps, useFieldRef } from "./common";
import { OfflinePackCard, OfflineSubmitNote, OutboxPanel } from "./offline";
import { useOnline } from "@/lib/local-draft";
import { fromLocalInput, nowLocal } from "@/components/emergency/common";

type S = Schemas;
type Project = S["ProjectRead"];
type Item = S["TemplateItem-Output"];
type Template = S["TemplateRead"];

/* ═════════════ item answers (shared by inspections and audits, EXE-2, §6.1) ═════════════ */

export interface AnswerState {
  answer: string;
  numeric: string;
  count: string;
  note: string;
  photos: S["PhotoInput"][];
  equipment_ref: string;
  severity: string;
  fixed_on_spot: boolean;
  ca_required: boolean;
  finding: string;
}
export const emptyAnswer = (): AnswerState => ({ answer: "", numeric: "", count: "", note: "", photos: [], equipment_ref: "", severity: "", fixed_on_spot: false, ca_required: false, finding: "" });

/** True when the answer is non-compliant (yes_no, rating ≤ 1, numeric out of range, option mapped non_compliant). */
export function failing(it: Item, a: AnswerState | undefined): boolean {
  if (!a) return false;
  switch (it.item_type) {
    case "yes_no":
      return a.answer === "non_compliant";
    case "rating_0_3":
      return a.answer === "0" || a.answer === "1";
    case "numeric": {
      if (a.numeric.trim() === "" || !it.numeric_rule) return false;
      const v = Number(a.numeric);
      return Number.isFinite(v) && (v < Number(it.numeric_rule.min) || v > Number(it.numeric_rule.max));
    }
    case "single_select":
      return (it.options ?? []).some((o) => o.code === a.answer && o.maps_to === "non_compliant");
    default:
      return false;
  }
}

export function answered(it: Item, a: AnswerState | undefined): boolean {
  if (it.item_type === "numeric") return Boolean(a && (a.numeric.trim() !== "" || a.answer === "na"));
  if (it.item_type === "text" || it.item_type === "photo" || it.item_type === "count") return true;
  return Boolean(a?.answer);
}

/** The finding severity the server will compute (FND-1 / AUD-2), so the user can only raise it. */
export function baseSeverity(it: Item, a: AnswerState, audit: boolean): string {
  if (audit) {
    if (it.critical && (a.answer === "0" || a.answer === "1")) return "major_nc";
    if (a.answer === "0") return "major_nc";
    if (a.answer === "1") return "minor_nc";
    if (failing(it, a)) return "major_nc";
    return "observation";
  }
  return it.critical ? "critical" : (it.default_severity ?? "minor");
}

/** Complete enough to send (EXE-2): answered, note ≥ 10 chars when non-compliant, photo when required. */
export function answerReady(it: Item, a: AnswerState | undefined): boolean {
  if (!answered(it, a)) return false;
  if (!a) return true;
  const needsNote = failing(it, a);
  if (needsNote && a.note.trim().length < 10) return false;
  if (needsNote && (it.photo_required_on_fail || it.critical) && a.photos.length === 0) return false;
  return true;
}

export function toAnswerInput(it: Item, a: AnswerState | undefined, audit: boolean): S["AnswerInput"] | null {
  if (!a) return null;
  const fail = failing(it, a);
  const base = fail || (audit && a.answer === "2") ? baseSeverity(it, a, audit) : "";
  const out: S["AnswerInput"] = {
    item_code: it.item_code,
    answer: null,
    photos: a.photos,
    fixed_on_spot: false,
    ca_required: false,
  };
  if (it.item_type === "numeric") {
    if (a.answer === "na") out.answer = "na";
    else if (a.numeric.trim() !== "") out.numeric_value = a.numeric.trim();
  } else if (it.item_type === "count") {
    if (a.count.trim() === "") return a.photos.length || a.note.trim() ? { ...out, note: a.note.trim() || null } : null;
    out.count_value = Number(a.count);
  } else if (it.item_type === "text") {
    if (!a.answer.trim()) return null;
    out.answer = a.answer.trim();
  } else if (it.item_type === "photo") {
    if (!a.photos.length) return null;
  } else {
    out.answer = a.answer || null;
  }
  if (a.note.trim()) out.note = a.note.trim();
  if (a.equipment_ref.trim()) out.equipment_ref = a.equipment_ref.trim();
  if (base && a.severity && a.severity !== base) out.severity = a.severity as S["AnswerInput"]["severity"];
  const sev = a.severity || base;
  if (fail && (sev === "minor" || sev === "minor_nc" || sev === "observation" || sev === "ofi")) {
    out.ca_required = a.ca_required;
    if (!audit) out.fixed_on_spot = a.fixed_on_spot && !a.ca_required;
  }
  if (fail && a.finding.trim()) out.finding_description_en = a.finding.trim();
  return out;
}

function AnswerChoices({ it, a, onPick, audit }: { it: Item; a: AnswerState; onPick: (v: string) => void; audit: boolean }) {
  const te = useTranslations("enums");
  const td = useTranslations("fdDesign");
  const bi = useBi();
  const { severity: sevLabel } = useFieldRef();
  // Audits (AUD-2): say on the button which finding grade a rating raises, before it is tapped.
  const consequence = (v: string) => (audit && it.item_type === "rating_0_3" && v !== "3" ? td("consequence", { grade: sevLabel(baseSeverity(it, { ...a, answer: v }, true)) }) : null);
  const opts: { value: string; label: string; bad?: boolean }[] =
    it.item_type === "yes_no"
      ? [
          { value: "compliant", label: te("fdAnswer.compliant") },
          { value: "non_compliant", label: te("fdAnswer.non_compliant"), bad: true },
        ]
      : it.item_type === "rating_0_3"
        ? ["3", "2", "1", "0"].map((r) => ({ value: r, label: te(`fdRating.${r}` as "fdRating.0"), bad: r === "0" || r === "1" }))
        : (it.options ?? []).map((o) => ({ value: o.code, label: bi(o.label_en, o.label_ar), bad: o.maps_to === "non_compliant" }));
  if (it.na_allowed) opts.push({ value: "na", label: te("fdAnswer.na") });
  return (
    <div
      role="radiogroup"
      aria-label={bi(it.text_en, it.text_ar)}
      className={cn("grid gap-2", opts.length === 2 ? "grid-cols-2" : opts.length === 3 ? "grid-cols-3" : "grid-cols-2 sm:grid-cols-4")}
      data-testid={`ans-${it.item_code}`}
    >
      {opts.map((o) => {
        const on = a.answer === o.value;
        const c = consequence(o.value);
        return (
          <Button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            variant={on ? (o.bad ? "destructive" : "default") : "outline"}
            className={cn("h-auto min-h-12 justify-start gap-2 px-3 py-2 text-start text-base whitespace-normal", !on && o.bad && "border-danger/40")}
            onClick={() => onPick(o.value)}
            data-testid={`ans-${it.item_code}-${o.value}`}
          >
            <ChoiceMark on={on} />
            <span className="flex min-w-0 flex-col">
              <span className="font-medium">{o.label}</span>
              {c ? <span className={cn("text-xs", on ? "opacity-90" : "text-muted-foreground")}>{c}</span> : null}
            </span>
          </Button>
        );
      })}
    </div>
  );
}

/** One checklist item on the phone: answer buttons, and for a non-compliance the note, photos and finding. */
export function ItemAnswer({ it, a, onChange, audit = false, readOnly = false }: { it: Item; a: AnswerState; onChange: (a: AnswerState) => void; audit?: boolean; readOnly?: boolean }) {
  const t = useTranslations("field.run");
  const te = useTranslations("enums");
  const bi = useBi();
  const { severity: sevLabel } = useFieldRef();
  const fail = failing(it, a);
  const base = fail || (audit && a.answer === "2") ? baseSeverity(it, a, audit) : "";
  const sev = a.severity || base;
  const ladder = audit ? ["observation", "minor_nc", "major_nc"] : ["minor", "major", "critical"];
  const canRaise = ladder.filter((s) => (SEVERITY_RANK[s] ?? 0) >= (SEVERITY_RANK[base] ?? 0));
  const minor = sev === "minor" || sev === "minor_nc" || sev === "observation";
  const set = (p: Partial<AnswerState>) => onChange({ ...a, ...p });
  const photoNeeded = fail && (it.photo_required_on_fail || it.critical);
  return (
    <li
      className={cn("flex flex-col gap-3 rounded-lg border p-3", fail && "border-danger/50 bg-danger-bg/30", it.critical && "border-s-4 border-s-danger")}
      data-testid="run-item"
      data-code={it.item_code}
      data-state={!answered(it, a) ? "open" : fail ? "fail" : "ok"}
    >
      <div className="flex items-start gap-2 text-sm">
        <Code className="shrink-0 font-semibold">{it.item_code}</Code>
        <span className="flex-1">
          <span className="block font-medium">{bi(it.text_en, it.text_ar)}</span>
          {it.guidance_en || it.guidance_ar ? <span className="mt-0.5 block text-xs text-muted-foreground">{bi(it.guidance_en, it.guidance_ar)}</span> : null}
          {it.reference ? <span className="mt-0.5 block text-xs text-muted-foreground ltr">{it.reference}</span> : null}
        </span>
        {it.critical ? <CriticalMark /> : null}
      </div>
      {readOnly ? null : it.item_type === "yes_no" || it.item_type === "rating_0_3" || it.item_type === "single_select" ? (
        <AnswerChoices it={it} a={a} audit={audit} onPick={(v) => set({ answer: v, severity: "" })} />
      ) : it.item_type === "numeric" ? (
        <div className="flex flex-wrap items-end gap-2">
          <FormField id={`num-${it.item_code}`} label={t("value", { unit: it.numeric_rule?.unit ?? "" })} hint={it.numeric_rule ? t("range", { min: it.numeric_rule.min, max: it.numeric_rule.max, unit: it.numeric_rule.unit }) : undefined}>
            <Input type="number" inputMode="decimal" className="ltr w-40" value={a.numeric} onChange={(e) => set({ numeric: e.target.value, answer: "", severity: "" })} data-testid={`num-${it.item_code}`} />
          </FormField>
          {it.na_allowed ? (
            <Button type="button" variant={a.answer === "na" ? "default" : "outline"} className="min-h-11" onClick={() => set({ answer: a.answer === "na" ? "" : "na", numeric: "" })}>
              <ChoiceMark on={a.answer === "na"} />
              {te("fdAnswer.na")}
            </Button>
          ) : null}
        </div>
      ) : it.item_type === "count" ? (
        <Input type="number" inputMode="numeric" min={0} className="ltr w-32" aria-label={t("count")} value={a.count} onChange={(e) => set({ count: e.target.value })} data-testid={`count-${it.item_code}`} />
      ) : it.item_type === "text" ? (
        <Textarea maxLength={500} aria-label={t("text")} value={a.answer} onChange={(e) => set({ answer: e.target.value })} data-testid={`text-${it.item_code}`} />
      ) : (
        <PhotoPicker value={a.photos} onChange={(photos) => set({ photos })} testId={`photo-${it.item_code}`} />
      )}
      {fail && it.stop_rule === "stop_work" && !audit ? <StopNow /> : null}
      {!readOnly && (fail || (audit && a.answer === "2")) ? (
        <div className="flex flex-col gap-3 border-t pt-3" data-testid={`fail-${it.item_code}`}>
          <FormField id={`note-${it.item_code}`} label={t("note")} required={fail} hint={<NoNamesHint />}>
            <Textarea maxLength={500} value={a.note} onChange={(e) => set({ note: e.target.value })} data-testid={`note-${it.item_code}`} />
          </FormField>
          {fail ? (
            <div className="flex flex-col gap-1">
              <span className="text-sm font-medium">
                {t("photos")}
                {photoNeeded ? <span className="text-danger"> *</span> : null}
              </span>
              <PhotoPicker value={a.photos} onChange={(photos) => set({ photos })} testId={`photo-${it.item_code}`} required={photoNeeded} />
            </div>
          ) : null}
          <div className="flex flex-wrap items-end gap-3">
            <FormField id={`sev-${it.item_code}`} label={audit ? t("grade") : t("severity")} hint={t("raiseOnly")}>
              <Select value={sev} onChange={(e) => set({ severity: e.target.value })} data-testid={`sev-${it.item_code}`}>
                {canRaise.map((s) => (
                  <option key={s} value={s}>
                    {sevLabel(s)}
                  </option>
                ))}
              </Select>
            </FormField>
            {fail && minor ? (
              <>
                <CheckboxField id={`ca-${it.item_code}`} label={t("caRequired")}>
                  <Checkbox checked={a.ca_required} onChange={(e) => set({ ca_required: e.target.checked, fixed_on_spot: false })} data-testid={`ca-${it.item_code}`} />
                </CheckboxField>
                {!audit ? (
                  <CheckboxField id={`fix-${it.item_code}`} label={t("fixedOnSpot")}>
                    <Checkbox checked={a.fixed_on_spot} onChange={(e) => set({ fixed_on_spot: e.target.checked, ca_required: false })} data-testid={`fix-${it.item_code}`} />
                  </CheckboxField>
                ) : null}
              </>
            ) : fail && !audit ? (
              <span className="text-xs text-muted-foreground" data-testid={`ca-auto-${it.item_code}`}>
                {t("caAuto")}
              </span>
            ) : null}
          </div>
          {fail ? (
            <FormField id={`eq-${it.item_code}`} label={t("equipmentRef")} hint={t("equipmentHint")}>
              <Input className="ltr" maxLength={120} value={a.equipment_ref} onChange={(e) => set({ equipment_ref: e.target.value })} />
            </FormField>
          ) : null}
          {fail && it.suggested_ca_en ? (
            <p className="text-xs text-muted-foreground">
              {t("suggestedCa")} <span dir="auto">{bi(it.suggested_ca_en, it.suggested_ca_ar)}</span>
              {it.suggested_control_level ? ` · ${te(`controlLevel.${it.suggested_control_level}`)}` : ""}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/** FND-7: shown at the moment of the answer, also offline. */
function StopNow() {
  const t = useTranslations("field.run");
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border-2 border-danger bg-danger-bg p-3 text-danger" data-testid="stop-now">
      <OctagonAlert aria-hidden className="size-8 shrink-0" />
      <span>
        <span className="block text-lg font-bold">{t("stopNow")}</span>
        <span className="block text-sm">{t("stopNowHint")}</span>
      </span>
    </div>
  );
}

/* ═════════════ manual findings (FND-2) ═════════════ */

export interface ManualFinding {
  severity: string;
  description: string;
  ca_required: boolean;
  fixed_on_spot: boolean;
}

export function ManualFindings({ value, onChange, audit = false }: { value: ManualFinding[]; onChange: (v: ManualFinding[]) => void; audit?: boolean }) {
  const t = useTranslations("field.run");
  const { severity: sevLabel } = useFieldRef();
  const sevs = audit ? ["ofi", "observation", "minor_nc", "major_nc"] : ["minor", "major", "critical"];
  return (
    <div className="flex flex-col gap-3" data-testid="manual-findings">
      {value.map((f, i) => (
        <div key={i} className="flex flex-col gap-2 rounded-md border p-3" data-testid="manual-finding">
          <div className="flex flex-wrap items-end gap-3">
            <FormField id={`mf-sev-${i}`} label={audit ? t("grade") : t("severity")}>
              <Select value={f.severity} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, severity: e.target.value, fixed_on_spot: false } : x)))}>
                {sevs.map((s) => (
                  <option key={s} value={s}>
                    {sevLabel(s)}
                  </option>
                ))}
              </Select>
            </FormField>
            {f.severity === "minor" || f.severity === "minor_nc" || f.severity === "observation" || f.severity === "ofi" ? (
              <CheckboxField id={`mf-ca-${i}`} label={t("caRequired")}>
                <Checkbox checked={f.ca_required} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, ca_required: e.target.checked } : x)))} />
              </CheckboxField>
            ) : null}
            <Button type="button" variant="ghost" size="sm" className="ms-auto" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label={t("removeFinding")}>
              <Trash2 aria-hidden />
            </Button>
          </div>
          <FormField id={`mf-desc-${i}`} label={t("findingText")} required hint={<NoNamesHint />}>
            <Textarea maxLength={1000} value={f.description} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} data-testid="mf-desc" />
          </FormField>
        </div>
      ))}
      <Button type="button" variant="outline" className="min-h-11 self-start" onClick={() => onChange([...value, { severity: audit ? "observation" : "minor", description: "", ca_required: false, fixed_on_spot: false }])} data-testid="mf-add">
        <Plus aria-hidden />
        {t("addFinding")}
      </Button>
    </div>
  );
}

export function toManualInput(f: ManualFinding): S["ManualFindingInput"] {
  return { severity: f.severity as S["ManualFindingInput"]["severity"], description_en: f.description.trim(), ca_required: f.ca_required, fixed_on_spot: false };
}

/** Items grouped by section in template order; airside-only items hidden outside airside zones (EXE-1). */
export function useSections(t: Template | null | undefined, airside: boolean) {
  return useMemo(() => {
    if (!t) return [];
    const secs = [...t.sections].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    return secs
      .map((s) => ({ s, items: t.items.filter((i) => i.section_code === s.code && (airside || !i.airside_only)).sort((a, b) => (a.order ?? 0) - (b.order ?? 0)) }))
      .filter((x) => x.items.length);
  }, [t, airside]);
}

/* ═════════════ checklist run (EXE-1…EXE-7, FND-1…FND-7) ═════════════ */

export function ChecklistRunPage() {
  return <ProjectGate>{(p) => <Run project={p} />}</ProjectGate>;
}

interface Start {
  inspectionId: string | null;
  ref: string | null;
  template: Template;
  siteId: string;
  zoneId: string;
  engagementId: string;
  startedAt: string;
}

function Run({ project }: { project: Project }) {
  const t = useTranslations("field.run");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const s = useSearchState();
  const preset = s.get("inspection") ?? "";
  const [start, setStart] = useState<Start | null>(null);
  const [done, setDone] = useState<{ r: S["ResponseRead"] } | { queued: string } | null>(null);
  const [key, setKey] = useState(0);
  if (!caps.record) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FieldInspectSubNav />
      <OutboxPanel kind="checklist" projectId={project.id} />
      {done ? (
        <Done
          d={done}
          onAgain={() => {
            setDone(null);
            setStart(null);
            setKey(key + 1);
            s.set({ inspection: null });
          }}
        />
      ) : start ? (
        <Answering key={key} project={project} start={start} onBack={() => setStart(null)} onDone={setDone} />
      ) : (
        <>
          <div className="mb-4">
            <OfflinePackCard projectId={project.id} />
          </div>
          <Chooser project={project} preset={preset} onStart={setStart} />
        </>
      )}
    </div>
  );
}

function Chooser({ project, preset, onStart }: { project: Project; preset: string; onStart: (s: Start) => void }) {
  const t = useTranslations("field.run");
  const bi = useBi();
  const opts = useProjectOptions(project.id);
  const { packs } = useFieldOffline();
  const pack = packs[project.id]?.pack;
  const live = useTemplates({ kind: "inspection", status: ["published"], project_id: project.id });
  const templates = (live.data?.items ?? pack?.templates.filter((x) => x.kind === "inspection" && x.status === "published") ?? []).filter((x) => x.kind === "inspection" && x.status === "published");
  const ins = useInspection(preset);
  const plan = useInspectionPlan(ins.data?.plan_id ?? "");
  const [tpl, setTpl] = useState("");
  const [site, setSite] = useState("");
  const [zone, setZone] = useState("");
  const [eng, setEng] = useState("");
  const zt = zone ? opts.zoneById.get(zone)?.zone_type : null;
  const planned = ins.data;
  const plannedTpl = planned ? templates.find((x) => x.template_code === (plan.data?.template_code ?? "") && x.inspection_type === planned.inspection_type) ?? null : null;
  const plannedChoices = planned ? templates.filter((x) => x.inspection_type === planned.inspection_type) : [];
  const chosen = templates.find((x) => x.id === tpl) ?? null;
  const zoneOk = !chosen || !zt || !chosen.zone_types.length || chosen.zone_types.includes(zt);

  if (preset && planned) {
    const use = plannedTpl ?? plannedChoices.find((x) => x.id === tpl) ?? null;
    return (
      <Card data-testid="run-planned">
        <CardHeader>
          <CardTitle className="text-base">
            <Code>{planned.ref}</Code>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <p>
            <Code>{planned.site.code}</Code>
            {planned.zone ? (
              <>
                {" · "}
                <Code>{planned.zone.code}</Code>
              </>
            ) : null}
            {planned.engagement ? (
              <>
                {" · "}
                <Code>{planned.engagement.short_code}</Code>
              </>
            ) : null}
          </p>
          {plannedTpl ? (
            <p data-testid="run-template">
              <Code>{plannedTpl.template_code}</Code> v{plannedTpl.version} · {bi(plannedTpl.title_en, plannedTpl.title_ar)}
            </p>
          ) : (
            <FormField id="run-tpl" label={t("template")} hint={t("planNoTemplate")}>
              <Select value={tpl} onChange={(e) => setTpl(e.target.value)} data-testid="run-template-select">
                <option value="">—</option>
                {plannedChoices.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.template_code} v{x.version} · {bi(x.title_en, x.title_ar)}
                  </option>
                ))}
              </Select>
            </FormField>
          )}
          <Button
            className="min-h-12 text-base"
            disabled={!use}
            onClick={() => use && onStart({ inspectionId: planned.id, ref: planned.ref, template: use, siteId: planned.site.id, zoneId: planned.zone?.id ?? "", engagementId: planned.engagement?.id ?? "", startedAt: new Date().toISOString() })}
            data-testid="run-start"
          >
            <ClipboardCheck aria-hidden />
            {t("start")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const instances = pack?.instances ?? [];
  return (
    <div className="flex flex-col gap-4">
      {instances.length ? (
        <Card data-testid="run-instances">
          <CardHeader>
            <CardTitle className="text-base">{t("myPlanned")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y text-sm">
              {instances.map((i) => (
                <li key={i.inspection_id} className="flex items-center justify-between gap-2 py-2">
                  <span>
                    <Code>{i.ref}</Code> · {i.planned_date}
                  </span>
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/field-inspections/new?inspection=${i.inspection_id}`}>{t("open")}</Link>
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      <Card data-testid="run-unplanned">
        <CardHeader>
          <CardTitle className="text-base">{t("unplanned")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <FormField id="run-tpl" label={t("template")} required>
            <Select value={tpl} onChange={(e) => setTpl(e.target.value)} data-testid="run-template-select">
              <option value="">—</option>
              {templates.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.template_code} v{x.version} · {bi(x.title_en, x.title_ar)}
                </option>
              ))}
            </Select>
          </FormField>
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField id="run-site" label={t("site")} required>
              <Select value={site} onChange={(e) => (setSite(e.target.value), setZone(""), setEng(""))} data-testid="run-site">
                <option value="">—</option>
                {opts.sites.map((x) => (
                  <option key={x.value} value={x.value}>
                    {x.code}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="run-zone" label={t("zone")}>
              <Select value={zone} onChange={(e) => setZone(e.target.value)} data-testid="run-zone">
                <option value="">—</option>
                {opts.zones
                  .filter((z) => z.siteId === site)
                  .map((z) => (
                    <option key={z.value} value={z.value}>
                      {z.label}
                    </option>
                  ))}
              </Select>
            </FormField>
            <FormField id="run-eng" label={t("engagement")}>
              <Select value={eng} onChange={(e) => setEng(e.target.value)} data-testid="run-eng">
                <option value="">—</option>
                {opts.engagements
                  .filter((e) => !site || e.siteIds.includes(site))
                  .map((e) => (
                    <option key={e.value} value={e.value}>
                      {e.label}
                    </option>
                  ))}
              </Select>
            </FormField>
          </div>
          {!zoneOk ? (
            <Alert tone="danger" data-testid="run-not-applicable">
              {t("notApplicable")}
            </Alert>
          ) : null}
          <Button
            className="min-h-12 text-base"
            disabled={!chosen || !site || !zoneOk}
            onClick={() => chosen && onStart({ inspectionId: null, ref: null, template: chosen, siteId: site, zoneId: zone, engagementId: eng, startedAt: new Date().toISOString() })}
            data-testid="run-start"
          >
            <ClipboardCheck aria-hidden />
            {t("start")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Answering({ project, start, onBack, onDone }: { project: Project; start: Start; onBack: () => void; onDone: (d: { r: S["ResponseRead"] } | { queued: string }) => void }) {
  const t = useTranslations("field.run");
  const bi = useBi();
  const { items: refItems, label } = useFieldRef();
  const opts = useProjectOptions(project.id);
  const { packs } = useFieldOffline();
  const zone = start.zoneId ? opts.zoneById.get(start.zoneId) : null;
  const airside = zone?.zone_type === "airside";
  const sections = useSections(start.template, airside);
  const all = sections.flatMap((x) => x.items);
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({});
  const [manual, setManual] = useState<ManualFinding[]>([]);
  const [activity, setActivity] = useState("");
  const [role, setRole] = useState("supervisor");
  const [instructedAt, setInstructedAt] = useState(nowLocal());
  const [permitIds, setPermitIds] = useState<string[]>([]);
  const [clientUuid] = useState(newUuid);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const a = (code: string) => answers[code] ?? emptyAnswer();
  const stopItems = all.filter((i) => i.stop_rule === "stop_work" && failing(i, answers[i.item_code]));
  const permits = usePermits(project.id, { zone_id: start.zoneId ? [start.zoneId] : null, status: ["issued", "active"], page_size: 50 }, { enabled: stopItems.length > 0 && Boolean(start.zoneId) });
  const scored = all.filter((i) => i.item_type !== "text" && i.item_type !== "photo" && i.item_type !== "count");
  const doneCount = scored.filter((i) => answered(i, answers[i.item_code])).length;
  const ready = all.every((i) => answerReady(i, answers[i.item_code])) && manual.every((m) => m.description.trim().length > 0) && (stopItems.length === 0 || (activity.trim().length > 0 && Boolean(instructedAt)));
  const anyCritical = all.some((i) => i.critical && failing(i, answers[i.item_code]));

  async function submit() {
    setBusy(true);
    setError(null);
    const body: S["SubmissionCreate"] = {
      client_uuid: clientUuid,
      inspection_id: start.inspectionId,
      template_id: start.template.id,
      template_code: start.template.template_code,
      site_id: start.inspectionId ? null : start.siteId,
      zone_id: start.inspectionId ? null : start.zoneId || null,
      engagement_id: start.inspectionId ? null : start.engagementId || null,
      started_at: start.startedAt,
      completed_at: new Date().toISOString(),
      answers: all.map((i) => toAnswerInput(i, answers[i.item_code], false)).filter((x): x is S["AnswerInput"] => x !== null),
      manual_findings: manual.map(toManualInput),
      stop_work: stopItems.length ? { activity_en: activity.trim(), instructed_role: role as S["InstructedRole"], instructed_at: fromLocalInput(instructedAt) ?? new Date().toISOString(), permit_ids: permitIds } : null,
    };
    const labelText = `${start.template.template_code} · ${start.ref ?? opts.sites.find((x) => x.value === start.siteId)?.code ?? ""}`;
    const res = await submitWithOutbox<S["ResponseRead"]>("checklist", project.id, body, labelText, cacheHoursOf(packs[project.id]?.pack));
    setBusy(false);
    if (res.status === "sent") onDone({ r: res.record });
    else if (res.status === "queued") onDone({ queued: labelText });
    else setError(res.error);
  }

  return (
    <div className="flex flex-col gap-4" data-testid="run-answering">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 p-4 text-sm">
          <Code className="font-semibold">
            {start.template.template_code} v{start.template.version}
          </Code>
          <span className="font-medium">{bi(start.template.title_en, start.template.title_ar)}</span>
          <span className="text-muted-foreground">
            {start.ref ? <Code>{start.ref}</Code> : null} {opts.sites.find((x) => x.value === start.siteId)?.code}
            {zone ? ` · ${zone.code}` : ""}
          </span>
          <span className="ms-auto font-medium tabular-nums" data-testid="run-progress">
            {t("progress", { done: doneCount, total: scored.length })}
          </span>
          <Button variant="ghost" size="sm" onClick={onBack}>
            {t("change")}
          </Button>
        </CardContent>
      </Card>
      {sections.map(({ s, items }) => (
        <section key={s.code} className="flex flex-col gap-2" data-testid="run-section">
          <h2 className="text-sm font-semibold text-muted-foreground">
            <Code>{s.code}</Code> {bi(s.title_en, s.title_ar)}
          </h2>
          <ol className="flex flex-col gap-3">
            {items.map((it) => (
              <ItemAnswer key={it.item_code} it={it} a={a(it.item_code)} onChange={(x) => setAnswers({ ...answers, [it.item_code]: x })} />
            ))}
          </ol>
        </section>
      ))}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("manualTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ManualFindings value={manual} onChange={setManual} />
        </CardContent>
      </Card>
      {stopItems.length ? (
        <Card className="border-2 border-danger" data-testid="stop-fields">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base text-danger">
              <OctagonAlert aria-hidden />
              {t("stopTitle", { items: stopItems.map((i) => i.item_code).join(", ") })}
            </CardTitle>
            <p className="text-sm text-muted-foreground">{t("stopIntro")}</p>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <FormField id="sw-activity" label={t("stopActivity")} required hint={<NoNamesHint />}>
              <Input maxLength={300} value={activity} onChange={(e) => setActivity(e.target.value)} data-testid="sw-activity" />
            </FormField>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField id="sw-role" label={t("stopRole")} required>
                <Select value={role} onChange={(e) => setRole(e.target.value)} data-testid="sw-role">
                  {refItems("instructed_roles").map((r) => (
                    <option key={r.code} value={r.code}>
                      {label("instructed_roles", r.code)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="sw-at" label={t("stopAt")} required>
                <Input type="datetime-local" value={instructedAt} onChange={(e) => setInstructedAt(e.target.value)} data-testid="sw-at" />
              </FormField>
            </div>
            {start.zoneId ? (
              <MultiSelect
                id="sw-permits"
                label={t("stopPermits")}
                allLabel={t("noPermits")}
                options={(permits.data?.items ?? []).map((p) => ({ value: p.id, label: p.permit_no }))}
                value={permitIds}
                onChange={setPermitIds}
                className="lg:w-full"
              />
            ) : null}
          </CardContent>
        </Card>
      ) : null}
      {anyCritical && !stopItems.length ? (
        <Alert tone="danger" data-testid="critical-note">
          {t("criticalNote")}
        </Alert>
      ) : null}
      <MutationError error={error} />
      <RunBar
        done={doneCount}
        total={scored.length}
        failingCount={all.filter((i) => failing(i, answers[i.item_code])).length}
        open={all.filter((i) => !answered(i, answers[i.item_code])).map((i) => i.item_code)}
        incomplete={all.filter((i) => answered(i, answers[i.item_code]) && !answerReady(i, answers[i.item_code])).map((i) => i.item_code)}
        manualMissing={!manual.every((m) => m.description.trim().length > 0)}
        stopMissing={stopItems.length > 0 && !(activity.trim().length > 0 && Boolean(instructedAt))}
        ready={ready}
        busy={busy}
        onSubmit={() => void submit()}
      />
    </div>
  );
}

function scrollToTestId(sel: string) {
  const el = document.querySelector<HTMLElement>(sel);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  const f = el.querySelector<HTMLElement>("button[role=radio], textarea, input");
  f?.focus({ preventScroll: true });
}

/**
 * Sticky at the bottom of the phone screen while answering: progress, what still blocks sending (with a jump to the
 * next item), and the submit button under the thumb. Nothing here is new logic: the counts are the ones the page used.
 */
function RunBar(p: { done: number; total: number; failingCount: number; open: string[]; incomplete: string[]; manualMissing: boolean; stopMissing: boolean; ready: boolean; busy: boolean; onSubmit: () => void }) {
  const t = useTranslations("field.run");
  const td = useTranslations("fdDesign");
  const online = useOnline();
  const pct = p.total ? Math.round((p.done / p.total) * 100) : 100;
  const next = p.open[0] ?? p.incomplete[0] ?? null;
  const goNext = () => {
    if (next) scrollToTestId(`[data-testid="run-item"][data-code="${next}"]`);
    else if (p.manualMissing) scrollToTestId('[data-testid="manual-findings"]');
    else if (p.stopMissing) scrollToTestId('[data-testid="stop-fields"]');
  };
  return (
    <div className="sticky bottom-0 z-20 -mx-1 flex flex-col gap-2 rounded-t-xl border border-b-0 bg-surface/95 p-3 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-surface/90" data-testid="run-bar">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="font-semibold tabular-nums">{td("answeredOf", { done: p.done, total: p.total })}</span>
        {p.failingCount ? (
          <span className="inline-flex items-center gap-1 font-medium text-danger" data-testid="run-failing" data-n={p.failingCount}>
            <XCircle aria-hidden className="size-4" />
            {td("failingN", { n: p.failingCount })}
          </span>
        ) : null}
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={p.total} aria-valuenow={p.done} aria-label={td("answeredOf", { done: p.done, total: p.total })}>
        <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${pct}%` }} />
      </div>
      {p.ready ? (
        <p className="flex items-center gap-1.5 text-sm text-success" data-testid="run-ready">
          <CheckCircle2 aria-hidden className="size-4" />
          {td("readyToSend")}
        </p>
      ) : (
        <ul className="flex flex-col gap-0.5 text-sm text-muted-foreground" data-testid="run-blockers">
          {p.open.length ? <li>{td("toAnswer", { n: p.open.length })}</li> : null}
          {p.incomplete.length ? <li className="text-warning">{td("toComplete", { n: p.incomplete.length })}</li> : null}
          {p.manualMissing ? <li>{td("manualMissing")}</li> : null}
          {p.stopMissing ? <li className="font-medium text-danger">{td("stopMissing")}</li> : null}
        </ul>
      )}
      <OfflineSubmitNote />
      <div className={cn("grid gap-2", p.ready ? "grid-cols-1" : "grid-cols-2")}>
        {!p.ready ? (
          <Button type="button" variant="outline" className="min-h-12 text-base" onClick={goNext} data-testid="run-next">
            <ArrowDown aria-hidden />
            {td("nextItem")}
          </Button>
        ) : null}
        <Button className="min-h-12 text-base" disabled={p.busy || !p.ready} onClick={p.onSubmit} data-testid="run-submit">
          {online ? <Send aria-hidden /> : <Hourglass aria-hidden />}
          {p.busy ? t("sending") : online ? t("submit") : td("saveOnPhone")}
        </Button>
      </div>
    </div>
  );
}

function Done({ d, onAgain }: { d: { r: S["ResponseRead"] } | { queued: string }; onAgain: () => void }) {
  const t = useTranslations("field.run");
  const router = useRouter();
  if ("queued" in d) {
    return (
      <div className="flex flex-col gap-4" data-testid="run-queued">
        <div className="rounded-md border-2 border-warning/50 bg-warning-bg p-4 text-warning">
          <p className="flex items-center gap-2 text-xl font-bold">
            <Hourglass aria-hidden className="size-7" />
            {t("queuedTitle")}
          </p>
          <p className="mt-1 text-sm text-foreground">{t("queuedText", { label: d.queued })}</p>
        </div>
        <Button className="min-h-12 text-base" onClick={onAgain} data-testid="run-again">
          {t("again")}
        </Button>
      </div>
    );
  }
  const r = d.r;
  const pass = r.result === "pass";
  return (
    <div className="flex flex-col gap-4" data-testid="run-done" data-result={r.result ?? ""}>
      <div className={pass ? "rounded-md border-2 border-success/40 bg-success-bg p-4 text-success" : "rounded-md border-2 border-danger/50 bg-danger-bg p-4 text-danger"}>
        <p className="flex items-center gap-2 text-xl font-bold">
          {pass ? <CheckCircle2 aria-hidden className="size-7" /> : <XCircle aria-hidden className="size-7" />}
          {pass ? t("passed") : t("failed")}
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-foreground">
          {r.inspection_ref ? <Code>{r.inspection_ref}</Code> : null}
          <Score v={r.score_pct} className="text-lg font-semibold" />
          <ResultBadge result={r.result} />
          <span>{t("items", { compliant: r.compliant_count, applicable: r.applicable_count })}</span>
        </p>
        {r.stop_work_order_no ? (
          <p className="mt-2 text-sm font-semibold" data-testid="done-stop">
            {t("stopRaised")} <Code>{r.stop_work_order_no}</Code>
          </p>
        ) : null}
        {r.findings.some((f) => f.ca_ref) ? (
          <p className="mt-1 text-sm text-foreground" data-testid="done-cas">
            {t("casRaised")}{" "}
            {r.findings
              .filter((f) => f.ca_ref)
              .map((f) => (
                <Code key={f.id} className="me-1">
                  {f.ca_ref}
                </Code>
              ))}
          </p>
        ) : null}
        {r.answers.filter((x) => x.raise_defect_for).map((x) => (
          <p key={x.item_code} className="mt-1 text-sm text-foreground" data-testid="raise-defect">
            <Link href="/defects" className="text-primary underline">
              {t("raiseDefect", { tag: x.raise_defect_for ?? "" })}
            </Link>
          </p>
        ))}
      </div>
      {r.self_inspection ? <Badge tone="info">{t("selfInspection")}</Badge> : null}
      <ApiWarnings warnings={r.warnings} />
      <div className="flex flex-wrap gap-2">
        {r.inspection_id ? (
          <Button className="min-h-12 text-base" variant="outline" onClick={() => router.push(`/inspections/${r.inspection_id}`)} data-testid="done-open">
            {t("openInspection")}
          </Button>
        ) : null}
        <Button className="min-h-12 text-base" onClick={onAgain} data-testid="run-again">
          {t("again")}
        </Button>
      </div>
    </div>
  );
}
