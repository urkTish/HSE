"use client";
import { Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";

/** Permanent delete (D-265), shown only to the named platform administrator. */
export function DeleteProject({ projectId, code }: { projectId: string; code: string }) {
  const t = useTranslations("project.delete");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const matches = typed.trim() === code;

  async function submit() {
    if (!matches) return;
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.POST("/api/v1/projects/{project_id}/delete", { params: { path: { project_id: projectId } }, body: { confirm_code: typed.trim() } }),
      );
      toast.success(t("done", { code }));
      setOpen(false);
      qc.removeQueries();
      router.push("/projects");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">{t("body")}</p>
        <div>
          <Button
            variant="destructive-outline"
            size="sm"
            onClick={() => {
              setTyped("");
              setError(null);
              setOpen(true);
            }}
            data-testid="delete-project"
          >
            <Trash2 aria-hidden />
            {t("button")}
          </Button>
        </div>
      </CardContent>
      <Dialog open={open} onOpenChange={(v) => !busy && setOpen(v)}>
        {open ? (
          <DialogContent closeLabel={tc("close")}>
            <DialogHeader>
              <DialogTitle>{t("dialogTitle", { code })}</DialogTitle>
              <DialogDescription>{t("dialogBody")}</DialogDescription>
            </DialogHeader>
            <Alert tone="warning">{t("warning")}</Alert>
            <FormField id="delete-confirm" label={t("typeCode", { code })} required>
              <Input dir="ltr" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} data-testid="delete-confirm-code" />
            </FormField>
            <MutationError error={error} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
                {tc("cancel")}
              </Button>
              <Button variant="destructive" onClick={submit} disabled={!matches || busy} data-testid="delete-confirm">
                {busy ? t("deleting") : t("confirm")}
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </Card>
  );
}
