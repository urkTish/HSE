"use client";
import { Archive, CopyPlus, Pencil, Plus, Send, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { StackedDate } from "@/components/medical/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useFieldRefresh, useTemplate, useTemplates, useTopic, useTopics } from "@/lib/api/field";
import { CONTROL_LEVELS, ITEM_TYPES, LINKED_REF_KINDS, OPTION_MAPPINGS, SCORED_TYPES, TEMPLATE_KINDS, VERSION_STATUSES, WORKER_LANGUAGES, ZONE_TYPES } from "@/lib/field-enums";
import { useRefLists } from "@/lib/reference";
import { useSearchState } from "@/lib/url-state";
import { CriticalMark, FieldLibrarySubNav, FieldReasonDialog, VersionStatusBadge, useBi, useFieldCaps, useFieldRef } from "./common";

type S = Schemas;
type Template = S["TemplateRead"];
type Item = S["TemplateItem-Output"];
type Topic = S["TopicRead"];

/* ═════════════ checklist template library (§3.1, §3.2, TPL-1…TPL-6) ═════════════ */

export function TemplatesPage() {
  const t = useTranslations("field.lib");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useFieldCaps();
  const bi = useBi();
  const { label } = useFieldRef();
  const ref = useRefLists();
  const s = useSearchState();
  const kind = (s.get("kind") ?? "") as S["TemplateKind"] | "";
  const status = (s.get("status") ?? "") as S["VersionStatus"] | "";
  const q = useTemplates({ kind: kind || null, status: status ? [status] : null }, { enabled: caps.libraryView });
  const [creating, setCreating] = useState(false);
  if (!caps.libraryView) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.author ? (
            <Button onClick={() => setCreating(true)} data-testid="tpl-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <FieldLibrarySubNav />
      <ListToolbar>
        <SelectFilter id="tpl-kind" label={t("kind")} value={kind} onChange={(v) => s.set({ kind: v })} options={TEMPLATE_KINDS.map((x) => ({ value: x, label: te(`fdTemplateKind.${x}`) }))} />
        <SelectFilter id="tpl-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={VERSION_STATUSES.map((x) => ({ value: x, label: te(`fdVersionStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="tpl-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("titleCol")}</TH>
              <TH>{t("type")}</TH>
              <TH className="text-end">{t("items")}</TH>
              <TH>{t("passMark")}</TH>
              <TH>{t("reviewDue")}</TH>
              <TH>{tc("status")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((x) => (
              <TR key={x.id} data-testid="tpl-row" data-code={x.template_code} data-version={x.version} data-status={x.status}>
                <TD label={t("code")}>
                  <Link href={`/checklist-templates/${x.id}`} className="font-medium text-primary hover:underline">
                    <Code>{x.template_code}</Code> <span className="ltr">v{x.version}</span>
                  </Link>
                </TD>
                <TD label={t("titleCol")}>{bi(x.title_en, x.title_ar)}</TD>
                <TD label={t("type")}>
                  {te(`fdTemplateKind.${x.kind}`)} · {x.kind === "inspection" ? ref.label("inspection_type", x.inspection_type) : label("audit_types", x.audit_type)}
                  {x.zone_types.length ? <span className="block text-xs text-muted-foreground">{x.zone_types.map((z) => te(`fdZoneType.${z}`)).join(" · ")}</span> : null}
                </TD>
                <TD label={t("items")} className="text-end tabular-nums">
                  {x.item_count}
                  {x.critical_count ? <span className="block text-xs text-danger">{t("criticalN", { n: x.critical_count })}</span> : null}
                </TD>
                <TD label={t("passMark")}>
                  <bdi className="ltr tabular-nums">{x.pass_mark_pct} %</bdi>
                </TD>
                <TD label={t("reviewDue")}>
                  <StackedDate v={x.review_due_on} />
                </TD>
                <TD label={tc("status")}>
                  <VersionStatusBadge status={x.status} overdue={x.review_overdue} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {creating ? <NewTemplateDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function NewTemplateDialog({ onClose }: { onClose: () => void }) {
  const t = useTranslations("field.lib");
  const te = useTranslations("enums");
  const ref = useRefLists();
  const { items, label } = useFieldRef();
  const router = useRouter();
  const refresh = useFieldRefresh();
  const [code, setCode] = useState("");
  const [kind, setKind] = useState<S["TemplateKind"]>("inspection");
  const [type, setType] = useState("");
  const [en, setEn] = useState("");
  const [ar, setAr] = useState("");
  const [pass, setPass] = useState("85.0");
  const valid = /^[A-Z]{2,8}$/.test(code) && type && en.trim();
  return (
    <StepDialog
      title={t("new")}
      description={t("newHint")}
      confirmLabel={t("createDraft")}
      disabled={!valid}
      testId="tpl-create"
      onConfirm={async () => {
        const r = await unwrap(
          api.POST("/api/v1/checklist-templates", {
            body: {
              template_code: code,
              kind,
              inspection_type: kind === "inspection" ? (type as S["InspectionType"]) : null,
              audit_type: kind === "audit" ? (type as S["AuditType"]) : null,
              title_en: en.trim(),
              title_ar: ar.trim(),
              pass_mark_pct: pass,
              sections: [{ code: "A", title_en: "General", title_ar: "عام", order: 1 }],
              items: [],
              zone_types: [],
              project_ids: [],
            },
          }),
        );
        await refresh();
        router.push(`/checklist-templates/${r.id}`);
      }}
      onClose={onClose}
    >
      <FormField id="nt-code" label={t("code")} required hint={t("codeHint")}>
        <Input className="ltr" maxLength={8} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} data-testid="nt-code" />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="nt-kind" label={t("kind")} required>
          <Select value={kind} onChange={(e) => (setKind(e.target.value as S["TemplateKind"]), setType(""))}>
            {TEMPLATE_KINDS.map((k) => (
              <option key={k} value={k}>
                {te(`fdTemplateKind.${k}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="nt-type" label={t("type")} required>
          <Select value={type} onChange={(e) => setType(e.target.value)} data-testid="nt-type">
            <option value="">—</option>
            {kind === "inspection"
              ? ref.options("inspection_type").map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))
              : items("audit_types").map((o) => (
                  <option key={o.code} value={o.code}>
                    {label("audit_types", o.code)}
                  </option>
                ))}
          </Select>
        </FormField>
      </div>
      <FormField id="nt-en" label={t("titleEn")} required>
        <Input maxLength={150} value={en} onChange={(e) => setEn(e.target.value)} data-testid="nt-en" />
      </FormField>
      <FormField id="nt-ar" label={t("titleAr")}>
        <Input dir="rtl" maxLength={150} value={ar} onChange={(e) => setAr(e.target.value)} />
      </FormField>
      <FormField id="nt-pass" label={t("passMark")}>
        <Input type="number" className="ltr w-32" min={50} max={100} step={0.1} value={pass} onChange={(e) => setPass(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

export function TemplatePage({ id }: { id: string }) {
  const t = useTranslations("field.lib");
  const te = useTranslations("enums");
  const tn = useTranslations("field.nav");
  const caps = useFieldCaps();
  const bi = useBi();
  const ref = useRefLists();
  const { label } = useFieldRef();
  const router = useRouter();
  const refresh = useFieldRefresh();
  const q = useTemplate(id);
  const versions = useTemplates({ template_code: q.data?.template_code ?? "" }, { enabled: Boolean(q.data) });
  const [dialog, setDialog] = useState<"header" | "section" | "publish" | "retire" | "delete" | { item: Item | null } | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const x = q.data;
  const draft = x.status === "draft";
  const editable = draft && caps.author;
  const hasDraft = (versions.data?.items ?? []).some((v) => v.status === "draft");
  async function patch(body: S["TemplateUpdate"]) {
    await unwrap(api.PATCH("/api/v1/checklist-templates/{template_id}", { params: { path: { template_id: x.id } }, body }));
    await refresh();
  }
  const sections = [...x.sections].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("templates"), href: "/checklist-templates" }, { label: `${x.template_code} v${x.version}` }]} />
      <Card data-testid="tpl-detail" data-status={x.status}>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-sm text-muted-foreground">
              <Code>{x.template_code}</Code> <span className="ltr">v{x.version}</span> · {te(`fdTemplateKind.${x.kind}`)} · {x.kind === "inspection" ? ref.label("inspection_type", x.inspection_type) : label("audit_types", x.audit_type)}
            </p>
            <CardTitle className="flex flex-wrap items-center gap-2">
              <span data-testid="tpl-title">{bi(x.title_en, x.title_ar)}</span>
              <VersionStatusBadge status={x.status} overdue={x.review_overdue} />
            </CardTitle>
          </div>
          <div className="flex flex-wrap gap-2">
            {editable ? (
              <Button size="sm" variant="outline" onClick={() => setDialog("header")} data-testid="tpl-edit">
                <Pencil aria-hidden />
                {t("editHeader")}
              </Button>
            ) : null}
            {draft && caps.publish ? (
              <Button size="sm" onClick={() => setDialog("publish")} data-testid="tpl-publish">
                <Send aria-hidden />
                {t("publish")}
              </Button>
            ) : null}
            {x.status === "published" && caps.author && !hasDraft ? (
              <Button
                size="sm"
                variant="outline"
                onClick={async () => {
                  const r = await unwrap(api.POST("/api/v1/checklist-templates/{template_id}/new-version", { params: { path: { template_id: x.id } } }));
                  await refresh();
                  router.push(`/checklist-templates/${r.id}`);
                }}
                data-testid="tpl-new-version"
              >
                <CopyPlus aria-hidden />
                {t("newVersion")}
              </Button>
            ) : null}
            {x.status === "published" && caps.publish ? (
              <Button size="sm" variant="outline" onClick={() => setDialog("retire")} data-testid="tpl-retire">
                <Archive aria-hidden />
                {t("retire")}
              </Button>
            ) : null}
            {editable ? (
              <Button size="sm" variant="ghost" onClick={() => setDialog("delete")} data-testid="tpl-delete">
                <Trash2 aria-hidden />
                {t("deleteDraft")}
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={t("titleEn")}>{x.title_en}</FieldItem>
            <FieldItem label={t("titleAr")}>
              <span dir="rtl">{x.title_ar || "—"}</span>
            </FieldItem>
            <FieldItem label={t("passMark")}>
              <bdi className="ltr">{x.pass_mark_pct} %</bdi>
            </FieldItem>
            <FieldItem label={t("zoneTypes")}>{x.zone_types.length ? x.zone_types.map((z) => te(`fdZoneType.${z}`)).join(" · ") : t("allZones")}</FieldItem>
            <FieldItem label={t("items")}>
              {x.item_count} · {t("criticalN", { n: x.critical_count })}
            </FieldItem>
            <FieldItem label={t("reviewDue")}>
              <StackedDate v={x.review_due_on} />
            </FieldItem>
            <FieldItem label={t("authored")}>
              <UserName u={x.authored_by} />
            </FieldItem>
            <FieldItem label={t("published")}>
              {x.published_by ? (
                <>
                  <UserName u={x.published_by} /> · <StackedDate v={x.published_at} />
                </>
              ) : (
                "—"
              )}
            </FieldItem>
            {x.change_note ? (
              <FieldItem label={t("changeNote")} wide>
                <span dir="auto">{x.change_note}</span>
              </FieldItem>
            ) : null}
            {x.status_reason ? (
              <FieldItem label={t("statusReason")} wide>
                <span dir="auto">{x.status_reason}</span>
              </FieldItem>
            ) : null}
          </FieldList>
          {!draft && caps.author ? <p className="mt-3 text-xs text-muted-foreground">{t("immutable")}</p> : null}
        </CardContent>
      </Card>
      <div className="mt-6 flex flex-col gap-4">
        {sections.map((sec) => {
          const its = x.items.filter((i) => i.section_code === sec.code).sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
          return (
            <Card key={sec.code} data-testid="tpl-section" data-code={sec.code}>
              <CardHeader className="flex-row items-center justify-between gap-2">
                <CardTitle className="text-base">
                  <Code>{sec.code}</Code> {bi(sec.title_en, sec.title_ar)}
                </CardTitle>
                {editable ? (
                  <Button size="sm" variant="outline" onClick={() => setDialog({ item: { item_code: `${x.template_code}-${String(x.items.length + 1).padStart(2, "0")}`, section_code: sec.code, order: its.length + 1, text_en: "", text_ar: "", item_type: "yes_no", weight: 1, critical: false, stop_rule: "none", na_allowed: false, photo_required_on_fail: false, default_severity: "minor", airside_only: false } as Item })} data-testid="tpl-add-item">
                    <Plus aria-hidden />
                    {t("addItem")}
                  </Button>
                ) : null}
              </CardHeader>
              <CardContent>
                {its.length ? (
                  <ul className="flex flex-col divide-y text-sm">
                    {its.map((i) => (
                      <li key={i.item_code} className="flex flex-wrap items-start gap-2 py-2" data-testid="tpl-item" data-code={i.item_code}>
                        <Code className="shrink-0 font-semibold">{i.item_code}</Code>
                        <span className="min-w-0 flex-1">
                          <span className="block">{bi(i.text_en, i.text_ar)}</span>
                          <span className="mt-0.5 flex flex-wrap gap-1 text-xs text-muted-foreground">
                            <Badge tone="neutral">{te(`fdItemType.${i.item_type}`)}</Badge>
                            {SCORED_TYPES.includes(i.item_type) ? <Badge tone="neutral">{t("weightN", { n: i.weight ?? 1 })}</Badge> : null}
                            {i.stop_rule === "stop_work" ? <Badge tone="danger">{t("stopRule")}</Badge> : null}
                            {i.airside_only ? <Badge tone="info">{t("airsideOnly")}</Badge> : null}
                            {i.na_allowed ? <Badge tone="neutral">{t("naAllowed")}</Badge> : null}
                            {i.numeric_rule ? (
                              <bdi className="ltr">
                                {i.numeric_rule.min}–{i.numeric_rule.max} {i.numeric_rule.unit}
                              </bdi>
                            ) : null}
                          </span>
                        </span>
                        {i.critical ? <CriticalMark /> : null}
                        {editable ? (
                          <span className="flex gap-1">
                            <Button size="sm" variant="ghost" onClick={() => setDialog({ item: i })} aria-label={t("editItem", { code: i.item_code })} data-testid="tpl-edit-item">
                              <Pencil aria-hidden />
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => void patch({ items: x.items.filter((y) => y.item_code !== i.item_code) as S["TemplateItem-Input"][] })} aria-label={t("removeItem", { code: i.item_code })}>
                              <Trash2 aria-hidden />
                            </Button>
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">{t("noItems")}</p>
                )}
              </CardContent>
            </Card>
          );
        })}
        {editable ? (
          <Button variant="outline" className="self-start" onClick={() => setDialog("section")} data-testid="tpl-add-section">
            <Plus aria-hidden />
            {t("addSection")}
          </Button>
        ) : null}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("versions")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y text-sm" data-testid="tpl-versions">
              {(versions.data?.items ?? []).map((v) => (
                <li key={v.id} className="flex flex-wrap items-center gap-2 py-2">
                  <Link href={`/checklist-templates/${v.id}`} className="text-primary hover:underline">
                    <span className="ltr">v{v.version}</span>
                  </Link>
                  <VersionStatusBadge status={v.status} />
                  <StackedDate v={v.published_at} />
                  {v.change_note ? (
                    <span className="flex-1 text-muted-foreground" dir="auto">
                      {v.change_note}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
      {dialog === "header" ? <HeaderDialog x={x} onSave={patch} onClose={() => setDialog(null)} /> : null}
      {dialog === "section" ? <SectionDialog x={x} onSave={patch} onClose={() => setDialog(null)} /> : null}
      {dialog && typeof dialog === "object" ? <ItemDialog x={x} item={dialog.item} onSave={patch} onClose={() => setDialog(null)} /> : null}
      {dialog === "publish" ? (
        <StepDialog
          title={t("publishTitle", { code: x.template_code, v: x.version })}
          description={t("publishHint")}
          confirmLabel={t("publish")}
          testId="tpl-publish-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/checklist-templates/{template_id}/transitions", { params: { path: { template_id: x.id } }, body: { action: "publish" } }));
            await refresh();
            toast.success(t("publishedToast"));
          }}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "retire" ? (
        <FieldReasonDialog
          title={t("retireTitle")}
          description={t("retireHint")}
          confirmLabel={t("retire")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/checklist-templates/{template_id}/transitions", { params: { path: { template_id: x.id } }, body: { action: "retire", reason } }))}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "delete" ? (
        <StepDialog
          title={t("deleteDraft")}
          destructive
          confirmLabel={t("deleteDraft")}
          onConfirm={async () => {
            await unwrap(api.DELETE("/api/v1/checklist-templates/{template_id}", { params: { path: { template_id: x.id } } }));
            await refresh();
            router.push("/checklist-templates");
          }}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}

function HeaderDialog({ x, onSave, onClose }: { x: Template; onSave: (b: S["TemplateUpdate"]) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("field.lib");
  const te = useTranslations("enums");
  const [en, setEn] = useState(x.title_en);
  const [ar, setAr] = useState(x.title_ar);
  const [pass, setPass] = useState(x.pass_mark_pct);
  const [zones, setZones] = useState<S["ZoneType"][]>(x.zone_types);
  const [note, setNote] = useState(x.change_note ?? "");
  return (
    <StepDialog
      title={t("editHeader")}
      confirmLabel={t("save")}
      disabled={!en.trim()}
      testId="tpl-header-save"
      onConfirm={() => onSave({ title_en: en.trim(), title_ar: ar.trim(), pass_mark_pct: pass, zone_types: zones, change_note: note.trim() || null })}
      onClose={onClose}
    >
      <FormField id="th-en" label={t("titleEn")} required>
        <Input maxLength={150} value={en} onChange={(e) => setEn(e.target.value)} />
      </FormField>
      <FormField id="th-ar" label={t("titleAr")}>
        <Input dir="rtl" maxLength={150} value={ar} onChange={(e) => setAr(e.target.value)} data-testid="th-ar" />
      </FormField>
      <FormField id="th-pass" label={t("passMark")}>
        <Input type="number" className="ltr w-32" min={50} max={100} step={0.1} value={pass} onChange={(e) => setPass(e.target.value)} />
      </FormField>
      <CheckboxGroup id="th-zones" legend={t("zoneTypes")} hint={t("zoneTypesHint")} value={zones} onChange={setZones} options={ZONE_TYPES.map((z) => ({ value: z, label: te(`fdZoneType.${z}`) }))} />
      <FormField id="th-note" label={t("changeNote")} hint={x.version >= 2 ? t("changeNoteRequired") : undefined} required={x.version >= 2}>
        <Textarea maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} data-testid="th-note" />
      </FormField>
    </StepDialog>
  );
}

function SectionDialog({ x, onSave, onClose }: { x: Template; onSave: (b: S["TemplateUpdate"]) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("field.lib");
  const [code, setCode] = useState(String.fromCharCode(65 + x.sections.length));
  const [en, setEn] = useState("");
  const [ar, setAr] = useState("");
  return (
    <StepDialog
      title={t("addSection")}
      confirmLabel={t("save")}
      disabled={!code.trim() || !en.trim() || x.sections.some((s) => s.code === code.trim())}
      onConfirm={() => onSave({ sections: [...x.sections, { code: code.trim(), title_en: en.trim(), title_ar: ar.trim(), order: x.sections.length + 1 }] })}
      onClose={onClose}
    >
      <FormField id="ts-code" label={t("sectionCode")} required>
        <Input className="ltr w-24" maxLength={4} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
      </FormField>
      <FormField id="ts-en" label={t("titleEn")} required>
        <Input maxLength={150} value={en} onChange={(e) => setEn(e.target.value)} />
      </FormField>
      <FormField id="ts-ar" label={t("titleAr")}>
        <Input dir="rtl" maxLength={150} value={ar} onChange={(e) => setAr(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function ItemDialog({ x, item, onSave, onClose }: { x: Template; item: Item | null; onSave: (b: S["TemplateUpdate"]) => Promise<void>; onClose: () => void }) {
  const t = useTranslations("field.lib");
  const te = useTranslations("enums");
  const isNew = !item || !x.items.some((i) => i.item_code === item.item_code);
  const [v, setV] = useState<Item>(item ?? ({} as Item));
  const set = (p: Partial<Item>) => setV({ ...v, ...p });
  const scored = SCORED_TYPES.includes(v.item_type);
  const opts = v.options ?? [];
  const valid = /^[A-Z]{2,8}-\d{2,3}$/.test(v.item_code ?? "") && (v.text_en ?? "").trim() && (isNew ? !x.items.some((i) => i.item_code === v.item_code) : true);
  return (
    <StepDialog
      wide
      title={isNew ? t("addItem") : t("editItem", { code: v.item_code })}
      confirmLabel={t("save")}
      disabled={!valid}
      testId="item-save"
      onConfirm={() => {
        const clean: Item = {
          ...v,
          critical: scored ? Boolean(v.critical) : false,
          stop_rule: scored && v.critical ? (v.stop_rule ?? "none") : "none",
          photo_required_on_fail: v.critical ? true : Boolean(v.photo_required_on_fail),
          numeric_rule: v.item_type === "numeric" ? v.numeric_rule : null,
          options: v.item_type === "single_select" ? opts : null,
        };
        const items = isNew ? [...x.items, clean] : x.items.map((i) => (i.item_code === item?.item_code ? clean : i));
        return onSave({ items: items as S["TemplateItem-Input"][] });
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField id="ti-code" label={t("itemCode")} required>
          <Input className="ltr" maxLength={12} value={v.item_code} disabled={!isNew} onChange={(e) => set({ item_code: e.target.value.toUpperCase() })} data-testid="ti-code" />
        </FormField>
        <FormField id="ti-sec" label={t("sectionCode")} required>
          <Select value={v.section_code} onChange={(e) => set({ section_code: e.target.value })}>
            {x.sections.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ti-type" label={t("itemType")} required>
          <Select value={v.item_type} onChange={(e) => set({ item_type: e.target.value as S["ItemType"] })} data-testid="ti-type">
            {ITEM_TYPES.map((i) => (
              <option key={i} value={i}>
                {te(`fdItemType.${i}`)}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      <FormField id="ti-en" label={t("textEn")} required>
        <Textarea maxLength={300} value={v.text_en} onChange={(e) => set({ text_en: e.target.value })} data-testid="ti-en" />
      </FormField>
      <FormField id="ti-ar" label={t("textAr")}>
        <Textarea dir="rtl" maxLength={300} value={v.text_ar ?? ""} onChange={(e) => set({ text_ar: e.target.value })} data-testid="ti-ar" />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ti-gen" label={t("guidanceEn")}>
          <Textarea maxLength={1000} value={v.guidance_en ?? ""} onChange={(e) => set({ guidance_en: e.target.value || null })} />
        </FormField>
        <FormField id="ti-gar" label={t("guidanceAr")}>
          <Textarea dir="rtl" maxLength={1000} value={v.guidance_ar ?? ""} onChange={(e) => set({ guidance_ar: e.target.value || null })} />
        </FormField>
      </div>
      {scored ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField id="ti-weight" label={t("weight")}>
            <Input type="number" className="ltr w-24" min={1} max={5} value={v.weight ?? 1} onChange={(e) => set({ weight: Number(e.target.value) })} />
          </FormField>
          <FormField id="ti-sev" label={t("defaultSeverity")}>
            <Select value={v.default_severity ?? "minor"} disabled={Boolean(v.critical)} onChange={(e) => set({ default_severity: e.target.value as S["app__core__field_enums__FindingSeverity"] })}>
              <option value="minor">{te("fdSeverity.minor")}</option>
              <option value="major">{te("fdSeverity.major")}</option>
            </Select>
          </FormField>
          <FormField id="ti-stop" label={t("stopRule")}>
            <Select value={v.stop_rule ?? "none"} onChange={(e) => set({ stop_rule: e.target.value as S["StopRule"] })} data-testid="ti-stop">
              <option value="none">{te("fdStopRule.none")}</option>
              <option value="stop_work">{te("fdStopRule.stop_work")}</option>
            </Select>
          </FormField>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-x-5 gap-y-1">
        {scored ? (
          <CheckboxField id="ti-critical" label={t("critical")}>
            <Checkbox checked={Boolean(v.critical)} onChange={(e) => set({ critical: e.target.checked, weight: e.target.checked && (v.weight ?? 1) < 3 ? 3 : v.weight })} data-testid="ti-critical" />
          </CheckboxField>
        ) : null}
        <CheckboxField id="ti-na" label={t("naAllowed")}>
          <Checkbox checked={Boolean(v.na_allowed)} onChange={(e) => set({ na_allowed: e.target.checked })} />
        </CheckboxField>
        <CheckboxField id="ti-photo" label={t("photoOnFail")}>
          <Checkbox checked={Boolean(v.photo_required_on_fail || v.critical)} disabled={Boolean(v.critical)} onChange={(e) => set({ photo_required_on_fail: e.target.checked })} />
        </CheckboxField>
        <CheckboxField id="ti-airside" label={t("airsideOnly")}>
          <Checkbox checked={Boolean(v.airside_only)} onChange={(e) => set({ airside_only: e.target.checked })} />
        </CheckboxField>
      </div>
      {v.stop_rule === "stop_work" && !v.critical ? <Alert tone="warning">{t("stopNeedsCritical")}</Alert> : null}
      {v.item_type === "numeric" ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField id="ti-unit" label={t("unit")} required>
            <Input className="ltr" value={v.numeric_rule?.unit ?? ""} onChange={(e) => set({ numeric_rule: { unit: e.target.value, min: v.numeric_rule?.min ?? "0", max: v.numeric_rule?.max ?? "0" } })} />
          </FormField>
          <FormField id="ti-min" label={t("min")} required>
            <Input type="number" className="ltr" value={v.numeric_rule?.min ?? ""} onChange={(e) => set({ numeric_rule: { unit: v.numeric_rule?.unit ?? "", min: e.target.value, max: v.numeric_rule?.max ?? "0" } })} />
          </FormField>
          <FormField id="ti-max" label={t("max")} required>
            <Input type="number" className="ltr" value={v.numeric_rule?.max ?? ""} onChange={(e) => set({ numeric_rule: { unit: v.numeric_rule?.unit ?? "", min: v.numeric_rule?.min ?? "0", max: e.target.value } })} />
          </FormField>
        </div>
      ) : null}
      {v.item_type === "single_select" ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">{t("options")}</p>
          {opts.map((o, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-4">
              <Input className="ltr" aria-label={t("optionCode")} placeholder={t("optionCode")} value={o.code} onChange={(e) => set({ options: opts.map((p, j) => (j === i ? { ...p, code: e.target.value } : p)) })} />
              <Input aria-label={t("textEn")} placeholder={t("textEn")} value={o.label_en} onChange={(e) => set({ options: opts.map((p, j) => (j === i ? { ...p, label_en: e.target.value } : p)) })} />
              <Input dir="rtl" aria-label={t("textAr")} placeholder={t("textAr")} value={o.label_ar ?? ""} onChange={(e) => set({ options: opts.map((p, j) => (j === i ? { ...p, label_ar: e.target.value } : p)) })} />
              <Select aria-label={t("mapsTo")} value={o.maps_to} onChange={(e) => set({ options: opts.map((p, j) => (j === i ? { ...p, maps_to: e.target.value as S["OptionMapping"] } : p)) })}>
                {OPTION_MAPPINGS.map((m) => (
                  <option key={m} value={m}>
                    {te(`fdMapping.${m}`)}
                  </option>
                ))}
              </Select>
            </div>
          ))}
          {opts.length < 8 ? (
            <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => set({ options: [...opts, { code: `O${opts.length + 1}`, label_en: "", label_ar: "", maps_to: "compliant" }] })}>
              <Plus aria-hidden />
              {t("addOption")}
            </Button>
          ) : null}
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ti-caen" label={t("suggestedCaEn")}>
          <Input maxLength={300} value={v.suggested_ca_en ?? ""} onChange={(e) => set({ suggested_ca_en: e.target.value || null })} />
        </FormField>
        <FormField id="ti-caar" label={t("suggestedCaAr")}>
          <Input dir="rtl" maxLength={300} value={v.suggested_ca_ar ?? ""} onChange={(e) => set({ suggested_ca_ar: e.target.value || null })} />
        </FormField>
        <FormField id="ti-cl" label={t("controlLevel")}>
          <Select value={v.suggested_control_level ?? ""} onChange={(e) => set({ suggested_control_level: (e.target.value || null) as S["ControlLevel"] | null })}>
            <option value="">—</option>
            {CONTROL_LEVELS.map((c) => (
              <option key={c} value={c}>
                {te(`controlLevel.${c}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ti-ref" label={t("reference")}>
          <Input className="ltr" maxLength={80} value={v.reference ?? ""} onChange={(e) => set({ reference: e.target.value || null })} />
        </FormField>
      </div>
    </StepDialog>
  );
}

/* ═════════════ toolbox topic library (§3.10, TBT-1, TBT-2) ═════════════ */

export function TopicsPage() {
  const t = useTranslations("field.topics");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useFieldCaps();
  const bi = useBi();
  const { label, items: refItems } = useFieldRef();
  const s = useSearchState();
  const cat = (s.get("category") ?? "") as S["TopicCategory"] | "";
  const status = (s.get("status") ?? "") as S["VersionStatus"] | "";
  const q = useTopics({ category: cat || null, status: status ? [status] : null }, { enabled: caps.libraryView });
  const [creating, setCreating] = useState(false);
  if (!caps.libraryView) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.author ? (
            <Button onClick={() => setCreating(true)} data-testid="topic-new">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <FieldLibrarySubNav />
      <ListToolbar>
        <SelectFilter id="tp-cat" label={t("category")} value={cat} onChange={(v) => s.set({ category: v })} options={refItems("topic_categories").map((x) => ({ value: x.code as S["TopicCategory"], label: label("topic_categories", x.code) }))} />
        <SelectFilter id="tp-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={VERSION_STATUSES.map((x) => ({ value: x, label: te(`fdVersionStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="topic-table">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("titleCol")}</TH>
              <TH>{t("category")}</TH>
              <TH>{t("languages")}</TH>
              <TH>{t("reviewDue")}</TH>
              <TH>{tc("status")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((x) => (
              <TR key={x.id} data-testid="topic-row" data-code={x.topic_code} data-status={x.status}>
                <TD label={t("code")}>
                  <Link href={`/toolbox-topics/${x.id}`} className="font-medium text-primary hover:underline">
                    <Code>{x.topic_code}</Code> <span className="ltr">v{x.version}</span>
                  </Link>
                </TD>
                <TD label={t("titleCol")}>{bi(x.title_en, x.title_ar)}</TD>
                <TD label={t("category")}>{label("topic_categories", x.category)}</TD>
                <TD label={t("languages")}>
                  <span className="text-xs">{["en", "ar", ...x.translations.map((tr) => tr.language)].map((l) => te(`fdLanguage.${l}` as "fdLanguage.en")).join(" · ")}</span>
                </TD>
                <TD label={t("reviewDue")}>
                  <StackedDate v={x.review_due_on} />
                </TD>
                <TD label={tc("status")}>
                  <VersionStatusBadge status={x.status} overdue={x.review_overdue} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {creating ? <TopicDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

const lines = (s: string) =>
  s
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);

function TopicDialog({ topic, onClose }: { topic?: Topic; onClose: () => void }) {
  const t = useTranslations("field.topics");
  const te = useTranslations("enums");
  const { label, items } = useFieldRef();
  const router = useRouter();
  const refresh = useFieldRefresh();
  const [code, setCode] = useState(topic?.topic_code ?? "TT-");
  const [cat, setCat] = useState<string>(topic?.category ?? "general");
  const [en, setEn] = useState(topic?.title_en ?? "");
  const [ar, setAr] = useState(topic?.title_ar ?? "");
  const [kpEn, setKpEn] = useState((topic?.key_points_en ?? []).join("\n"));
  const [kpAr, setKpAr] = useState((topic?.key_points_ar ?? []).join("\n"));
  const [trs, setTrs] = useState<S["TopicTranslation"][]>(topic?.translations ?? []);
  const [refs, setRefs] = useState<S["LinkedRef"][]>(topic?.linked_refs ?? []);
  const valid = /^TT-\d{3}$/.test(code) && en.trim();
  return (
    <StepDialog
      wide
      title={topic ? t("edit") : t("new")}
      description={t("pointsHint")}
      confirmLabel={topic ? t("save") : t("createDraft")}
      disabled={!valid}
      testId="topic-save"
      onConfirm={async () => {
        const body = { category: cat as S["TopicCategory"], title_en: en.trim(), title_ar: ar.trim(), key_points_en: lines(kpEn), key_points_ar: lines(kpAr), translations: trs.map((x) => ({ ...x, key_points: x.key_points.filter(Boolean) })), linked_refs: refs.filter((r) => r.ref.trim()) };
        if (topic) {
          await unwrap(api.PATCH("/api/v1/toolbox-topics/{topic_id}", { params: { path: { topic_id: topic.id } }, body }));
          await refresh();
        } else {
          const r = await unwrap(api.POST("/api/v1/toolbox-topics", { body: { topic_code: code, ...body } }));
          await refresh();
          router.push(`/toolbox-topics/${r.id}`);
        }
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="tt-code" label={t("code")} required hint={t("codeHint")}>
          <Input className="ltr" maxLength={6} disabled={Boolean(topic)} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} data-testid="tt-code" />
        </FormField>
        <FormField id="tt-cat" label={t("category")} required>
          <Select value={cat} onChange={(e) => setCat(e.target.value)}>
            {items("topic_categories").map((c) => (
              <option key={c.code} value={c.code}>
                {label("topic_categories", c.code)}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      <FormField id="tt-en" label={t("titleEn")} required>
        <Input maxLength={150} value={en} onChange={(e) => setEn(e.target.value)} data-testid="tt-en" />
      </FormField>
      <FormField id="tt-ar" label={t("titleAr")}>
        <Input dir="rtl" maxLength={150} value={ar} onChange={(e) => setAr(e.target.value)} data-testid="tt-ar" />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="tt-kpen" label={t("pointsEn")} hint={t("pointsCount", { n: lines(kpEn).length })}>
          <Textarea rows={6} value={kpEn} onChange={(e) => setKpEn(e.target.value)} data-testid="tt-kpen" />
        </FormField>
        <FormField id="tt-kpar" label={t("pointsAr")} hint={t("pointsCount", { n: lines(kpAr).length })}>
          <Textarea dir="rtl" rows={6} value={kpAr} onChange={(e) => setKpAr(e.target.value)} data-testid="tt-kpar" />
        </FormField>
      </div>
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">{t("translations")}</p>
        {trs.map((tr, i) => (
          <div key={i} className="grid gap-2 rounded-md border p-2 sm:grid-cols-3">
            <Select aria-label={t("language")} value={tr.language} onChange={(e) => setTrs(trs.map((x, j) => (j === i ? { ...x, language: e.target.value as S["WorkerLanguage"] } : x)))}>
              {WORKER_LANGUAGES.filter((l) => l !== "en" && l !== "ar").map((l) => (
                <option key={l} value={l}>
                  {te(`fdLanguage.${l}`)}
                </option>
              ))}
            </Select>
            <Textarea aria-label={t("points")} dir="auto" rows={3} className="sm:col-span-2" value={tr.key_points.join("\n")} onChange={(e) => setTrs(trs.map((x, j) => (j === i ? { ...x, key_points: e.target.value.split("\n") } : x)))} />
            <Input aria-label={t("reviewer")} placeholder={t("reviewer")} className="sm:col-span-2" value={tr.reviewed_by_name_role ?? ""} onChange={(e) => setTrs(trs.map((x, j) => (j === i ? { ...x, reviewed_by_name_role: e.target.value || null } : x)))} />
            <Button type="button" variant="ghost" size="sm" onClick={() => setTrs(trs.filter((_, j) => j !== i))}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setTrs([...trs, { language: "ur", key_points: [], reviewed_by_name_role: null }])}>
          <Plus aria-hidden />
          {t("addTranslation")}
        </Button>
      </div>
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">{t("linked")}</p>
        {refs.map((r, i) => (
          <div key={i} className="flex gap-2">
            <Select aria-label={t("linkKind")} className="w-48" value={r.kind} onChange={(e) => setRefs(refs.map((x, j) => (j === i ? { ...x, kind: e.target.value as S["LinkedRefKind"] } : x)))}>
              {LINKED_REF_KINDS.map((k) => (
                <option key={k} value={k}>
                  {te(`fdLinkedRef.${k}`)}
                </option>
              ))}
            </Select>
            <Input className="ltr" aria-label={t("linkRef")} value={r.ref} onChange={(e) => setRefs(refs.map((x, j) => (j === i ? { ...x, ref: e.target.value } : x)))} />
            <Button type="button" variant="ghost" size="sm" onClick={() => setRefs(refs.filter((_, j) => j !== i))}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setRefs([...refs, { kind: "incident", ref: "" }])}>
          <Plus aria-hidden />
          {t("addLink")}
        </Button>
        <p className="text-xs text-muted-foreground">{t("linkHint")}</p>
      </div>
    </StepDialog>
  );
}

export function TopicPage({ id }: { id: string }) {
  const t = useTranslations("field.topics");
  const te = useTranslations("enums");
  const tn = useTranslations("field.nav");
  const caps = useFieldCaps();
  const { label } = useFieldRef();
  const router = useRouter();
  const refresh = useFieldRefresh();
  const q = useTopic(id);
  const versions = useTopics({ topic_code: q.data?.topic_code ?? "" }, { enabled: Boolean(q.data) });
  const [dialog, setDialog] = useState<"edit" | "publish" | "retire" | "delete" | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const x = q.data;
  const draft = x.status === "draft";
  const hasDraft = (versions.data?.items ?? []).some((v) => v.status === "draft");
  return (
    <div className="mx-auto max-w-4xl">
      <Breadcrumbs items={[{ label: tn("topics"), href: "/toolbox-topics" }, { label: `${x.topic_code} v${x.version}` }]} />
      <Card data-testid="topic-detail" data-status={x.status}>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-sm text-muted-foreground">
              <Code>{x.topic_code}</Code> <span className="ltr">v{x.version}</span> · {label("topic_categories", x.category)}
            </p>
            <CardTitle className="flex flex-wrap items-center gap-2">
              {x.title_en}
              <VersionStatusBadge status={x.status} overdue={x.review_overdue} />
            </CardTitle>
            <p dir="rtl" className="mt-1 text-start text-sm">
              {x.title_ar}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {draft && caps.author ? (
              <Button size="sm" variant="outline" onClick={() => setDialog("edit")} data-testid="topic-edit">
                <Pencil aria-hidden />
                {t("edit")}
              </Button>
            ) : null}
            {draft && caps.publish ? (
              <Button size="sm" onClick={() => setDialog("publish")} data-testid="topic-publish">
                <Send aria-hidden />
                {t("publish")}
              </Button>
            ) : null}
            {x.status === "published" && caps.author && !hasDraft ? (
              <Button
                size="sm"
                variant="outline"
                onClick={async () => {
                  const r = await unwrap(api.POST("/api/v1/toolbox-topics/{topic_id}/new-version", { params: { path: { topic_id: x.id } } }));
                  await refresh();
                  router.push(`/toolbox-topics/${r.id}`);
                }}
                data-testid="topic-new-version"
              >
                <CopyPlus aria-hidden />
                {t("newVersion")}
              </Button>
            ) : null}
            {x.status === "published" && caps.publish ? (
              <Button size="sm" variant="outline" onClick={() => setDialog("retire")} data-testid="topic-retire">
                <Archive aria-hidden />
                {t("retire")}
              </Button>
            ) : null}
            {draft && caps.author ? (
              <Button size="sm" variant="ghost" onClick={() => setDialog("delete")}>
                <Trash2 aria-hidden />
                {t("deleteDraft")}
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {x.review_overdue ? <Alert tone="warning">{t("overdueNote")}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-sm font-medium">{t("pointsEn")}</p>
              <ol className="list-inside list-decimal text-sm" data-testid="kp-en">
                {x.key_points_en.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ol>
            </div>
            <div dir="rtl">
              <p className="mb-1 text-sm font-medium">{t("pointsAr")}</p>
              <ol className="list-inside list-decimal text-sm" data-testid="kp-ar">
                {x.key_points_ar.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ol>
            </div>
          </div>
          {x.translations.map((tr) => (
            <div key={tr.language}>
              <p className="mb-1 text-sm font-medium">
                {te(`fdLanguage.${tr.language}`)}
                {tr.reviewed_by_name_role ? <span className="text-xs font-normal text-muted-foreground"> · {t("reviewedBy", { who: tr.reviewed_by_name_role })}</span> : null}
              </p>
              <ol className="list-inside list-decimal text-sm" dir="auto">
                {tr.key_points.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ol>
            </div>
          ))}
          <FieldList>
            <FieldItem label={t("linked")} wide>
              {x.linked_refs.length
                ? x.linked_refs.map((r) => (
                    <span key={`${r.kind}-${r.ref}`} className="me-3 inline-flex gap-1">
                      {te(`fdLinkedRef.${r.kind}`)} <Code>{r.ref}</Code>
                    </span>
                  ))
                : "—"}
            </FieldItem>
            <FieldItem label={t("reviewDue")}>
              <StackedDate v={x.review_due_on} />
            </FieldItem>
            <FieldItem label={t("published")}>
              <StackedDate v={x.published_at} />
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      {dialog === "edit" ? <TopicDialog topic={x} onClose={() => setDialog(null)} /> : null}
      {dialog === "publish" ? (
        <StepDialog
          title={t("publish")}
          description={t("publishHint")}
          confirmLabel={t("publish")}
          testId="topic-publish-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/toolbox-topics/{topic_id}/transitions", { params: { path: { topic_id: x.id } }, body: { action: "publish" } }));
            await refresh();
          }}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "retire" ? (
        <FieldReasonDialog
          title={t("retire")}
          confirmLabel={t("retire")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/toolbox-topics/{topic_id}/transitions", { params: { path: { topic_id: x.id } }, body: { action: "retire", reason } }))}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "delete" ? (
        <StepDialog
          title={t("deleteDraft")}
          destructive
          confirmLabel={t("deleteDraft")}
          onConfirm={async () => {
            await unwrap(api.DELETE("/api/v1/toolbox-topics/{topic_id}", { params: { path: { topic_id: x.id } } }));
            await refresh();
            router.push("/toolbox-topics");
          }}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}
