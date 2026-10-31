"use client";
import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { api, unwrap } from "@/lib/api/client";
import { useFormatters } from "@/lib/use-formatters";
import { qError, type S } from "../q0/common";

export type { S };

/** Tones of the Q2 statuses and verdicts (labels come from the server reference, D-327). */
export const Q2_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  draft: "neutral",
  submitted: "info",
  approved: "success",
  approved_as_noted: "success",
  revise_resubmit: "warning",
  rejected: "danger",
  superseded: "neutral",
  withdrawn: "neutral",
  decided: "success",
  cancelled: "neutral",
  quarantined: "warning",
  released: "success",
  returned: "neutral",
  scrapped: "neutral",
  requested: "neutral",
  sampled: "info",
  at_lab: "info",
  results_entered: "warning",
  verified: "success",
  amended: "warning",
  voided: "neutral",
  pass: "success",
  fail: "danger",
  indicative: "info",
  pending: "neutral",
  planned: "neutral",
  started: "info",
  closed: "success",
  welded: "neutral",
  visual_accepted: "info",
  visual_rejected: "danger",
  ndt_pending: "warning",
  accepted: "success",
  repaired_r1: "warning",
  repaired_r2: "warning",
  cut_out: "danger",
  active: "success",
  lapsed: "danger",
  expired: "danger",
  revoked: "neutral",
  open: "warning",
  met: "success",
  expiring: "warning",
  not_met: "danger",
  not_applicable: "neutral",
};

export function Q2Badge({ label, value, testId }: { label: string; value: string | null | undefined; testId?: string }) {
  if (!value) return <>—</>;
  return (
    <Badge tone={Q2_TONE[value] ?? "neutral"} data-status={value} data-testid={testId}>
      {label}
    </Badge>
  );
}

/** Sign-offs of a record (append-only, Q-RPM-05). */
export function Signoffs({ recordType, recordId }: { recordType: S["QRecordType"]; recordId: string }) {
  const t = useTranslations("quality.q2");
  const ar = useLocale() === "ar";
  const q = useQuery({
    queryKey: ["q-signoffs", recordType, recordId],
    queryFn: () => unwrap(api.GET("/api/v1/quality/signoffs", { params: { query: { record_type: recordType, record_id: recordId } } })),
    retry: false,
  });
  const { dateTime } = useFormatters(null);
  const rows = q.data ?? [];
  return (
    <Card className="mb-4" data-testid="q2-signoffs">
      <CardContent className="p-4">
        <h3 className="mb-2 text-sm font-semibold">{t("signoffs")}</h3>
        {rows.length ? (
          <ul className="flex flex-col gap-1 text-sm">
            {rows.map((s) => (
              <li key={s.id} data-testid="q2-signoff" data-step={s.step} data-decision={s.decision}>
                <span className="font-medium">{s.step}</span> · <span className="ltr">{s.decision}</span> · {ar ? s.text_ar : s.text_en} · {dateTime(s.signed_at)}
                {s.comment ? <span className="block text-muted-foreground" dir="auto">{s.comment}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noSignoffs")}</p>
        )}
      </CardContent>
    </Card>
  );
}

/** A decision with options and a comment (comment required for some options). */
export function DecisionDialog({
  open,
  onOpenChange,
  title,
  options,
  needsComment,
  extra,
  onSubmit,
  testId,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  options: { value: string; label: string }[];
  needsComment: (v: string) => boolean;
  extra?: ReactNode;
  onSubmit: (decision: string, comment: string) => Promise<unknown>;
  testId?: string;
}) {
  const t = useTranslations("quality.q2");
  const tc = useTranslations("common");
  const [decision, setDecision] = useState(options[0]?.value ?? "");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const short = needsComment(decision) && comment.trim().length < 20;
  async function go() {
    setBusy(true);
    setError(null);
    try {
      await onSubmit(decision, comment.trim());
      setComment("");
      onOpenChange(false);
    } catch (e) {
      setError(qError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={tc("close")} data-testid={testId}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{t("decisionHint")}</DialogDescription>
        </DialogHeader>
        <MutationError error={error} />
        <FormField id="q2-decision" label={t("decision")}>
          <Select value={decision} onChange={(e) => setDecision(e.target.value)} data-testid="q2-decision">
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </FormField>
        {extra}
        <FormField id="q2-comment" label={t("comment")} hint={needsComment(decision) ? t("min20") : undefined}>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3} data-testid="q2-comment" />
        </FormField>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void go()} disabled={busy || short} data-testid="q2-decision-confirm">
            {t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export const clean = (o: Record<string, string>) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== ""));
