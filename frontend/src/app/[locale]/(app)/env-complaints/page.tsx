import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ComplaintsPage } from "@/components/env/spills";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ComplaintsPage />;
}
