"use client";
import { useTranslations } from "next-intl";
import { Alert } from "@/components/ui/alert";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { gb, useLicence } from "@/lib/api/licence";
import { useFormatters } from "@/lib/use-formatters";

/** Paid licences show the banner only in their last weeks; a trial always shows its countdown. */
const ENDING_SOON_DAYS = 30;

/**
 * D-294: the licence banner on every page. Trial → "Trial: N days left"; expired or invalid key →
 * "read-only" for everyone; storage at 80 % and over → a warning for the HSE Manager. Nothing when
 * no key is installed (unlimited) or a paid licence has more than 30 days left.
 */
export function LicenceBanner() {
  const t = useTranslations("licenceBanner");
  const me = useMeData();
  const { date } = useFormatters();
  const q = useLicence();
  const l = q.data;
  if (!l || l.state === "none") return null;

  const manageLink = me.is_hse_manager ? (
    <Link href="/licence" className="font-medium underline underline-offset-2" data-testid="licence-banner-link">
      {t("manage")}
    </Link>
  ) : null;

  if (l.read_only) {
    return (
      <Alert tone="danger" className="mb-4 print:hidden" data-testid="licence-banner" data-state={l.state}>
        <p className="font-semibold">{l.state === "invalid" ? t("invalid") : t("expired")}</p>
        <p>
          {t("readOnlyText")} {me.is_hse_manager ? null : t("askManager")}
        </p>
        {l.data_deletion_after ? <p>{t("deletion", { date: date(l.data_deletion_after) })}</p> : null}
        {manageLink ? <p className="mt-1">{manageLink}</p> : null}
      </Alert>
    );
  }

  const days = l.days_left ?? 0;
  const countdown = l.is_trial || days <= ENDING_SOON_DAYS;
  const storage = me.is_hse_manager && l.storage.warning && l.storage.limit_gb !== null;
  if (!countdown && !storage) return null;
  const tone = storage || days <= 7 ? "warning" : "info";
  return (
    <Alert tone={tone} className="mb-4 print:hidden" data-testid="licence-banner" data-state={l.state}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {countdown ? (
          <>
            <span className="font-semibold" data-testid="licence-banner-days">
              {l.is_trial ? t("trial", { n: days }) : t("ending", { n: days })}
            </span>
            {l.valid_until ? <span>{t("until", { date: date(l.valid_until) })}</span> : null}
          </>
        ) : null}
        {storage ? (
          <span data-testid="licence-banner-storage">
            {t("storage", { percent: l.storage.percent ?? 0, used: gb(l.storage.used_bytes), limit: l.storage.limit_gb ?? 0 })}
          </span>
        ) : null}
        {manageLink}
      </div>
    </Alert>
  );
}
