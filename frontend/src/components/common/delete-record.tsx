"use client";
import { Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";

/** D-271: the platform administrator deletes any record; it stays traceable under Deleted items. */
export function DeleteRecordButton({
  entityType,
  entityId,
  onDeleted,
  size = "sm",
}: {
  entityType: string;
  entityId: string;
  /** Defaults to going back to the previous page. */
  onDeleted?: () => void;
  size?: "sm" | "icon";
}) {
  const t = useTranslations("deleteRecord");
  const tc = useTranslations("common");
  const me = useMeData();
  const qc = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!me.can_delete_projects) return null;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/admin/records/delete", { body: { entity_type: entityType, entity_id: entityId, reason: reason.trim() } }));
      toast.success(t("done"));
      setOpen(false);
      await qc.invalidateQueries();
      if (onDeleted) onDeleted();
      else router.back();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        variant="destructive-outline"
        size={size}
        onClick={() => {
          setReason("");
          setError(null);
          setOpen(true);
        }}
        aria-label={size === "icon" ? t("button") : undefined}
        data-testid="delete-record"
      >
        <Trash2 aria-hidden />
        {size === "icon" ? null : t("button")}
      </Button>
      <Dialog open={open} onOpenChange={(v) => !busy && setOpen(v)}>
        {open ? (
          <DialogContent closeLabel={tc("close")}>
            <DialogHeader>
              <DialogTitle>{t("title")}</DialogTitle>
              <DialogDescription>{t("body")}</DialogDescription>
            </DialogHeader>
            <Alert tone="warning">{t("warning")}</Alert>
            <FormField id="delete-reason" label={tc("reason")} required>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="delete-reason" />
            </FormField>
            <MutationError error={error} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
                {tc("cancel")}
              </Button>
              <Button variant="destructive" onClick={() => void run()} disabled={busy || !reason.trim()} data-testid="delete-record-confirm">
                {busy ? t("deleting") : t("confirm")}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </>
  );
}
