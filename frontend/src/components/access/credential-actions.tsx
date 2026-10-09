"use client";
import { useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { MANUAL_REASONS } from "@/lib/access-enums";
import { ACCESS_PREFIXES, ak, useCredential } from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { DEFAULT_TIME_ZONE, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { StackedDate } from "@/components/medical/common";
import { DaysLeft } from "./common";

type Kind = Exclude<Schemas["CredentialKind"], "wap" | "worker">;
type Action = "suspend" | "confirm" | "reinstate" | "revoke" | "return" | "loss" | "authority";

const NEEDS_REASON_CODE: Action[] = ["suspend", "reinstate", "revoke", "loss"];
const NEEDS_TEXT: Action[] = ["suspend", "confirm", "reinstate", "revoke", "loss"];

/**
 * Shared lifecycle panel for inductions, airport passes, ADPs, AVPs and access cards (§5.9, DECISIONS 31):
 * state, open suspensions, actions allowed for the role, and the event log. The server enforces every rule.
 */
export function CredentialPanel({ kind, id, projectId, onChanged }: { kind: Kind; id: string; projectId: string; onChanged?: (s: Schemas["CredentialState"]) => void }) {
  const t = useTranslations("credentials");
  const te = useTranslations("enums");
  const me = useMeData();
  const name = useLocalizedName();
  const { date, dateTime } = useFormatters(projectId);
  const q = useCredential(kind, id);
  const [action, setAction] = useState<Action | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState rows={2} />;
  const s = q.data;
  const confirmCap = canWrite(me, "credential.suspend_confirm", projectId);
  const raiseCap = canWrite(me, "credential.suspend_raise", projectId);
  const custodyCap = canWrite(me, "credential.custody", projectId);
  const revokeCap = kind === "induction" ? canWrite(me, "induction.suspend_revoke", projectId) : confirmCap;
  const live = kind === "induction" ? s.induction_status === "valid" || s.induction_status === "suspended" : kind === "access_card" ? s.token_status === "active" : s.validity_status === "active" || s.validity_status === "suspended";
  const active = kind === "induction" ? s.induction_status === "valid" : kind === "access_card" ? s.token_status === "active" : s.validity_status === "active";
  const suspended = kind === "induction" ? s.induction_status === "suspended" : s.validity_status === "suspended";
  const raised = s.open_suspensions.some((x) => x.state === "raised");
  const manualOpen = s.open_suspensions.some((x) => x.state !== "system");
  const actions: { a: Action; destructive?: boolean; show: boolean }[] = [
    { a: "suspend", show: kind !== "access_card" && active && (raiseCap || confirmCap || (kind === "induction" && revokeCap)) },
    { a: "confirm", show: raised && (confirmCap || (kind === "induction" && revokeCap)) },
    { a: "reinstate", show: suspended && manualOpen && (confirmCap || (kind === "induction" && revokeCap)) },
    { a: "revoke", destructive: true, show: kind !== "access_card" && live && revokeCap },
    { a: "return", show: s.custody_status === "return_due" && custodyCap },
    { a: "loss", destructive: true, show: (s.custody_status === "held" || s.custody_status === "return_due" || (kind === "access_card" && s.token_status === "active")) && custodyCap },
    { a: "authority", show: Boolean(s.lost_reported_at) && !s.authority_notified_at && custodyCap },
  ];
  const status = kind === "induction" ? s.induction_status : kind === "access_card" ? s.token_status : s.validity_status;
  const statusLabel =
    kind === "induction" && s.induction_status
      ? te(`inductionStatus.${s.induction_status}`)
      : kind === "access_card" && s.token_status
        ? te(`qrTokenStatus.${s.token_status}`)
        : s.validity_status
          ? te(`validityStatus.${s.validity_status}`)
          : "—";
  const days = s.effective_valid_until ? Math.round((Date.parse(`${s.effective_valid_until}T00:00:00Z`) - Date.parse(`${new Date().toISOString().slice(0, 10)}T00:00:00Z`)) / 86_400_000) : null;
  return (
    <Card data-testid="credential-panel" data-kind={kind} data-status={status ?? ""}>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("title")}</CardTitle>
        {status ? <StatusBadge status={status} label={statusLabel} /> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
          {s.effective_valid_until ? (
            <div>
              <dt className="text-xs text-muted-foreground">{t("effectiveUntil")}</dt>
              <dd className="flex flex-wrap items-center gap-2">
                <StackedDate v={s.effective_valid_until} projectId={projectId} />
                {active ? <DaysLeft days={days} /> : null}
              </dd>
            </div>
          ) : null}
          {s.limiting_factor ? (
            <div>
              <dt className="text-xs text-muted-foreground">{t("limitingFactor")}</dt>
              <dd data-testid="limiting-factor" data-factor={s.limiting_factor}>
                {te(`limitingFactor.${s.limiting_factor}`)}
              </dd>
            </div>
          ) : null}
          {s.custody_status ? (
            <div>
              <dt className="text-xs text-muted-foreground">{t("custody")}</dt>
              <dd className="flex flex-wrap items-center gap-2" data-testid="custody-status" data-custody={s.custody_status}>
                <StatusBadge status={s.custody_status} label={te(`custodyStatus.${s.custody_status}`)} />
                {s.return_due_on ? <span className="text-xs text-muted-foreground">{t("returnDueOn", { date: date(s.return_due_on) })}</span> : null}
              </dd>
            </div>
          ) : null}
          {s.returned_at ? (
            <div>
              <dt className="text-xs text-muted-foreground">{t("returnedAt")}</dt>
              <dd>
                {dateTime(s.returned_at)}
                {s.received_by ? ` · ${name(s.received_by.full_name_en, s.received_by.full_name_ar)}` : ""}
              </dd>
            </div>
          ) : null}
          {s.lost_reported_at ? (
            <div>
              <dt className="text-xs text-muted-foreground">{t("lostReportedAt")}</dt>
              <dd>{dateTime(s.lost_reported_at)}</dd>
            </div>
          ) : null}
          {s.lost_reported_at ? (
            <div>
              <dt className="text-xs text-muted-foreground">{t("authorityNotifiedAt")}</dt>
              <dd data-testid="authority-notified">{s.authority_notified_at ? dateTime(s.authority_notified_at) : <span className="inline-flex items-center gap-1 font-medium text-warning">
                    <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
                    {t("authorityNotYet")}
                  </span>}</dd>
            </div>
          ) : null}
        </dl>
        {s.open_suspensions.length > 0 ? (
          <ul className="flex flex-col gap-2" data-testid="open-suspensions">
            {s.open_suspensions.map((x, i) => (
              <li key={i} className="rounded-md border border-warning/40 bg-warning-bg p-2" data-state={x.state} data-reason={x.reason_code}>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={x.state} label={te(`suspensionState.${x.state}`)} />
                  <span className="font-medium">{te(`credentialReason.${x.reason_code}`)}</span>
                </div>
                {x.reason_text ? <p className="mt-1 whitespace-pre-wrap">{x.reason_text}</p> : null}
                <p className="mt-1 text-xs text-muted-foreground">
                  {dateTime(x.raised_at)}
                  {x.raised_by ? ` · ${name(x.raised_by.full_name_en, x.raised_by.full_name_ar)}` : ` · ${t("system")}`}
                  {x.expires_at ? ` · ${t("liftsAt", { time: dateTime(x.expires_at) })}` : ""}
                  {x.suspension_end ? ` · ${t("suspensionEnd", { date: date(x.suspension_end) })}` : ""}
                </p>
                {x.state === "system" ? <p className="mt-1 text-xs">{t("systemHint")}</p> : null}
              </li>
            ))}
          </ul>
        ) : null}
        {actions.some((x) => x.show) ? (
          // Everyday steps first; Revoke / Report loss at the end of the card, outlined and set apart (record-actions pattern).
          <div className="flex flex-col gap-2" role="group" aria-label={t("actions")}>
            {actions.some((x) => x.show && !x.destructive) ? (
              <div className="flex flex-wrap gap-2">
                {actions
                  .filter((x) => x.show && !x.destructive)
                  .map((x) => (
                    <Button key={x.a} size="sm" variant="outline" onClick={() => setAction(x.a)} data-testid={`cred-${x.a}`}>
                      {x.a === "suspend" ? (confirmCap || kind === "induction" ? t("action.suspend") : t("action.raise")) : t(`action.${x.a}`)}
                    </Button>
                  ))}
              </div>
            ) : null}
            {actions.some((x) => x.show && x.destructive) ? (
              <div className="flex flex-wrap justify-end gap-2 border-t pt-2">
                {actions
                  .filter((x) => x.show && x.destructive)
                  .map((x) => (
                    <Button key={x.a} size="sm" variant="destructive-outline" onClick={() => setAction(x.a)} data-testid={`cred-${x.a}`}>
                      {t(`action.${x.a}`)}
                    </Button>
                  ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {s.events.length > 0 ? (
          <details className="text-sm">
            <summary className="cursor-pointer py-1 font-medium">{t("events", { count: s.events.length })}</summary>
            <ol className="mt-2 flex flex-col gap-2 border-s ps-3" data-testid="credential-events">
              {s.events.map((ev) => (
                <li key={ev.id}>
                  <p className="font-medium">
                    {te(`credentialAction.${ev.action}`)} · <span className="font-normal">{te(`credentialReason.${ev.reason_code}`)}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {dateTime(ev.occurred_at)} · {ev.actor ? name(ev.actor.full_name_en, ev.actor.full_name_ar) : t("system")}
                  </p>
                  {ev.reason_text ? <p className="text-xs whitespace-pre-wrap">{ev.reason_text}</p> : null}
                </li>
              ))}
            </ol>
          </details>
        ) : null}
      </CardContent>
      {action ? <ActionDialog kind={kind} id={id} action={action} onClose={() => setAction(null)} onDone={onChanged} /> : null}
    </Card>
  );
}

function ActionDialog({ kind, id, action, onClose, onDone }: { kind: Kind; id: string; action: Action; onClose: () => void; onDone?: (s: Schemas["CredentialState"]) => void }) {
  const t = useTranslations("credentials");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const now = utcToZonedInput(new Date().toISOString(), DEFAULT_TIME_ZONE);
  const [code, setCode] = useState<Schemas["CredentialReason"] | "">(action === "loss" ? "lost_stolen" : "");
  const [text, setText] = useState("");
  const [when, setWhen] = useState(now);
  const [notified, setNotified] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const needCode = NEEDS_REASON_CODE.includes(action);
  const needText = NEEDS_TEXT.includes(action);
  const ok = (!needCode || code !== "") && (!needText || text.trim().length >= 10) && (action !== "authority" || when !== "");

  async function submit() {
    setBusy(true);
    setError(null);
    const path = { params: { path: { kind, credential_id: id } } };
    const reason = { reason_code: code as Schemas["CredentialReason"], reason_text: text.trim() };
    try {
      let s: Schemas["CredentialState"];
      if (action === "suspend") s = await unwrap(api.POST("/api/v1/credentials/{kind}/{credential_id}/suspend", { ...path, body: reason }));
      else if (action === "confirm") s = await unwrap(api.POST("/api/v1/credentials/{kind}/{credential_id}/confirm-suspension", { ...path, body: { reason_text: text.trim() } }));
      else if (action === "reinstate") s = await unwrap(api.POST("/api/v1/credentials/{kind}/{credential_id}/reinstate", { ...path, body: reason }));
      else if (action === "revoke") s = await unwrap(api.POST("/api/v1/credentials/{kind}/{credential_id}/revoke", { ...path, body: reason }));
      else if (action === "return") s = await unwrap(api.POST("/api/v1/credentials/{kind}/{credential_id}/return", { ...path, body: { returned_at: zonedInputToUtc(when), notes: notes.trim() || null } }));
      else if (action === "loss")
        s = await unwrap(
          api.POST("/api/v1/credentials/{kind}/{credential_id}/loss", {
            ...path,
            body: { ...reason, lost_reported_at: zonedInputToUtc(when), authority_notified_at: notified ? zonedInputToUtc(notified) : null },
          }),
        );
      else s = await unwrap(api.POST("/api/v1/credentials/{kind}/{credential_id}/authority-notified", { ...path, body: { authority_notified_at: zonedInputToUtc(when) } }));
      qc.setQueryData(ak.credential(kind, id), s);
      await Promise.all(ACCESS_PREFIXES.map((p) => qc.invalidateQueries({ queryKey: [p] })));
      toast.success(t(`done.${action}`));
      onDone?.(s);
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t(`action.${action}`)}</DialogTitle>
          <DialogDescription>{t(`help.${action}`)}</DialogDescription>
        </DialogHeader>
        {needCode ? (
          <FormField id="cred-reason-code" label={t("reasonCode")} required>
            <Select value={code} onChange={(e) => setCode(e.target.value as Schemas["CredentialReason"] | "")}>
              <option value="">{tc("select")}</option>
              {(action === "loss" ? (["lost_stolen", "fraud_misuse", "other"] as const) : MANUAL_REASONS).map((r) => (
                <option key={r} value={r}>
                  {te(`credentialReason.${r}`)}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        {action === "return" || action === "loss" || action === "authority" ? (
          <FormField id="cred-when" label={action === "return" ? t("returnedAt") : action === "loss" ? t("lostReportedAt") : t("authorityNotifiedAt")} required>
            <Input type="datetime-local" value={when} max={now} onChange={(e) => setWhen(e.target.value)} />
          </FormField>
        ) : null}
        {action === "loss" ? (
          <FormField id="cred-notified" label={t("authorityNotifiedOptional")}>
            <Input type="datetime-local" value={notified} max={now} onChange={(e) => setNotified(e.target.value)} />
          </FormField>
        ) : null}
        {needText ? (
          <FormField id="cred-reason-text" label={tc("reason")} required hint={t("min10")}>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={500} />
          </FormField>
        ) : null}
        {action === "return" ? (
          <FormField id="cred-notes" label={t("notes")}>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
          </FormField>
        ) : null}
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant={action === "revoke" || action === "loss" ? "destructive" : "default"} onClick={() => void submit()} disabled={!ok || busy} data-testid="cred-confirm">
            {busy ? tc("saving") : t(`action.${action}`)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
