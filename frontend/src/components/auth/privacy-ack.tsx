"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxField } from "@/components/common/form-field";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { PrivacyText } from "@/components/auth/privacy-text";
import { useLogout } from "@/components/auth/use-logout";
import { useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { keys, usePrivacyNotice } from "@/lib/api/queries";

export function PrivacyAck() {
  const t = useTranslations("auth.privacy");
  const ts = useTranslations("shell");
  const notice = usePrivacyNotice();
  const qc = useQueryClient();
  const router = useRouter();
  const logout = useLogout();
  const [checked, setChecked] = useState(false);
  const [checkError, setCheckError] = useState<string | undefined>();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!notice.data) return;
    if (!checked) {
      setCheckError(t("mustAck"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const me = await unwrap(api.POST("/api/v1/auth/privacy-notice/ack", { body: { version: notice.data.version } }));
      qc.setQueryData(keys.me, me);
      router.replace("/", { locale: me.display_language });
    } catch (e) {
      setError(e);
      if (e && typeof e === "object" && "code" in e && e.code === "PRIVACY_NOTICE_VERSION_MISMATCH") {
        await notice.refetch();
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="text-xl">{t("title")}</span>
        </CardTitle>
        <CardDescription>{t("intro")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {notice.isLoading ? (
          <LoadingState rows={3} />
        ) : notice.isError ? (
          <ErrorState error={notice.error} onRetry={() => notice.refetch()} />
        ) : notice.data ? (
          <>
            <PrivacyText notice={notice.data} />
            <CheckboxField id="privacy-ack" label={t("acknowledge")} error={checkError}>
              <Checkbox
                checked={checked}
                onChange={(e) => {
                  setChecked(e.target.checked);
                  setCheckError(undefined);
                }}
              />
            </CheckboxField>
            <MutationError error={error} />
            <Button size="lg" onClick={submit} disabled={busy}>
              {busy ? t("submitting") : t("submit")}
            </Button>
            <Button variant="ghost" onClick={logout}>
              {ts("logout")}
            </Button>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
