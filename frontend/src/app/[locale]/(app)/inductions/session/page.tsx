import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { InductionSessionPage } from "@/components/access/inductions";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <InductionSessionPage />;
}
