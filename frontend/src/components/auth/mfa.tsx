"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, KeyRound, ShieldCheck } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { QrImage } from "@/components/access/common";
import { FormField } from "@/components/common/form-field";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useLogout } from "@/components/auth/use-logout";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useMe } from "@/lib/api/queries";
import { DEFAULT_TIME_ZONE, formatDate } from "@/lib/datetime";

export const mfaKey = ["auth", "mfa"] as const;

/** Dates on the MFA screens (no project settings outside the shell). */
export function useMfaDate() {
  const locale = useLocale() === "ar" ? "ar" : "en";
  return (v: string | null | undefined) =>
    formatDate(v, { locale, timeZone: DEFAULT_TIME_ZONE, showHijri: false, digits: "western", dateFormatEn: "DD MMM YYYY" });
}

/** A 6-digit authenticator code field (digits only, one-time-code autofill on phones). */
export function CodeInput({ id, value, onChange, error }: { id: string; value: string; onChange: (v: string) => void; error?: string }) {
  const t = useTranslations("mfa");
  return (
    <FormField id={id} label={t("code")} error={error} required>
      <Input
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        className="ltr h-touch max-w-48 text-center font-mono text-lg tracking-[0.3em]"
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        data-testid={`${id}-input`}
      />
    </FormField>
  );
}

/** Second sign-in step: authenticator code, or a recovery code when the phone is lost. */
export function MfaVerifyStep({ onDone, onBack }: { onDone: (res: Schemas["LoginResponse"]) => void; onBack: () => void }) {
  const t = useTranslations("mfa.verify");
  const tm = useTranslations("mfa");
  const [recovery, setRecovery] = useState(false);
  const [code, setCode] = useState("");
  const [rc, setRc] = useState("");
  const [fieldError, setFieldError] = useState<string>();
  const verify = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/v1/auth/mfa/verify", { body: recovery ? { recovery_code: rc.trim() } : { code } })),
    onSuccess: (res) => {
      if (recovery) toast.info(t("lowCodes"));
      onDone(res);
    },
    onError: () => {
      setCode("");
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!recovery && code.length !== 6) {
      setFieldError(tm("codeInvalid"));
      return;
    }
    if (recovery && rc.trim().length < 8) return;
    setFieldError(undefined);
    verify.mutate();
  }

  return (
    <Card data-testid="mfa-verify">
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2 text-xl">
            <ShieldCheck aria-hidden className="size-5 text-primary" />
            {recovery ? t("recoveryTitle") : t("title")}
          </span>
        </CardTitle>
        <CardDescription>{recovery ? t("recoverySubtitle") : t("subtitle")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate className="flex flex-col gap-4">
          <MutationError error={verify.error} />
          {recovery ? (
            <FormField id="mfa-recovery" label={t("recoveryCode")} required>
              <Input
                autoComplete="off"
                className="ltr h-touch font-mono"
                value={rc}
                onChange={(e) => setRc(e.target.value)}
                data-testid="mfa-recovery-input"
              />
            </FormField>
          ) : (
            <CodeInput id="mfa-code" value={code} onChange={setCode} error={fieldError} />
          )}
          <Button type="submit" size="lg" disabled={verify.isPending} data-testid="mfa-verify-submit">
            {verify.isPending ? t("submitting") : t("submit")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setRecovery((r) => !r);
              verify.reset();
              setFieldError(undefined);
            }}
            data-testid="mfa-toggle-recovery"
          >
            {recovery ? t("useApp") : t("useRecovery")}
          </Button>
          <Button type="button" variant="link" onClick={onBack}>
            {t("backToLogin")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

/** Recovery codes, shown once after set-up or regeneration, with copy and download. */
export function RecoveryCodes({ codes, email }: { codes: string[]; email: string }) {
  const t = useTranslations("mfa.codes");
  const text = `${t("fileTitle", { email })}\n\n${codes.join("\n")}\n`;
  return (
    <div className="flex flex-col gap-3" data-testid="mfa-recovery-codes">
      <h3 className="font-semibold">{t("title")}</h3>
      <Alert tone="warning">{t("hint")}</Alert>
      <ul className="ltr grid grid-cols-2 gap-2 rounded-lg border bg-surface p-3 font-mono text-sm" dir="ltr">
        {codes.map((c) => (
          <li key={c} data-testid="mfa-recovery-code">
            {c}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              toast.success(t("copied"));
            } catch {
              /* clipboard blocked: the codes stay on screen */
            }
          }}
        >
          <Copy aria-hidden />
          {t("copy")}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            const href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
            const a = document.createElement("a");
            a.href = href;
            a.download = "recovery-codes.txt";
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(href);
          }}
        >
          <Download aria-hidden />
          {t("download")}
        </Button>
      </div>
    </div>
  );
}

/** Enrolment: QR + manual key → first code → recovery codes. `onFinished` runs after the codes were saved. */
export function MfaEnrol({ email, onFinished }: { email: string; onFinished: () => void }) {
  const t = useTranslations("mfa.setup");
  const tm = useTranslations("mfa");
  const tc = useTranslations("mfa.codes");
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const [fieldError, setFieldError] = useState<string>();
  const [codes, setCodes] = useState<string[] | null>(null);
  const start = useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/auth/mfa/setup")) });
  const confirm = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/mfa/confirm", { body: { code } })),
    onSuccess: (res) => {
      setCodes(res.codes);
      void qc.invalidateQueries({ queryKey: keys.me });
      void qc.invalidateQueries({ queryKey: mfaKey });
    },
    onError: () => setCode(""),
  });

  if (codes) {
    return (
      <div className="flex flex-col gap-4">
        <Alert tone="success">{t("done")}</Alert>
        <RecoveryCodes codes={codes} email={email} />
        <Button type="button" size="lg" onClick={onFinished} data-testid="mfa-finish">
          {tc("saved")}
        </Button>
      </div>
    );
  }
  if (!start.data) {
    return (
      <div className="flex flex-col gap-3">
        <MutationError error={start.error} />
        <Button type="button" size="lg" onClick={() => start.mutate()} disabled={start.isPending} data-testid="mfa-start">
          <KeyRound aria-hidden />
          {t("start")}
        </Button>
      </div>
    );
  }
  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (code.length !== 6) {
          setFieldError(tm("codeInvalid"));
          return;
        }
        setFieldError(undefined);
        confirm.mutate();
      }}
    >
      <p className="text-sm">{t("step1")}</p>
      <p className="text-sm">{t("step2")}</p>
      <div className="flex justify-center">
        <QrImage payload={start.data.otpauth_uri} size={200} label={t("qrLabel")} />
      </div>
      <div className="text-sm">
        <p className="text-muted-foreground">{t("manual")}</p>
        <p className="ltr mt-1 break-all rounded-md border bg-surface p-2 font-mono text-sm" dir="ltr" data-testid="mfa-secret">
          {start.data.secret.replace(/(.{4})/g, "$1 ").trim()}
        </p>
      </div>
      <p className="text-sm">{t("step3")}</p>
      <CodeInput id="mfa-setup-code" value={code} onChange={setCode} error={fieldError} />
      <MutationError error={confirm.error} />
      <Button type="submit" size="lg" disabled={confirm.isPending} data-testid="mfa-confirm">
        {confirm.isPending ? t("confirming") : t("confirm")}
      </Button>
    </form>
  );
}

/** Profile card: status, set-up link, new recovery codes, turn off (optional roles only). */
export function MfaProfileCard({ me }: { me: Schemas["Me"] }) {
  const t = useTranslations("mfa");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const fmt = useMfaDate();
  const status = useQuery({ queryKey: mfaKey, queryFn: () => unwrap(api.GET("/api/v1/auth/mfa")) });
  const [dialog, setDialog] = useState<"codes" | "off" | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [newCodes, setNewCodes] = useState<string[] | null>(null);
  const regen = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/mfa/recovery-codes", { body: { code } })),
    onSuccess: (res) => {
      setNewCodes(res.codes);
      setCode("");
      void qc.invalidateQueries({ queryKey: mfaKey });
    },
  });
  const off = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/mfa/disable", { body: { password, code } })),
    onSuccess: () => {
      toast.success(t("turnedOff"));
      close();
      void qc.invalidateQueries({ queryKey: mfaKey });
      void qc.invalidateQueries({ queryKey: keys.me });
    },
  });
  function close() {
    setDialog(null);
    setCode("");
    setPassword("");
    setNewCodes(null);
    regen.reset();
    off.reset();
  }
  const s = status.data;
  const enabled = s?.enabled ?? me.mfa_enabled;
  const required = s?.required ?? me.mfa_required ?? false;
  return (
    <Card data-testid="mfa-card">
      <CardHeader>
        <CardTitle>
          <span className="flex flex-wrap items-center gap-2">
            {t("title")}
            <Badge tone={enabled ? "success" : required ? "warning" : "neutral"} data-testid="mfa-status">
              {enabled ? t("statusOn") : t("statusOff")}
            </Badge>
          </span>
        </CardTitle>
        <CardDescription>{t("intro")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {required ? <p className="font-medium">{t("requiredNote")}</p> : null}
        {enabled && s?.enabled_at ? <p className="text-muted-foreground">{t("enabledSince", { date: fmt(s.enabled_at) })}</p> : null}
        {enabled && s ? (
          <p className={s.recovery_codes_remaining <= 2 ? "font-medium text-warning" : "text-muted-foreground"} data-testid="mfa-codes-left">
            {t("codesLeft", { count: s.recovery_codes_remaining })}
          </p>
        ) : null}
        {!enabled && required && s?.setup_due ? <p>{t("setup.due", { date: fmt(s.setup_due) })}</p> : null}
        <div className="flex flex-wrap gap-2">
          {!enabled ? (
            <Button asChild>
              <Link href="/mfa-setup" data-testid="mfa-setup-link">
                {t("setUp")}
              </Link>
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={() => setDialog("codes")} data-testid="mfa-new-codes">
                {t("newCodes")}
              </Button>
              {!required ? (
                <Button type="button" variant="destructive-outline" onClick={() => setDialog("off")} data-testid="mfa-turn-off">
                  {t("turnOff")}
                </Button>
              ) : null}
            </>
          )}
        </div>
      </CardContent>
      <Dialog open={dialog !== null} onOpenChange={(o) => (o ? null : close())}>
        <DialogContent closeLabel={tc("close")}>
          <DialogHeader>
            <DialogTitle>{dialog === "off" ? t("turnOffTitle") : t("newCodes")}</DialogTitle>
            <DialogDescription>{dialog === "off" ? t("turnOffHint") : t("newCodesHint")}</DialogDescription>
          </DialogHeader>
          {newCodes ? (
            <RecoveryCodes codes={newCodes} email={me.email} />
          ) : (
            <form
              id="mfa-dialog-form"
              noValidate
              className="flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (code.length !== 6) return;
                if (dialog === "off") off.mutate();
                else regen.mutate();
              }}
            >
              {dialog === "off" ? (
                <FormField id="mfa-off-password" label={t("password")} required>
                  <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                </FormField>
              ) : null}
              <CodeInput id="mfa-dialog-code" value={code} onChange={setCode} />
              <MutationError error={dialog === "off" ? off.error : regen.error} />
            </form>
          )}
          <DialogFooter>
            {newCodes ? (
              <Button type="button" onClick={close}>
                {tc("close")}
              </Button>
            ) : (
              <>
                <Button type="button" variant="outline" onClick={close}>
                  {tc("cancel")}
                </Button>
                <Button
                  type="submit"
                  form="mfa-dialog-form"
                  variant={dialog === "off" ? "destructive" : "default"}
                  disabled={code.length !== 6 || regen.isPending || off.isPending}
                  data-testid="mfa-dialog-submit"
                >
                  {dialog === "off" ? t("turnOff") : t("newCodes")}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/** Shell banner while a required user is in the grace period. */
export function MfaBanner({ me }: { me: Schemas["Me"] }) {
  const t = useTranslations("mfa");
  const fmt = useMfaDate();
  if (!me.mfa_required || me.mfa_enabled || !me.mfa_setup_due) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-warning/40 bg-warning-bg px-3 py-2 text-sm print:hidden" data-testid="mfa-banner">
      <ShieldCheck aria-hidden className="size-4 shrink-0 text-warning" />
      <span className="min-w-0 flex-1">{t("banner", { date: fmt(me.mfa_setup_due) })}</span>
      <Link href="/mfa-setup" className="font-medium text-primary underline-offset-4 hover:underline">
        {t("bannerAction")}
      </Link>
    </div>
  );
}

/** /mfa-setup: outside the shell, so a user whose grace period is over can still reach it. */
export function MfaSetupPage() {
  const t = useTranslations("mfa.setup");
  const tm = useTranslations("mfa");
  const qc = useQueryClient();
  const router = useRouter();
  const logout = useLogout();
  const fmt = useMfaDate();
  const me = useMe();
  if (!me.data) {
    return me.isError && !(me.error instanceof ApiError && me.error.status === 401) ? (
      <ErrorState error={me.error} onRetry={() => me.refetch()} />
    ) : (
      <LoadingState rows={3} />
    );
  }
  const m = me.data;
  const done = () => {
    void qc.invalidateQueries({ queryKey: keys.me });
    router.replace("/", { locale: m.display_language });
  };
  return (
    <Card data-testid="mfa-setup">
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2 text-xl">
            <ShieldCheck aria-hidden className="size-5 text-primary" />
            {t("title")}
          </span>
        </CardTitle>
        <CardDescription>{tm("intro")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {m.mfa_enabled ? (
          <>
            <Alert tone="success">{t("alreadyOn")}</Alert>
            <Button type="button" onClick={done}>
              {t("continue")}
            </Button>
          </>
        ) : (
          <>
            {m.mfa_setup_blocking ? (
              <Alert tone="warning" data-testid="mfa-blocking">
                {t("blocking")}
              </Alert>
            ) : m.mfa_required && m.mfa_setup_due ? (
              <Alert tone="info">{t("due", { date: fmt(m.mfa_setup_due) })}</Alert>
            ) : null}
            <MfaEnrol email={m.email} onFinished={done} />
            {m.mfa_setup_blocking ? (
              <Button type="button" variant="link" onClick={() => void logout()}>
                {t("signOut")}
              </Button>
            ) : (
              <Button type="button" variant="link" onClick={done} data-testid="mfa-later">
                {t("later")}
              </Button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
