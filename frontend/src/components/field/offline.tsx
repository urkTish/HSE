"use client";
import { CloudDownload, CloudUpload, Hourglass, Trash2, WifiOff, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Code } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { useFieldRefresh } from "@/lib/api/field";
import { deletePack, discardOutbox, downloadPack, flushOutbox, useFieldOffline, useFieldOfflineSync, type OutboxKind } from "@/lib/field-offline";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { useOnline } from "@/lib/local-draft";
import { useFormatters } from "@/lib/use-formatters";

/** Mounted in the shell: owner check, 72 h purge, and sending waiting items when the signal returns. */
export function FieldOfflineSync() {
  const me = useMeData();
  const t = useTranslations("field.offline");
  const refresh = useFieldRefresh();
  const onSent = useCallback(
    (n: number) => {
      toast.success(t("sentN", { n }));
      void refresh();
    },
    [t, refresh],
  );
  useFieldOfflineSync(me.id, onSent);
  return null;
}

/** The phone's offline pack for a project: download, refresh, delete; shows when it expires (EXE-6). */
export function OfflinePackCard({ projectId }: { projectId: string }) {
  const t = useTranslations("field.offline");
  const msg = useErrorMessage();
  const online = useOnline();
  const { packs } = useFieldOffline();
  const { dateTime } = useFormatters(projectId);
  const [busy, setBusy] = useState(false);
  const p = packs[projectId];
  return (
    <Card data-testid="offline-pack" data-cached={p ? "yes" : "no"}>
      <CardContent className="flex flex-wrap items-center gap-3 p-4 text-sm">
        <CloudDownload aria-hidden className="size-5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1">
          {p ? (
            <>
              <span className="font-medium">{t("packReady")}</span>{" "}
              <span className="text-muted-foreground">
                {t("packInfo", { at: dateTime(p.cached_at), until: dateTime(p.pack.expires_at), n: p.pack.deployments.length, i: p.pack.instances.length })}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground">{t("packNone")}</span>
          )}
        </span>
        <span className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            className="min-h-11"
            disabled={busy || !online}
            onClick={async () => {
              setBusy(true);
              try {
                await downloadPack(projectId);
                toast.success(t("packSaved"));
              } catch (e) {
                toast.error(msg(e));
              } finally {
                setBusy(false);
              }
            }}
            data-testid="pack-download"
          >
            <CloudDownload aria-hidden />
            {p ? t("packRefresh") : t("packDownload")}
          </Button>
          {p ? (
            <Button variant="ghost" className="min-h-11" onClick={() => void deletePack(projectId)} data-testid="pack-delete">
              <Trash2 aria-hidden />
              {t("packDelete")}
            </Button>
          ) : null}
        </span>
      </CardContent>
    </Card>
  );
}

/** "Waiting to send" panel: items recorded without signal (or refused by the server) on this device. */
export function OutboxPanel({ kind, projectId }: { kind: OutboxKind; projectId: string }) {
  const t = useTranslations("field.offline");
  const ar = useLocale() === "ar";
  const online = useOnline();
  const refresh = useFieldRefresh();
  const { outbox } = useFieldOffline();
  const { dateTime } = useFormatters(projectId);
  const [busy, setBusy] = useState(false);
  const items = outbox.filter((i) => i.kind === kind && i.project_id === projectId);
  if (!items.length && online) return null;
  return (
    <div className="mb-4 flex flex-col gap-2" data-testid="outbox" data-count={items.length}>
      {!online ? (
        <Alert tone="warning" data-testid="offline-banner">
          <span className="inline-flex items-center gap-2">
            <WifiOff aria-hidden className="size-4 shrink-0" />
            {t("offlineNow")}
          </span>
        </Alert>
      ) : null}
      {items.length ? (
        <Card className="border-warning/40">
          <CardContent className="flex flex-col gap-3 p-4">
            <p className="flex items-center gap-2 font-semibold">
              <Hourglass aria-hidden className="size-5 text-warning" />
              {t("waiting", { n: items.length })}
            </p>
            <ul className="flex flex-col divide-y text-sm">
              {items.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center gap-2 py-2" data-testid="outbox-item" data-state={i.error ? "rejected" : "waiting"}>
                  {i.error ? <XCircle aria-hidden className="size-4 shrink-0 text-danger" /> : <Hourglass aria-hidden className="size-4 shrink-0 text-warning" />}
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{i.label}</span> <span className="text-muted-foreground">· {dateTime(i.created_at)}</span>
                    {i.error ? (
                      <span className="block text-danger" data-testid="outbox-error" data-code={i.error.code}>
                        {t("refused")} {ar && i.error.message_ar ? i.error.message_ar : i.error.message} (<Code>{i.error.code}</Code>)
                      </span>
                    ) : (
                      <span className="block text-xs text-muted-foreground">{t("keptUntil", { at: dateTime(i.expires_at) })}</span>
                    )}
                  </span>
                  {i.error ? (
                    <Button variant="ghost" size="sm" onClick={() => void discardOutbox(i.id)} data-testid="outbox-discard">
                      <Trash2 aria-hidden />
                      {t("discard")}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
            {items.some((i) => !i.error) ? (
              <Button
                className="min-h-11 self-start"
                disabled={busy || !online}
                onClick={async () => {
                  setBusy(true);
                  try {
                    const r = await flushOutbox();
                    if (r.sent) {
                      toast.success(t("sentN", { n: r.sent }));
                      await refresh();
                    }
                  } finally {
                    setBusy(false);
                  }
                }}
                data-testid="outbox-send"
              >
                <CloudUpload aria-hidden />
                {t("sendNow")}
              </Button>
            ) : null}
            <p className="text-xs text-muted-foreground">{t("outboxHint")}</p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
