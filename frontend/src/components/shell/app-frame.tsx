"use client";
import { useEffect, type ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { useMe } from "@/lib/api/queries";
import { ApiError } from "@/lib/api/client";
import { CurrentProjectProvider } from "@/lib/current-project";
import { ErrorState } from "@/components/common/states";
import { MeContext } from "@/components/shell/me-context";
import { Shell } from "@/components/shell/shell";
import { ReauthProvider } from "@/components/ptw/signing";

function FullPageLoading() {
  const t = useTranslations("common");
  return (
    <div className="flex min-h-dvh items-center justify-center gap-2 text-muted-foreground" aria-busy="true">
      <ShieldCheck aria-hidden className="size-6 animate-pulse text-primary" />
      <span>{t("loading")}</span>
    </div>
  );
}

/** Authenticated area: resolves the session, then renders the shell. Redirects are driven by auth events. */
export function AppFrame({ children }: { children: ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const mfaBlocked = Boolean(me.data?.mfa_setup_blocking && !me.data.mfa_enabled);
  useEffect(() => {
    if (mfaBlocked) router.replace("/mfa-setup");
  }, [mfaBlocked, router]);
  if (me.isLoading || mfaBlocked) return <FullPageLoading />;
  if (me.isError) {
    const e = me.error;
    const redirecting =
      e instanceof ApiError && (e.status === 401 || e.code === "PRIVACY_ACK_REQUIRED" || e.code === "MFA_ENROLMENT_REQUIRED");
    if (redirecting) return <FullPageLoading />;
    return (
      <div className="mx-auto max-w-lg p-8">
        <ErrorState error={e} onRetry={() => me.refetch()} />
      </div>
    );
  }
  if (!me.data) return <FullPageLoading />;
  return (
    <MeContext.Provider value={me.data}>
      <CurrentProjectProvider>
        <ReauthProvider>
          <Shell>{children}</Shell>
        </ReauthProvider>
      </CurrentProjectProvider>
    </MeContext.Provider>
  );
}
