"use client";
import { Wand2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { api, unwrap } from "@/lib/api/client";
import { todayInZone } from "@/lib/datetime";

/** D-268: fill daily returns from gate entries / the deployment roster for a date range. */
export function WorkforceAutoFill({ projectId }: { projectId: string }) {
  const t = useTranslations("workforce");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const today = todayInZone();
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await unwrap(
        api.POST("/api/v1/projects/{project_id}/workforce-returns/auto-fill", { params: { path: { project_id: projectId } }, body: { from_date: from, to_date: to } }),
      );
      toast.success(t("autoFillDone", { created: res.created, updated: res.updated, skipped: res.skipped }));
      setOpen(false);
      await qc.invalidateQueries({ queryKey: ["workforce-returns"] });
      await qc.invalidateQueries({ queryKey: ["kpi"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} data-testid="auto-fill">
        <Wand2 aria-hidden />
        {t("autoFill")}
      </Button>
      <Dialog open={open} onOpenChange={(v) => !busy && setOpen(v)}>
        {open ? (
          <DialogContent closeLabel={tc("close")}>
            <DialogHeader>
              <DialogTitle>{t("autoFillTitle")}</DialogTitle>
              <DialogDescription>{t("autoFillBody")}</DialogDescription>
            </DialogHeader>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField id="af-from" label={t("autoFillFrom")} required>
                <Input type="date" max={today} value={from} onChange={(e) => setFrom(e.target.value)} />
              </FormField>
              <FormField id="af-to" label={t("autoFillTo")} required>
                <Input type="date" max={today} value={to} onChange={(e) => setTo(e.target.value)} />
              </FormField>
            </div>
            <MutationError error={error} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
                {tc("cancel")}
              </Button>
              <Button onClick={() => void run()} disabled={busy || !from || !to || to < from} data-testid="auto-fill-run">
                {busy ? tc("saving") : t("autoFillRun")}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </>
  );
}
