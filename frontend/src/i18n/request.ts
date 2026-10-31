import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";
import { mergeQuality, type MessageTree } from "./quality-messages";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;
  const base = (await import(`../../messages/${locale}.json`)).default as MessageTree;
  // 8-quality §3.3a: each Quality part keeps its strings in messages/quality/q<n>.<locale>.json,
  // deep-merged under the `quality` namespace (a key defined twice fails).
  const parts = await Promise.all(
    [0, 1, 2, 3, 4].map(async (n) => (await import(`../../messages/quality/q${n}.${locale}.json`)).default as MessageTree),
  );
  return {
    locale,
    timeZone: "Asia/Riyadh",
    messages: mergeQuality(base, parts),
  };
});
