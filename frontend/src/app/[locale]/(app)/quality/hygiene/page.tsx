import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HygienePage } from "@/components/quality/q3/hygiene";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HygienePage />;
}
