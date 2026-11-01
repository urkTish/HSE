import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { KpisPage } from "@/components/quality/q4/analytics";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <KpisPage />;
}
