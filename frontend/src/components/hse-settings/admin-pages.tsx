"use client";
import { Check, Pencil, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ListToolbar } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { HseSettingsPage } from "@/components/hse-settings/hse-settings";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useAiLogs, useReferenceLists } from "@/lib/api/hse";
import { useCurrentProject } from "@/lib/current-project";
import { ARABIC_SCRIPT } from "@/lib/forms";
import { useErrorMessage, useLocalizedName } from "@/lib/i18n-helpers";
import { can } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";

export function HseSettingsRoute() {
  return <ProjectGate>{(p) => <HseSettingsPage project={p} />}</ProjectGate>;
}

export function ReferenceListsPage() {
  const t = useTranslations("refLists");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const me = useMeData();
  const qc = useQueryClient();
  const msg = useErrorMessage();
  const q = useReferenceLists();
  const s = useSearchState();
  const editable = can(me, "hse_settings.edit");
  const lists = q.data?.lists ?? [];
  const current = (s.get("list") ?? lists[0]?.name ?? "severity") as Schemas["ReferenceList"];
  const list = lists.find((l) => l.name === current);
  const [editing, setEditing] = useState<{ code: string; en: string; ar: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!editing) return;
    if (!editing.en.trim() || !ARABIC_SCRIPT.test(editing.ar)) {
      toast.error(tv("arabicRequired"));
      return;
    }
    setBusy(true);
    try {
      await unwrap(
        api.PATCH("/api/v1/reference-lists/{list_name}/{code}", {
          params: { path: { list_name: current, code: editing.code } },
          body: { label_en: editing.en.trim(), label_ar: editing.ar.trim() },
        }),
      );
      await qc.invalidateQueries({ queryKey: hk.refLists });
      toast.success(tc("saved"));
      setEditing(null);
    } catch (e) {
      toast.error(msg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ListToolbar>
        <div className="flex flex-col gap-1.5 sm:w-64">
          <Label htmlFor="rl-list">{t("list")}</Label>
          <Select id="rl-list" value={current} onChange={(e) => s.set({ list: e.target.value })} data-testid="ref-list-select">
            {lists.map((l) => (
              <option key={l.name} value={l.name}>
                {t(`names.${l.name}`)}
              </option>
            ))}
          </Select>
        </div>
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !list || list.items.length === 0 ? (
        <EmptyState />
      ) : (
        <Table data-testid="ref-items">
          <THead>
            <TR>
              <TH>{t("code")}</TH>
              <TH>{t("labelEn")}</TH>
              <TH>{t("labelAr")}</TH>
              <TH>{t("group")}</TH>
              {editable ? <TH>{tc("actions")}</TH> : null}
            </TR>
          </THead>
          <TBody>
            {[...list.items]
              .sort((a, b) => a.sort_order - b.sort_order)
              .map((i) => (
                <TR key={i.code} data-testid="ref-row" data-code={i.code}>
                  <TD label={t("code")}>
                    <span className="ltr font-mono text-xs">{i.code}</span>
                  </TD>
                  <TD label={t("labelEn")}>
                    {editing?.code === i.code ? <Input aria-label={t("labelEn")} value={editing.en} onChange={(e) => setEditing({ ...editing, en: e.target.value })} maxLength={120} /> : i.label_en}
                  </TD>
                  <TD label={t("labelAr")}>
                    {editing?.code === i.code ? (
                      <Input aria-label={t("labelAr")} dir="rtl" value={editing.ar} onChange={(e) => setEditing({ ...editing, ar: e.target.value })} maxLength={120} />
                    ) : (
                      <span dir="rtl">{i.label_ar}</span>
                    )}
                  </TD>
                  <TD label={t("group")}>{i.group ?? "—"}</TD>
                  {editable ? (
                    <TD label={tc("actions")}>
                      {editing?.code === i.code ? (
                        <span className="inline-flex gap-1">
                          <Button size="sm" onClick={() => void save()} disabled={busy} aria-label={tc("save")}>
                            <Check aria-hidden />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditing(null)} aria-label={tc("cancel")}>
                            <X aria-hidden />
                          </Button>
                        </span>
                      ) : (
                        <Button size="sm" variant="ghost" onClick={() => setEditing({ code: i.code, en: i.label_en, ar: i.label_ar })} aria-label={`${tc("edit")} ${i.code}`}>
                          <Pencil aria-hidden />
                        </Button>
                      )}
                    </TD>
                  ) : null}
                </TR>
              ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

export function AiLogsPage() {
  const t = useTranslations("aiLogs");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const name = useLocalizedName();
  const { projectId } = useCurrentProject();
  const { dateTime } = useFormatters(projectId);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const failedOnly = s.getBool("grounding_failed") ?? false;
  const q = useAiLogs({ grounding_failed: failedOnly || null, date_from: s.get("date_from") || null, date_to: s.get("date_to") || null, page, page_size: 50 });
  if (!me.is_hse_manager) return <Alert tone="info">{tc("noAccess")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ListToolbar>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="al-from">{tc("dateFrom")}</Label>
          <Input id="al-from" type="date" value={s.get("date_from") ?? ""} onChange={(e) => s.set({ date_from: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5 lg:w-40">
          <Label htmlFor="al-to">{tc("dateTo")}</Label>
          <Input id="al-to" type="date" value={s.get("date_to") ?? ""} onChange={(e) => s.set({ date_to: e.target.value })} />
        </div>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <Checkbox checked={failedOnly} onChange={(e) => s.set({ grounding_failed: e.target.checked ? "true" : null })} />
          {t("groundingFailedOnly")}
        </label>
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <Table data-testid="ai-logs-table">
            <THead>
              <TR>
                <TH>{t("fields.when")}</TH>
                <TH>{t("fields.user")}</TH>
                <TH>{t("fields.kind")}</TH>
                <TH>{t("fields.question")}</TH>
                <TH>{t("fields.tools")}</TH>
                <TH>{t("fields.grounding")}</TH>
                <TH className="text-end">{t("fields.tokens")}</TH>
                <TH className="text-end">{t("fields.latency")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((l) => (
                <TR key={l.id} data-testid="ai-log-row">
                  <TD label={t("fields.when")}>{dateTime(l.created_at)}</TD>
                  <TD label={t("fields.user")}>
                    {name(l.user.full_name_en, l.user.full_name_ar)}
                    {l.project_code ? <span className="ltr block text-xs text-muted-foreground">{l.project_code}</span> : null}
                  </TD>
                  <TD label={t("fields.kind")}>{t(`kind.${l.kind}`)}</TD>
                  <TD label={t("fields.question")}>
                    <span className="line-clamp-3 max-w-md" dir="auto">
                      {l.question_masked ?? "—"}
                    </span>
                    {l.error_code ? <span className="ltr block text-xs text-destructive">{l.error_code}</span> : null}
                  </TD>
                  <TD label={t("fields.tools")}>
                    <span className="ltr text-xs">{l.tool_calls.map((c) => c.name).join(", ") || "—"}</span>
                  </TD>
                  <TD label={t("fields.grounding")}>
                    <StatusBadge status={l.grounding === "failed" ? "error" : l.grounding === "not_applicable" ? "unplanned" : "ok"} label={te(`grounding.${l.grounding}`)} />
                  </TD>
                  <TD label={t("fields.tokens")} className="text-end tabular-nums">
                    {l.input_tokens ?? "—"} / {l.output_tokens ?? "—"}
                  </TD>
                  <TD label={t("fields.latency")} className="text-end tabular-nums">
                    {l.latency_ms !== null ? `${(l.latency_ms / 1000).toLocaleString(locale === "ar" ? "ar-SA-u-nu-latn" : "en-GB", { maximumFractionDigits: 1 })} s` : "—"}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      )}
    </div>
  );
}
