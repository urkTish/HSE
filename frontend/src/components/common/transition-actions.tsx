"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Alert } from "@/components/ui/alert";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";

export interface TransitionOption<S extends string> {
  to: S;
  /** Button label; defaults to "Set to {status}". */
  label?: string;
  reasonRequired?: boolean;
  destructive?: boolean;
  warning?: string;
}

/** One button per allowed transition; each opens a confirm dialog with a reason field. */
export function TransitionActions<S extends string>({
  current,
  options,
  statusLabel,
  onTransition,
}: {
  current: S;
  options: TransitionOption<S>[];
  statusLabel: (s: S) => string;
  onTransition: (to: S, reason: string | null) => Promise<unknown>;
}) {
  const t = useTranslations("transitions");
  const tc = useTranslations("common");
  const [open, setOpen] = useState<TransitionOption<S> | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);

  if (options.length === 0) return null;

  function start(o: TransitionOption<S>) {
    setOpen(o);
    setReason("");
    setError(null);
    setReasonError(undefined);
  }

  async function submit() {
    if (!open) return;
    if (open.reasonRequired && !reason.trim()) {
      setReasonError(t("reasonRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onTransition(open.to, reason.trim() || null);
      toast.success(t("done", { status: statusLabel(open.to) }));
      setOpen(null);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* Destructive moves (close, archive, blacklist, deactivate) last, outlined and set apart from the everyday ones. */}
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("changeStatus")}>
        {[...options.filter((o) => !o.destructive), ...options.filter((o) => o.destructive)].map((o, i, all) => (
          <Button
            key={o.to}
            variant={o.destructive ? "destructive-outline" : "outline"}
            size="sm"
            className={o.destructive && i > 0 && !all[i - 1].destructive ? "sm:ms-3" : undefined}
            onClick={() => start(o)}
            data-testid={`transition-${o.to}`}
          >
            {o.label ?? t("moveTo", { status: statusLabel(o.to) })}
          </Button>
        ))}
      </div>
      <Dialog open={open !== null} onOpenChange={(v) => !v && setOpen(null)}>
        {open ? (
          <DialogContent closeLabel={tc("close")}>
            <DialogHeader>
              <DialogTitle>{t("dialogTitle", { status: statusLabel(open.to) })}</DialogTitle>
              <DialogDescription>{t("dialogBody", { from: statusLabel(current) })}</DialogDescription>
            </DialogHeader>
            {open.warning ? <Alert tone="warning">{open.warning}</Alert> : null}
            <FormField
              id="transition-reason"
              label={open.reasonRequired ? tc("reason") : t("reasonOptional")}
              required={open.reasonRequired}
              error={reasonError}
              hint={tc("pdplHint")}
            >
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} />
            </FormField>
            <MutationError error={error} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(null)}>
                {tc("cancel")}
              </Button>
              <Button variant={open.destructive ? "destructive" : "default"} onClick={submit} disabled={busy} data-testid="transition-confirm">
                {busy ? tc("saving") : t("submit")}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </>
  );
}
