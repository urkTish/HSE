import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HseTeamPage } from "@/components/users/hse-team";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HseTeamPage />;
}
