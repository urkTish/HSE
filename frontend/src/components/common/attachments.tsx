"use client";
import { Camera, Download, Paperclip, Trash2, Upload } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useAttachments } from "@/lib/api/hse";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";

function size(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Files on a record: list, upload (incl. phone camera), short-lived signed-URL download. */
export function Attachments({
  ownerType,
  ownerId,
  canUpload,
  canDelete,
  hint,
  max,
  onChange,
}: {
  ownerType: Schemas["AttachmentOwner"];
  ownerId: string;
  canUpload: boolean;
  canDelete?: boolean;
  hint?: string;
  max?: number;
  onChange?: () => void;
}) {
  const t = useTranslations("common");
  const msg = useErrorMessage();
  const qc = useQueryClient();
  const { dateTime } = useFormatters();
  const q = useAttachments(ownerType, ownerId);
  const fileRef = useRef<HTMLInputElement>(null);
  const camRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const items = q.data?.items ?? [];
  const full = max !== undefined && items.length >= max;

  async function upload(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    try {
      for (const f of Array.from(files)) {
        const form = new FormData();
        form.set("owner_type", ownerType);
        form.set("owner_id", ownerId);
        form.set("file", f);
        await postForm<Schemas["AttachmentRead"]>("/api/v1/attachments", form);
      }
      await qc.invalidateQueries({ queryKey: hk.attachments(ownerType, ownerId) });
      onChange?.();
    } catch (e) {
      toast.error(msg(e));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
      if (camRef.current) camRef.current.value = "";
    }
  }

  async function open(a: Schemas["AttachmentRead"]) {
    try {
      const s = await unwrap(api.POST("/api/v1/attachments/{attachment_id}/signed-url", { params: { path: { attachment_id: a.id } } }));
      window.open(s.url, "_blank", "noopener");
    } catch (e) {
      toast.error(msg(e));
    }
  }

  async function remove(a: Schemas["AttachmentRead"]) {
    try {
      await unwrap(api.DELETE("/api/v1/attachments/{attachment_id}", { params: { path: { attachment_id: a.id } } }));
      await qc.invalidateQueries({ queryKey: hk.attachments(ownerType, ownerId) });
      onChange?.();
    } catch (e) {
      toast.error(msg(e));
    }
  }

  return (
    <div className="flex flex-col gap-3" data-testid={`attachments-${ownerType}`}>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("noAttachments")}</p>
      ) : (
        <ul className="flex flex-col divide-y rounded-lg border">
          {items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
              <Paperclip aria-hidden className="size-4 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate ltr">{a.file_name}</span>
              <span className="text-xs text-muted-foreground">
                {size(a.size_bytes)} · {dateTime(a.created_at)}
              </span>
              {a.scan_status === "pending" ? <Badge tone="info">{t("scanPending")}</Badge> : null}
              <Button variant="ghost" size="sm" onClick={() => void open(a)} disabled={a.scan_status === "infected"}>
                <Download aria-hidden />
                {t("download")}
              </Button>
              {canDelete ? (
                <Button variant="ghost" size="icon" aria-label={t("delete")} onClick={() => void remove(a)}>
                  <Trash2 aria-hidden />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canUpload && !full ? (
        <div className="flex flex-wrap gap-2">
          <input ref={fileRef} type="file" accept="image/*,application/pdf" multiple className="sr-only" onChange={(e) => void upload(e.target.files)} data-testid="file-input" aria-label={t("upload")} />
          <input ref={camRef} type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => void upload(e.target.files)} aria-label={t("takePhoto")} tabIndex={-1} />
          <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={busy}>
            <Upload aria-hidden />
            {busy ? t("uploading") : t("upload")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => camRef.current?.click()} disabled={busy} className="md:hidden">
            <Camera aria-hidden />
            {t("takePhoto")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
