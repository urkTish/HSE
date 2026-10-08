"use client";
import { useQueryClient } from "@tanstack/react-query";
import { KeyRound, PenLine } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/common/form-field";
import { MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { ApiError, api, unwrap, type Schemas } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { useFormatters } from "@/lib/use-formatters";
import { useNow, userLabel } from "./common";

type Ask = () => Promise<boolean>;
const ReauthContext = createContext<Ask | null>(null);

/**
 * Step-up re-authentication for signing actions (PT-15). A 401 REAUTH_REQUIRED is not a logout: the user types
 * their password, POST /auth/reauth runs, and the same request is sent again unchanged.
 */
export function ReauthProvider({ children }: { children: ReactNode }) {
  const t = useTranslations("ptw.reauth");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  const ask = useCallback<Ask>(
    () =>
      new Promise<boolean>((resolve) => {
        resolver.current = resolve;
        setPassword("");
        setError(null);
        setOpen(true);
      }),
    [],
  );

  function finish(ok: boolean) {
    setOpen(false);
    setPassword("");
    resolver.current?.(ok);
    resolver.current = null;
  }

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/auth/reauth", { body: { password } }));
      await qc.invalidateQueries({ queryKey: keys.me });
      finish(true);
    } catch (e) {
      setError(e instanceof ApiError && e.code === "REAUTH_REQUIRED" ? new ApiError(401, { code: "INVALID_CREDENTIALS", message: "Invalid password" }) : e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <ReauthContext.Provider value={ask}>
      {children}
      <Dialog open={open} onOpenChange={(v) => !v && finish(false)}>
        <DialogContent closeLabel={tc("close")} data-testid="reauth-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound aria-hidden className="size-5" />
              {t("title")}
            </DialogTitle>
            <DialogDescription>{t("body")}</DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (password) void confirm();
            }}
            className="flex flex-col gap-3"
          >
            <FormField id="reauth-password" label={t("password")} required>
              <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus data-testid="reauth-password" />
            </FormField>
            <MutationError error={error} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => finish(false)}>
                {tc("cancel")}
              </Button>
              <Button type="submit" disabled={!password || busy} data-testid="reauth-confirm">
                {busy ? tc("saving") : t("confirm")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </ReauthContext.Provider>
  );
}

/** Wrap a signing request: on REAUTH_REQUIRED ask for the password and resend it once. */
export function useSigned() {
  const ask = useContext(ReauthContext);
  return useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T> => {
      try {
        return await fn();
      } catch (e) {
        if (ask && e instanceof ApiError && e.status === 401 && e.code === "REAUTH_REQUIRED") {
          const ok = await ask();
          if (!ok) throw e;
          return await fn();
        }
        throw e;
      }
    },
    [ask],
  );
}

/** "You are signing" notice with the signer's name (and whether a password will be asked). */
export function SigningNotice() {
  const t = useTranslations("ptw.reauth");
  const me = useMeData();
  const locale = useLocale();
  const now = useNow(30_000);
  const valid = me.reauth_valid_until ? new Date(me.reauth_valid_until).getTime() > now : false;
  return (
    <p className="flex items-start gap-2 rounded-md border bg-surface p-2 text-xs text-muted-foreground" data-testid="signing-notice">
      <PenLine aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span>
        {t("signingAs", { name: locale === "ar" && me.full_name_ar ? me.full_name_ar : me.full_name_en })} {valid ? null : t("willAsk")}
      </span>
    </p>
  );
}

export type CosignState = { mode: "device" | "here"; password: string };

/**
 * Receiver co-signature on issue / revalidate / resume: either the receiver already accepted on their own device
 * (POST receiver-acceptance, still valid), or they type their password here on the issuer's device.
 */
export function ReceiverCosign({
  permit,
  purpose,
  value,
  onChange,
}: {
  permit: Schemas["PermitRead"];
  purpose: Schemas["AcceptancePurpose"];
  value: CosignState;
  onChange: (v: CosignState) => void;
}) {
  const t = useTranslations("ptw.cosign");
  const locale = useLocale();
  const { dateTime } = useFormatters(permit.project_id);
  const acc = permit.receiver_acceptance;
  const now = useNow(30_000);
  const accepted = Boolean(acc && acc.purpose === purpose && new Date(acc.valid_until).getTime() > now);
  return (
    <fieldset className="flex flex-col gap-2 rounded-md border p-3" data-testid="receiver-cosign">
      <legend className="px-1 text-sm font-medium">{t("title", { name: userLabel(permit.receiver, locale) })}</legend>
      <label className="flex min-h-touch items-center gap-2 text-sm">
        <input type="radio" name="cosign-mode" checked={value.mode === "device"} onChange={() => onChange({ mode: "device", password: "" })} data-testid="cosign-device" />
        <span>
          {t("ownDevice")}
          {accepted && acc ? (
            <span className="block text-xs text-success" data-testid="receiver-accepted">
              {t("accepted", { until: dateTime(acc.valid_until) })}
            </span>
          ) : (
            <span className="block text-xs text-muted-foreground">{t("notYet")}</span>
          )}
        </span>
      </label>
      <label className="flex min-h-touch items-center gap-2 text-sm">
        <input type="radio" name="cosign-mode" checked={value.mode === "here"} onChange={() => onChange({ mode: "here", password: "" })} data-testid="cosign-here" />
        <span>{t("here")}</span>
      </label>
      {value.mode === "here" ? (
        <FormField id="cosign-password" label={t("password", { name: userLabel(permit.receiver, locale) })} required hint={t("passwordHint")}>
          <Input type="password" autoComplete="off" value={value.password} onChange={(e) => onChange({ ...value, password: e.target.value })} data-testid="cosign-password" />
        </FormField>
      ) : !accepted ? (
        <Alert tone="info">{t("askReceiver")}</Alert>
      ) : null}
    </fieldset>
  );
}

export function cosignBody(permit: Schemas["PermitRead"], v: CosignState): Schemas["CoSignature"] | null {
  return v.mode === "here" && v.password ? { user_id: permit.receiver.id, password: v.password } : null;
}

export function cosignReady(permit: Schemas["PermitRead"], purpose: Schemas["AcceptancePurpose"], v: CosignState): boolean {
  // On "own device" the server checks the stored acceptance (it may arrive after this page was loaded).
  void permit;
  void purpose;
  return v.mode === "device" || v.password.length > 0;
}
