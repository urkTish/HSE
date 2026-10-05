import { hasLocale } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { routing, type AppLocale } from "./routing";

export type LocaleParams = { params: Promise<{ locale: string }> };

/** Validate the [locale] segment and enable static rendering for next-intl. */
export async function initRequestLocale(params: LocaleParams["params"]): Promise<AppLocale> {
  const { locale } = await params;
  const l: AppLocale = hasLocale(routing.locales, locale) ? locale : routing.defaultLocale;
  setRequestLocale(l);
  return l;
}
