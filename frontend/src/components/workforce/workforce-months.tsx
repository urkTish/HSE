"use client";
import { Lock, LockOpen } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useWorkforceMonths } from "@/lib/api/hse";
import { useDisplay, groupDecimal } from "@/lib/digits";
import { todayInZone } from "@/lib/datetime";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";

export function monthLabel(month: string, locale: string): string {
  const [y, m] = month.split("-").map(Number);
  if (!y || !m) return month;
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, 15)),
  );
}

export function WorkforceMonths({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("workforce");
  const tn = useTranslations("nav");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const show = useDisplay(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const thisYear = Number(todayInZone().slice(0, 4));
  const [year, setYear] = useState(thisYear);
  const q = useWorkforceMonths(project.id, year);
  const [dialog, setDialog] = useState<{ month: string; kind: "lock" | "unlock" } | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string>();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const canLock = canWrite(me, "workforce.lock", project.id);
  const canUnlock = canWrite(me, "workforce.unlock", project.id);
  const startYear = Number(project.start_date.slice(0, 4));
  const years = Array.from({ length: Math.max(1, thisYear - startYear + 1) }, (_, i) => thisYear - i);

  async function submit() {
    if (!dialog) return;
    if (dialog.kind === "unlock" && !reason.trim()) {
      setReasonError(tc("reason"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (dialog.kind === "lock") {
        await unwrap(api.POST("/api/v1/projects/{project_id}/workforce-months/{month}/lock", { params: { path: { project_id: project.id, month: dialog.month } }, body: { reason: reason.trim() || null } }));
      } else {
        await unwrap(api.POST("/api/v1/projects/{project_id}/workforce-months/{month}/unlock", { params: { path: { project_id: project.id, month: dialog.month } }, body: { reason: reason.trim() } }));
      }
      toast.success(dialog.kind === "lock" ? t("locked") : t("unlocked"));
      setDialog(null);
      await qc.invalidateQueries({ queryKey: ["workforce-months"] });
      await qc.invalidateQueries({ queryKey: ["workforce-returns"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("workforce"), href: "/workforce" }, { label: t("monthsTitle") }]} />
      <PageHeader title={t("monthsTitle")} description={t("monthsSubtitle")} />
      <div className="mb-4 flex flex-col gap-1.5 sm:w-40">
        <Label htmlFor="months-year">{tc("year")}</Label>
        <Select id="months-year" value={String(year)} onChange={(e) => setYear(Number(e.target.value))}>
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </Select>
      </div>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (q.data?.items.length ?? 0) === 0 ? (
        <EmptyState />
      ) : (
        <Table data-testid="months-table">
          <THead>
            <TR>
              <TH>{t("monthCols.month")}</TH>
              <TH>{t("monthCols.status")}</TH>
              <TH className="text-end">{t("monthCols.manHours")}</TH>
              <TH>{t("monthCols.rows")}</TH>
              <TH>{t("monthCols.autoLock")}</TH>
              <TH>{t("monthCols.lockedBy")}</TH>
              <TH>{tc("actions")}</TH>
            </TR>
          </THead>
          <TBody>
            {q.data?.items.map((m) => (
              <TR key={m.month} data-testid="month-row" data-month={m.month}>
                <TD label={t("monthCols.month")}>
                  <span className="font-medium">{monthLabel(m.month, locale)}</span>
                </TD>
                <TD label={t("monthCols.status")}>
                  <span className="inline-flex flex-wrap gap-1">
                    <StatusBadge status={m.status === "locked" ? "month_locked" : "month_open"} label={te(`monthLock.${m.status}`)} />
                    {m.restated ? <Badge tone="warning">{t("restatedBadge")}</Badge> : null}
                  </span>
                </TD>
                <TD label={t("monthCols.manHours")} className="text-end tabular-nums">
                  {show(groupDecimal(m.man_hours))}
                </TD>
                <TD label={t("monthCols.rows")}>
                  <span className="text-xs">
                    {Object.entries(m.rows_by_status)
                      .map(([k, v]) => `${te(`workforceStatus.${k as Schemas["WorkforceStatus"]}`)} ${show(v)}`)
                      .join(" · ") || "—"}
                  </span>
                </TD>
                <TD label={t("monthCols.autoLock")}>{date(m.auto_lock_date)}</TD>
                <TD label={t("monthCols.lockedBy")}>{m.locked_by ? `${name(m.locked_by.full_name_en, m.locked_by.full_name_ar)} · ${dateTime(m.locked_at)}` : "—"}</TD>
                <TD label={tc("actions")}>
                  {m.status === "open" && canLock ? (
                    <Button size="sm" variant="outline" onClick={() => { setDialog({ month: m.month, kind: "lock" }); setReason(""); setError(null); }} data-testid={`lock-${m.month}`}>
                      <Lock aria-hidden />
                      {t("lock")}
                    </Button>
                  ) : null}
                  {m.status === "locked" && canUnlock ? (
                    <Button size="sm" variant="outline" onClick={() => { setDialog({ month: m.month, kind: "unlock" }); setReason(""); setError(null); }} data-testid={`unlock-${m.month}`}>
                      <LockOpen aria-hidden />
                      {t("unlock")}
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <Dialog open={dialog !== null} onOpenChange={(v) => !v && setDialog(null)}>
        {dialog ? (
          <DialogContent closeLabel={tc("close")}>
            <DialogHeader>
              <DialogTitle>{dialog.kind === "lock" ? t("lockTitle", { month: monthLabel(dialog.month, locale) }) : t("unlockTitle", { month: monthLabel(dialog.month, locale) })}</DialogTitle>
              <DialogDescription>{dialog.kind === "lock" ? t("lockBody") : t("unlockBody")}</DialogDescription>
            </DialogHeader>
            <FormField id="month-reason" label={tc("reason")} required={dialog.kind === "unlock"} error={reasonError}>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
            </FormField>
            <MutationError error={error} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialog(null)}>
                {tc("cancel")}
              </Button>
              <Button onClick={() => void submit()} disabled={busy} data-testid="month-confirm">
                {dialog.kind === "lock" ? t("lock") : t("unlock")}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  );
}
